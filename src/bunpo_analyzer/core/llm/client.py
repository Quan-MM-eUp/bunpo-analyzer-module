"""Lop goi LLM dung chung (buoc 2.1).

- Goi model chinh; loi tam thoi (timeout, gateway 5xx/429) thi goi lai toi da
  `llm_max_retries` lan, cach nhau ngan.
- Van loi (hoac `use_fallback=True`, vi du buoc 2.3 khi dau ra sai khuon) thi
  goi model du phong.
- Moi lan goi ghi log: model, token, do tre, chi phi uoc tinh.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Optional

from bunpo_analyzer.config import Settings, get_settings
from bunpo_analyzer.core.llm.base import LLMError, LLMProvider, LLMResult, Message, T

log = logging.getLogger("bunpo_analyzer.llm")


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        from bunpo_analyzer.core.llm.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(settings.openai_api_key, settings.openai_base_url, settings.llm_prices,
                                    reasoning_effort=settings.llm_reasoning_effort)
    raise LLMError("config", f"chua ho tro nha cung cap '{settings.llm_provider}'")


class LLMClient:
    def __init__(self, provider: Optional[LLMProvider] = None, settings: Optional[Settings] = None,
                 retry_delay_s: float = 0.5) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or get_provider(self.settings)
        self.retry_delay_s = retry_delay_s

    async def _try_model(self, messages: list[Message], output_model: type[T], model: str,
                         attempts: int) -> tuple[Optional[LLMResult[T]], Optional[LLMError], int]:
        s = self.settings
        last: Optional[LLMError] = None
        for k in range(s.llm_max_retries + 1):
            attempts += 1
            try:
                res = await self.provider.generate(messages, output_model, model, s.llm_timeout_s, s.llm_max_tokens)
                return res, None, attempts
            except LLMError as e:
                last = e
                log.warning("llm loi model=%s lan=%d kind=%s: %s", model, k + 1, e.kind, e)
                if not e.retryable:
                    break
                if k < s.llm_max_retries:
                    await asyncio.sleep(self.retry_delay_s * (k + 1))
        return None, last, attempts

    async def generate(self, messages: list[Message], output_model: type[T],
                       use_fallback: bool = False, model: Optional[str] = None) -> LLMResult[T]:
        """model: thay model chinh cho lan goi nay (vi du "dich nhe" dung model re hon)."""
        s = self.settings
        attempts = 0
        err: Optional[LLMError] = None
        if not use_fallback:
            res, err, attempts = await self._try_model(messages, output_model, model or s.llm_model, attempts)
            if res is not None:
                return self._done(replace(res, attempts=attempts))
            if err is not None and (err.kind == "quota" or (err.kind == "config" and "key" in str(err).lower())):
                raise err  # het ngan sach / sai key: model du phong cung loi
        if s.llm_fallback_model:
            res, err2, attempts = await self._try_model(messages, output_model, s.llm_fallback_model, attempts)
            if res is not None:
                return self._done(replace(res, attempts=attempts, used_fallback=True))
            err = err2 or err
        raise err or LLMError("unavailable", "khong goi duoc model nao")

    @staticmethod
    def _done(res: LLMResult[T]) -> LLMResult[T]:
        log.info("llm ok model=%s tokens=%d(cache %d)+%d ms=%d cost=$%.6f attempts=%d fallback=%s mode=%s",
                 res.model, res.prompt_tokens, res.cached_tokens, res.completion_tokens, res.latency_ms, res.cost_usd,
                 res.attempts, res.used_fallback, res.mode)
        return res
