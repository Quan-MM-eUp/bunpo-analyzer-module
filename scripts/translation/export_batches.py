"""C1: dong goi kho ngu phap thanh cac lo dich (ke-hoach-dich-kho-ngu-phap.md, muc 3, 6).

    python scripts/translation/export_batches.py --out "<Model bunpo>/translation"

Can module bunpo_analyzer (dung grammar_detail() de lay ban da lam sach). Ghi:
    source/items.json        moi mau 1 muc (de tra cuu, dich bu)
    source/bNNN.json         cac lo, ~20 nghin ky tu nguon / lo, N5 -> N1
    source/index.json        danh sach lo + so mau + so ky tu + ma bam

Mot muc (mau ngu phap) gom:
    id, level, src_hash
    context: ten mau, pattern, 接続 goc, cau vi du tieng Nhat  (de hieu dung ngu phap)
    fields:  cac truong can dich; moi truong ghi nguon ("vi" hoac "ja") va cach dich
             - name / connection: "vi_parts" = chi dich phan chu Viet, giu chu Nhat va ky hieu
             - examples: dich tu cau Nhat (ban Viet chi tham khao)
             - comparison: dich chu trong o (o chi co chu Nhat / ky hieu thi giu nguyen)
Bo 130 mau phu da gom ve mau chuan (tables/grammar_canon.json).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KANA, KANJI, LATIN, has_vi, is_ja_only, src_hash, write_json

from bunpo_analyzer.config import get_settings
from bunpo_analyzer.core.canon import canon_id
from bunpo_analyzer.core.data import get_kho
from bunpo_analyzer.core.grammar_detail import (
    examples_clean,
    grammar_detail,
)

LEVEL_ORDER = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}
TARGET_CHARS = 20000
MAX_ITEMS = 40


# Truong bi dan nham cau vi du (vd meaning = "*① ...\n#####\n② ..."): loi kho, khong dich
JUNK = re.compile(r"#####|^\s*\*①")
DATA_ISSUES: list[dict] = []


def _text_field(text, mode="full", where=""):
    if not text or not text.strip():
        return None
    if JUNK.search(text):
        DATA_ISSUES.append({"where": where, "issue": "truong chua cau vi du / ##### (loi kho)", "text": text[:120]})
        return None
    if not has_vi(text) and len(LATIN.findall(text)) > 2 * (len(KANA.findall(text)) + len(KANJI.findall(text))) \
            and len(LATIN.findall(text)) >= 20:
        return {"src": "en", "text": text}  # kho ghi bang tieng Anh
    if is_ja_only(text):
        return {"src": "ja", "text": text}
    if not has_vi(text):
        return None  # chi ky hieu / chu Latin khong phai tieng Viet: giu nguyen
    return {"src": "vi", "text": text, **({"mode": mode} if mode != "full" else {})}


def build_item(g, kho) -> dict | None:
    d = grammar_detail(g.id, "vi", kho)
    raw = g.raw
    fields: dict = {}
    f = _text_field(g.name, "vi_parts", f"#{g.id}.name")
    if f and f["src"] == "vi":
        fields["name"] = f
    f = _text_field(d.meaning, where=f"#{g.id}.meaning")
    if f:
        fields["meaning"] = f
    conn = raw.get("接続") or ""
    if has_vi(conn):
        fields["connection"] = {"src": "vi", "text": conn, "mode": "vi_parts"}
    exs = examples_clean(raw.get("examples"))
    if exs:
        fields["examples"] = [{"jp": e.jp, "vi": e.vi} for e in exs]
    for key, val in (("explain", d.explain), ("notes", d.notes)):
        f = _text_field(val, where=f"#{g.id}.{key}")
        if f:
            fields[key] = f
    if d.mistakes:
        fields["mistakes"] = [{"src": "ja" if is_ja_only(m) else "vi", "text": m} for m in d.mistakes]
    if d.comparison and (any(has_vi(c) for c in d.comparison.headers)
                         or any(has_vi(c) for r in d.comparison.rows for c in r)):
        fields["comparison"] = {"headers": d.comparison.headers, "rows": d.comparison.rows}
    if not fields:
        return None
    context = {"name": g.name, "pattern": g.pattern or None, "connection": conn or None,
               "examples_jp": [e.jp for e in exs[:3]]}
    return {"id": g.id, "level": g.level, "src_hash": src_hash(fields), "context": context, "fields": fields}


def item_chars(it: dict) -> int:
    n = 0
    for k, v in it["fields"].items():
        if k == "examples":
            n += sum(len(e["jp"]) + len(e["vi"] or "") for e in v)
        elif k == "mistakes":
            n += sum(len(m["text"]) for m in v)
        elif k == "comparison":
            n += sum(len(c) for c in v["headers"]) + sum(len(c) for r in v["rows"] for c in r)
        else:
            n += len(v["text"])
    return n


def make_batches(items: list[dict], target: int = TARGET_CHARS, max_items: int = MAX_ITEMS) -> list[list[dict]]:
    batches, cur, size = [], [], 0
    for it in items:
        n = item_chars(it)
        if cur and (size + n > target or len(cur) >= max_items):
            batches.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        batches.append(cur)
    return batches


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="thu muc translation/")
    ap.add_argument("--target", type=int, default=TARGET_CHARS)
    a = ap.parse_args()
    out = Path(a.out)
    kho = get_kho(get_settings().data_dir)
    gs = [g for g in kho.grammars.values() if canon_id(g.id) == g.id]
    gs.sort(key=lambda g: (LEVEL_ORDER.get(g.level or "", 9), g.id))
    items = [it for it in (build_item(g, kho) for g in gs) if it]
    batches = make_batches(items, a.target)
    index = []
    for k, b in enumerate(batches, 1):
        bid = f"b{k:03d}"
        write_json(out / "source" / f"{bid}.json", {"batch": bid, "items": b})
        index.append({"batch": bid, "items": len(b), "chars": sum(item_chars(i) for i in b),
                      "levels": sorted({i["level"] for i in b}, key=lambda x: LEVEL_ORDER.get(x or "", 9)),
                      "ids": [i["id"] for i in b], "hash": src_hash([i["src_hash"] for i in b])})
    write_json(out / "source" / "items.json", {str(i["id"]): i for i in items}, indent=None)
    write_json(out / "source" / "data_issues.json", DATA_ISSUES)
    write_json(out / "source" / "index.json", {"kho_version": kho.core_version, "batches": index})
    total = sum(x["chars"] for x in index)
    print(f"{len(items)} mau, {len(batches)} lo, {total:,} ky tu nguon -> {out / 'source'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
