"""Thu tra nghia tu bang tu dien ngoai (Mazii) cho mot cau, khong goi LLM.

    python scripts/try_dict.py "富士山に登ったことがありますか。" --lang en
    python scripts/try_dict.py "..." --lang vi --provider kho      # so voi kho word_lib

Can BUNPO_MAZII_PEM_PATH (hoac BUNPO_MAZII_PEM) trong .env va may goi duoc mazii.net.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core import cache as C
from bunpo_analyzer.core.data import get_kho
from bunpo_analyzer.core.dictionary import MaziiDictionary
from bunpo_analyzer.core.lookup import lookup, lookup_dict
from bunpo_analyzer.core.tokenizer import tokenize


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--provider", default="mazii", choices=("mazii", "kho"))
    a = ap.parse_args()
    s = Settings()
    toks = tokenize(a.text)
    t0 = time.perf_counter()
    if a.provider == "kho":
        lk = lookup(toks, get_kho(s.data_dir), a.lang)
    else:
        d = MaziiDictionary.from_settings(s, cache=C.MemoryCache())
        lk = await lookup_dict(toks, d, a.lang)
        await d.aclose()
    ms = (time.perf_counter() - t0) * 1000
    for w in lk.words:
        t = toks[w.i]
        if t.pos == "punct":
            continue
        extra = " ".join(x for x in (w.level, w.han) if x)
        print(f"{t.surface:<8} {t.base:<8} {t.pos:<5} {w.meaning_source:<14} {w.meaning or '-'}  {extra}")
    print(f"-- {ms:.0f} ms, tu dien: {lk.stats or '-'}, khong tra duoc: {lk.misses or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
