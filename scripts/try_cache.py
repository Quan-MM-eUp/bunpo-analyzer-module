"""Thu cache + "dich nhe" voi LLM that (buoc 2.6). Cache trong bo nho, chi song trong lan chay.

    python scripts/try_cache.py
    python scripts/try_cache.py --text "昨日友達と見た映画はとても面白かったです。" --langs vi vi en ko

Moi lan in: trang thai cache (miss / hit / light), model, do tre, chi phi, ban dich.
Ket qua day du luu vao runs/cache_<thoi gian>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.analyzer import analyze_full
from bunpo_analyzer.core.cache import MemoryCache

TEXTS = ["昨日友達と見た映画はとても面白かったです。", "映画は面白いでした。"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="append", help="cau can thu (lap lai duoc); mac dinh 2 cau mau")
    ap.add_argument("--langs", nargs="+", default=["vi", "vi", "en", "ko", "en"])
    a = ap.parse_args()
    s = Settings()
    if not s.openai_api_key:
        print("Thieu BUNPO_OPENAI_API_KEY trong .env")
        return 1
    cache = MemoryCache()
    out = []
    for text in a.text or TEXTS:
        print(f"\n=== {text}")
        for lang in a.langs:
            t0 = time.perf_counter()
            r = await analyze_full(text, lang, settings=s, cache=cache)
            ms = int((time.perf_counter() - t0) * 1000)
            models = [x.model for x in r.stage.attempts] if r.stage else []
            res = r.result
            ic = res.input_check
            line = res.translation or (ic.explain if ic.status == "error" else "") or (res.error.code if res.error else "")
            print(f"  [{lang}] cache={r.cache:5} | {ms:5d} ms | ${r.cost_usd:.6f} | {models or '-'} | {line}")
            if r.cache == "light":
                print("        gloss:", " / ".join(f"{n.id}:{n.gloss}" for n in res.nodes if n.gloss))
            out.append({"text": text, "lang": lang, "cache": r.cache, "ms": ms, "cost": r.cost_usd, "models": models,
                        "result": res.model_dump(mode="json", exclude_none=True)})
    Path("runs").mkdir(exist_ok=True)
    f = Path("runs") / f"cache_{time.strftime('%Y%m%d_%H%M%S')}.json"
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nDa luu {f}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
