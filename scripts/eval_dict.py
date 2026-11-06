"""D4: danh gia tra nghia tu bang Mazii (du lieu mau D0, khong goi mang) so voi kho word_lib.

    python scripts/eval_dict.py [--out docs/mazii_eval.md]

Voi moi cau (bo cau kiem thu + cau bo sung cua mazii_capture.py) va moi ngon ngu da ghi:
- ti le tu noi dung co nghia tu tu dien / phai nho LLM / lay tu bang tro tu;
- tieng Viet: so voi word_lib (cung muc tu? kho co ma Mazii khong?);
- bang tung tu de duyet tay: muc tu duoc chon, cach doc, cap JLPT, nghia vi + en.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from collections import Counter
from pathlib import Path

from bunpo_analyzer.core.data import Kho
from bunpo_analyzer.core.dictionary import StaticDictionary
from bunpo_analyzer.core.lookup import _CONTENT, lookup, lookup_dict
from bunpo_analyzer.core.tokenizer import tokenize

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "mazii"
LANGS = ("vi", "en", "tw", "cn", "ko")


def _sentences() -> list[str]:
    spec = importlib.util.spec_from_file_location("cap", ROOT / "scripts" / "mazii_capture.py")
    cap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cap)
    return cap.sentences()


async def run(out: Path) -> None:
    d = StaticDictionary.from_dir(FIX)
    kho_dir = Path(os.environ.get("BUNPO_DATA_DIR", ROOT.parent))
    kho = Kho(kho_dir) if (kho_dir / "word" / "word_lib.json").exists() else None
    sents = _sentences()
    stats = {lang: Counter() for lang in LANGS}
    cmp = Counter()
    rows: list[str] = []
    for text in sents:
        toks = tokenize(text)
        res = {lang: await lookup_dict(toks, d, lang) for lang in LANGS}
        kres = lookup(toks, kho, "vi") if kho else None
        for lang, lk in res.items():
            for w in lk.words:
                t = toks[w.i]
                if t.pos not in _CONTENT or w.via == "number":
                    continue
                stats[lang]["content"] += 1
                stats[lang][w.meaning_source] += 1
        vi, en = res["vi"].words, res["en"].words
        for k, t in enumerate(toks):
            if t.pos not in _CONTENT:
                continue
            wv, we = vi[k], en[k]
            kw = kres.words[k] if kres else None
            if kw is not None:
                a, b = wv.meaning_source == "dict", kw.meaning_source == "word_lib"
                cmp["ca hai" if a and b else "chi Mazii" if a else "chi kho" if b else "khong ben nao"] += 1
            if wv.meaning_source in ("dict", "llm"):
                rows.append(f"| {t.surface} | {t.base} | {t.pos} | {wv.via or '-'} | {wv.level or ''} | "
                            f"{(wv.meaning or '—')[:60]} | {(we.meaning or '—')[:60]} | "
                            f"{(kw.meaning if kw and kw.meaning_source == 'word_lib' else '')[:40]} |")
    lines = ["# Đánh giá tra nghĩa từ bằng Mazii (D4)", "",
             f"{len(sents)} câu (bộ câu kiểm thử + câu bổ sung), dữ liệu mẫu D0. Chỉ tính từ nội dung (danh, động, tính, phó từ).",
             "", "| Ngôn ngữ | Từ nội dung | Có nghĩa từ Mazii | Bảng trợ từ | Nhờ LLM |", "|---|---|---|---|---|"]
    for lang in LANGS:
        s = stats[lang]
        n = s["content"] or 1
        lines.append(f"| {lang} | {s['content']} | {s['dict']} ({s['dict'] / n:.0%}) | {s['particle_table']} | "
                     f"{s['llm']} ({s['llm'] / n:.0%}) |")
    if cmp:
        lines += ["", "So với kho word_lib (tiếng Việt): " + ", ".join(f"{k} {v}" for k, v in cmp.items()), ""]
    lines += ["## Từng từ (vi / en, so với word_lib)", "",
              "| Mặt chữ | Dạng gốc | Từ loại | Cách khớp | JLPT | Nghĩa vi (Mazii) | Nghĩa en (Mazii) | word_lib |",
              "|---|---|---|---|---|---|---|---|", *rows]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"-> {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "mazii_eval.md"))
    a = ap.parse_args()
    asyncio.run(run(Path(a.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
