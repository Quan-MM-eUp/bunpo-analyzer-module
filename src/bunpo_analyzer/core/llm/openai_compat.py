"""Nha cung cap theo chuan OpenAI (OpenAI that, hoac LLM gateway noi bo co base_url rieng).

Dung structured output (response_format json_schema, strict) giong chatbot dang lam.
Neu gateway / model khong ho tro json_schema thi tu ha xuong json_object + mo ta
khuon trong prompt, roi kiem tra lai bang pydantic.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from bunpo_analyzer.core.llm.base import LLMError, LLMResult, Message, T, estimate_cost

# 429 do het ngan sach / han muc (khac 429 qua tai tam thoi)
_QUOTA = re.compile(r"ngân sách|ngan sach|budget|quota|insufficient_quota|billing|hạn mức", re.I)


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Schema cho strict mode cua OpenAI: moi object deu additionalProperties=false
    va moi truong deu required (truong tuy chon phai cho phep null)."""
    from openai.lib._pydantic import to_strict_json_schema

    return to_strict_json_schema(model)


def is_reasoning_model(model: str) -> bool:
    m = model.lower()
    return (m.startswith(("gpt-5", "o1", "o3", "o4")) and "chat" not in m)


class OpenAICompatProvider:
    name = "openai"

    def __init__(self, api_key: str, base_url: Optional[str] = None,
                 prices: Optional[dict[str, tuple[float, float]]] = None, client: Any = None,
                 reasoning_effort: str = "low") -> None:
        if client is None:
            if not api_key:
                raise LLMError("config", "thieu BUNPO_OPENAI_API_KEY")
            from openai import AsyncOpenAI

            # Tu quan ly goi lai o LLMClient nen tat retry cua SDK.
            client = AsyncOpenAI(api_key=api_key, base_url=base_url or None, max_retries=0)
        self._client = client
        self._prices = prices or {}
        self._effort = reasoning_effort
        self._no_schema: set[str] = set()  # model da biet khong ho tro json_schema

    async def generate(self, messages: list[Message], output_model: type[T], model: str,
                       timeout_s: float, max_tokens: int) -> LLMResult[T]:
        import openai

        mode = "json_object" if model in self._no_schema else "json_schema"
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        t0 = time.perf_counter()
        try:
            resp = await self._call(msgs, output_model, model, timeout_s, max_tokens, mode)
        except openai.BadRequestError as e:
            if mode == "json_schema" and "response_format" in str(e).lower():
                self._no_schema.add(model)
                mode = "json_object"
                resp = await self._call(msgs, output_model, model, timeout_s, max_tokens, mode)
            else:
                raise LLMError("config", f"gateway tu choi yeu cau: {e}", model) from e
        latency = int((time.perf_counter() - t0) * 1000)

        choice = resp.choices[0]
        content = choice.message.content
        if getattr(choice.message, "refusal", None) or not content:
            raise LLMError("bad_output", "model tu choi hoac tra rong", model)
        if choice.finish_reason == "length":
            raise LLMError("bad_output", "het max_tokens truoc khi xong JSON", model)
        try:
            data = output_model.model_validate_json(content)
        except ValidationError as e:
            raise LLMError("bad_output", f"sai khuon: {e.error_count()} loi", model) from e
        u = getattr(resp, "usage", None)
        p_tok = getattr(u, "prompt_tokens", 0) or 0
        c_tok = getattr(u, "completion_tokens", 0) or 0
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        return LLMResult(data=data, model=getattr(resp, "model", None) or model, prompt_tokens=p_tok,
                         cached_tokens=cached, completion_tokens=c_tok, latency_ms=latency,
                         cost_usd=estimate_cost(self._prices, model, p_tok, c_tok, cached), mode=mode)

    async def _call(self, msgs: list[dict], output_model: type[BaseModel], model: str,
                    timeout_s: float, max_tokens: int, mode: str):
        import openai

        if mode == "json_schema":
            rf = {"type": "json_schema", "json_schema": {
                "name": output_model.__name__, "strict": True, "schema": strict_schema(output_model)}}
        else:
            rf = {"type": "json_object"}
            schema = json.dumps(output_model.model_json_schema(), ensure_ascii=False)
            msgs = msgs + [{"role": "system", "content": f"Chi tra ve DUY NHAT mot JSON dung schema sau:\n{schema}"}]
        if is_reasoning_model(model):
            # Dong "suy nghi": khong nhan temperature; gioi han token ten khac (tinh ca phan suy nghi).
            params = {"max_completion_tokens": max_tokens * 4, "reasoning_effort": self._effort}
        else:
            params = {"max_tokens": max_tokens, "temperature": 0}
        try:
            return await self._client.chat.completions.create(
                model=model, messages=msgs, response_format=rf, timeout=timeout_s, **params)
        except openai.APITimeoutError as e:
            raise LLMError("timeout", f"qua {timeout_s}s", model) from e
        except (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError) as e:
            raise LLMError("config", str(e), model) from e
        except openai.BadRequestError:
            raise
        except openai.RateLimitError as e:
            # 429 vi het ngan sach / han muc (gateway: "het ngan sach tong cua thang"): goi lai vo ich
            raise LLMError("quota" if _QUOTA.search(str(e)) else "unavailable", str(e), model) from e
        except (openai.InternalServerError, openai.APIConnectionError) as e:
            raise LLMError("unavailable", str(e), model) from e
        except openai.APIStatusError as e:
            kind = "unavailable" if e.status_code >= 500 or e.status_code == 429 else "config"
            raise LLMError(kind, str(e), model) from e
