"""Kiem tra nhanh ket noi LLM tren may cua ban (khong in API key ra man hinh).

    python scripts/llm_smoke.py            # dung .env trong thu muc hien tai
    python scripts/llm_smoke.py --models   # them: liet ke model gateway cho phep

In ra: model nao duoc goi, che do structured output, token, do tre, chi phi uoc tinh.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

from pydantic import BaseModel

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.llm import LLMClient, LLMError, Message


class Probe(BaseModel):
    translation: str
    has_grammar_error: bool
    note: Optional[str] = None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", action="store_true")
    a = ap.parse_args()
    s = Settings()
    if not s.openai_api_key:
        print("Chua co BUNPO_OPENAI_API_KEY trong .env (chep .env.example thanh .env roi dien key).")
        return 1
    print(f"Gateway: {s.openai_base_url} | model: {s.llm_model} | du phong: {s.llm_fallback_model}")
    if a.models:
        from openai import AsyncOpenAI

        c = AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)
        try:
            ms = await c.models.list()
            names = sorted(m.id for m in ms.data)
            print(f"{len(names)} model:", ", ".join(names))
        except Exception as e:  # gateway co the khong mo /models
            print("Khong liet ke duoc model:", type(e).__name__, str(e)[:200])
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = LLMClient(settings=s)
    for text in ("今夜たくさんの宿題がある。", "映画は面白いでした。"):
        try:
            r = await client.generate([
                Message("system", "Dich cau tieng Nhat sang tieng Viet. has_grammar_error = true neu cau sai ngu phap ro rang. note: ngan gon hoac null."),
                Message("user", text),
            ], Probe)
        except LLMError as e:
            print(f"LOI ({e.kind}): {e}")
            return 2
        print(f"\n{text}\n  -> {r.data.model_dump()}\n  model={r.model} mode={r.mode} token={r.prompt_tokens}+{r.completion_tokens} "
              f"tre={r.latency_ms}ms chi_phi~${r.cost_usd} lan_goi={r.attempts} du_phong={r.used_fallback}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
