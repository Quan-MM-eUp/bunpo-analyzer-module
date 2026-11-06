"""C2: chuan hoa bang thuat ngu + bang tro tu sau buoc soan / duyet.

    python finalize_glossary.py --ws <translation/> [--langs en,ko]

Doc glossary/<lang>.json (ban duyet, dang {"terms": {id: {tr, accept, note}}}) + glossary/_source.json,
ghi lai glossary/<lang>.json dang check.py dung: {"lang", "version", "terms": [{id, cat, vi, ja, tr, accept, note, check}]}.
Kiem tra particles/<lang>.json (du khoa, khong sot chu Viet, giu chu Nhat / ～ / ngoac).
In bao cao; ma thoat 1 neu co loi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import check_text
from common import LANGS, VI_ONLY, read_json, workspace, write_json


def finalize_glossary(ws: Path, lang: str) -> tuple[list[str], int]:
    src = read_json(ws / "glossary" / "_source.json")["terms"]
    p = ws / "glossary" / f"{lang}.json"
    if not p.exists():
        return [f"{lang}: thieu glossary/{lang}.json"], 0
    data = read_json(p)
    terms = data.get("terms")
    if isinstance(terms, list):  # da chuan hoa
        terms = {t["id"]: t for t in terms}
    errs, out = [], []
    for s in src:
        t = (terms or {}).get(s["id"])
        if not t or not str(t.get("tr", "")).strip():
            errs.append(f"{lang}: thieu thuat ngu {s['id']}")
            continue
        tr = str(t["tr"]).strip()
        if VI_ONLY.search(tr):
            errs.append(f"{lang}: {s['id']} con chu Viet: {tr}")
        acc = [a for a in (t.get("accept") or []) if isinstance(a, str) and a.strip() and a != tr]
        out.append({"id": s["id"], "cat": s["cat"], "vi": s["vi"], "ja": s["ja"], "tr": tr, "accept": acc,
                    "note": t.get("note") or "", "check": s["check"]})
    extra = set(terms or {}) - {s["id"] for s in src}
    if extra:
        errs.append(f"{lang}: thuat ngu la {sorted(extra)}")
    if not errs:
        write_json(p, {"lang": lang, "version": "1", "terms": out})
    return errs, len(out)


def check_particles(ws: Path, lang: str) -> tuple[list[str], list[str], int]:
    src = read_json(ws / "source" / "particle_table.json")["entries"]
    p = ws / "particles" / f"{lang}.json"
    if not p.exists():
        return [f"{lang}: thieu particles/{lang}.json"], [], 0
    tr = read_json(p)
    errs, warns = [], []
    for e in src:
        t = tr.get(e["key"])
        e2, w2 = check_text(e["vi"], t, lang, "vi", f"{lang}.particle[{e['key']}]", [])
        errs += e2
        warns += [w for w in w2 if "do dai" not in w]
        if isinstance(t, str) and len(t) > max(3 * len(e["vi"]), len(e["vi"]) + 40):
            warns.append(f"{lang}.particle[{e['key']}]: qua dai ({len(e['vi'])} -> {len(t)})")
    extra = set(tr) - {e["key"] for e in src}
    if extra:
        errs.append(f"{lang}: khoa la {sorted(extra)[:5]}")
    return errs, warns, len(tr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws")
    ap.add_argument("--langs", default=",".join(LANGS))
    a = ap.parse_args(argv)
    ws = workspace(a.ws)
    bad = False
    for lang in [x for x in a.langs.split(",") if x]:
        ge, n = finalize_glossary(ws, lang)
        pe, pw, m = check_particles(ws, lang)
        style = (ws / "style" / f"{lang}.md").exists()
        print(f"{lang}: {n} thuat ngu, {m} tro tu, style={'co' if style else 'THIEU'}, "
              f"{len(ge) + len(pe)} loi, {len(pw)} canh bao")
        for x in (ge + pe)[:15]:
            print("   x", x)
        for x in pw[:8]:
            print("   !", x)
        bad |= bool(ge or pe or not style)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
