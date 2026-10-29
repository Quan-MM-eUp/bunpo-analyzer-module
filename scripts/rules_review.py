"""Tao file doc duyet luat (markdown) cho nguoi khong doc JSON.

    python scripts/rules_review.py src/bunpo_analyzer/rules/n5.json > docs/rules_N5.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bunpo_analyzer.core.matcher import Cond, RuleFile

POS = {"noun": "N", "verb": "V", "adj": "A", "adv": "Adv", "prt": "trợ từ", "aux": "trợ ĐT", "punct": "dấu câu"}


def _v(x) -> str:
    return "/".join(x) if isinstance(x, list) else str(x)


def cond(c: Cond) -> str:
    if c.gap is not None:
        return f"…(≤{c.gap} từ)…"
    if c.bos:
        return "‹đầu câu›"
    if c.eos:
        return "‹cuối câu›"
    parts = []
    if c.surface is not None:
        parts.append(_v(c.surface))
    if c.base is not None and c.surface is None:
        parts.append(f"{_v(c.base)}(chia)")
    if c.norm is not None:
        parts.append(f"≈{_v(c.norm)}")
    if c.pos is not None and c.surface is None and c.base is None:
        parts.append("/".join(POS.get(p, p) for p in (c.pos if isinstance(c.pos, list) else [c.pos])))
    for k in ("pos1", "pos2", "pos3", "cform", "ctype"):
        v = getattr(c, k)
        if v is not None and not (k == "pos2" and c.surface is not None):
            parts.append(_v(v))
    if c.not_ is not None:
        parts.append(f"không phải {cond(c.not_)}")
    s = " ".join(parts) or "?"
    if c.optional:
        s = f"({s})"
    if c.ctx:
        s = f"[{s}]"
    return s


def main(path: str) -> None:
    rf = RuleFile.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    print(f"# Duyệt luật: {Path(path).name}\n")
    print(f"{len(rf.rules)} luật, {len(rf.llm_only)} mẫu để LLM tự nhận diện. "
          "Ký hiệu: `[ ]` từ ngữ cảnh (không tính vào mẫu), `( )` có thể vắng, `(chia)` mọi dạng chia.\n")
    print("| ID | Mẫu | Luật | Ví dụ khớp | Ví dụ không được khớp |\n|---|---|---|---|---|")
    for r in rf.rules:
        pats = "<br>hoặc ".join(" + ".join(cond(c) for c in p) for p in r.patterns)
        print(f"| {r.id} | {r.name} | {pats} | {'<br>'.join(r.examples[:3])} | {'<br>'.join(r.not_examples[:2])} |")
    if rf.llm_only:
        print("\n## Để LLM tự nhận diện\n\n| ID | Mẫu | Lý do |\n|---|---|---|")
        for x in rf.llm_only:
            print(f"| {x.id} | {x.name} | {x.reason} |")


if __name__ == "__main__":
    main(sys.argv[1])
