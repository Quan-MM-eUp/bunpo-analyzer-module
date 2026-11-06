"""Bang thuat ngu rut gon cho mot lo: chi cac thuat ngu xuat hien trong lo (giam token doc cho tac tu).

    python brief.py [--ws DIR] <lang> <batch>

In moi dong: "<vi variants> → <tr>  (also: <accept>)  [note]".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LANGS, read_json, workspace


def batch_text(items: list[dict]) -> str:
    parts = []
    for it in items:
        for k, v in it["fields"].items():
            if k == "examples":
                continue  # cau vi du dich tu tieng Nhat
            parts.append(json.dumps(v, ensure_ascii=False))
    return "\n".join(parts).lower()


def terms_for(ws: Path, lang: str, batch: str) -> list[dict]:
    items = read_json(ws / "source" / f"{batch}.json")["items"]
    text = batch_text(items)
    out = []
    for t in read_json(ws / "glossary" / f"{lang}.json")["terms"]:
        if any(re.search(r"(?<![\wà-ỹđ])" + re.escape(v.lower()) + r"(?![\wà-ỹđ])", text) for v in t["vi"]):
            out.append(t)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws")
    ap.add_argument("lang", choices=LANGS)
    ap.add_argument("batch")
    a = ap.parse_args(argv)
    ws = workspace(a.ws)
    ts = terms_for(ws, a.lang, a.batch)
    print(f"# Glossary terms used in {a.batch} ({a.lang}): {len(ts)}. Vietnamese -> mandatory {a.lang} term")
    for t in ts:
        line = f"{' / '.join(t['vi'])} ({t['ja']}) → {t['tr']}"
        if t.get("accept"):
            line += f"  (also: {', '.join(t['accept'])})"
        if t.get("note"):
            line += f"  [{t['note']}]"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
