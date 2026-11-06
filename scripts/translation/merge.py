"""Gop out/<lang>/*.json thanh grammar_text.<lang>.json (ke-hoach-dich-kho-ngu-phap.md, muc 8).

    python merge.py [--ws DIR] <lang> [--dest FILE] [--include translated]

Mac dinh chi lay lo co trang thai passed / qa_low trong manifest, ghi ra
<ws>/merged/grammar_text.<lang>.json (buoc C6 moi chep vao kho grammar/).
Truong null / []: nguon rong hoac khong can dich -> giao dien dung ban goc.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LANGS, read_json, workspace, write_json
from tm import load_manifest

OK_STATUSES = ("passed", "qa_low")
KEYS = ("name", "meaning", "connection", "examples", "explain", "comparison", "mistakes", "notes")


def merge_item(si: dict, ti: dict, batch_meta: dict) -> dict:
    tf = ti.get("fields") or {}
    sf = si["fields"]
    rec: dict = {k: None for k in KEYS}
    rec["examples"], rec["mistakes"] = [], []
    for k in ("name", "meaning", "connection", "explain", "notes"):
        if k in sf:
            rec[k] = tf.get(k)
    if "examples" in sf:
        rec["examples"] = [{"jp": ex["jp"], "tr": tr} for ex, tr in zip(sf["examples"], tf.get("examples") or [])]
    if "mistakes" in sf:
        rec["mistakes"] = list(tf.get("mistakes") or [])
    if "comparison" in sf:
        rec["comparison"] = tf.get("comparison")
    q = ti.get("qa") or {}
    rec["_meta"] = {"src_hash": si["src_hash"], "model": batch_meta.get("model"), "judge": q.get("judge"),
                    "score": q.get("score"), "qa": q.get("qa", "unchecked"),
                    "issues": q.get("issues") or None, "prompt_ver": batch_meta.get("prompt_ver"),
                    "date": batch_meta.get("date"), "batch": batch_meta.get("batch")}
    if not rec["_meta"]["issues"]:
        del rec["_meta"]["issues"]
    return rec


def merge_lang(ws: Path, lang: str, statuses: tuple[str, ...] = OK_STATUSES) -> tuple[dict, dict]:
    rows = load_manifest(ws, lang)
    take = [r["batch"] for r in rows if r["status"] in statuses]
    out: dict = {}
    stats = {"batches": len(take), "of": len(rows), "items": 0, "qa_low": 0, "stale": 0}
    for b in take:
        p = ws / "out" / lang / f"{b}.json"
        if not p.exists():
            continue
        src = {si["id"]: si for si in read_json(ws / "source" / f"{b}.json")["items"]}
        data = read_json(p)
        meta = {k: data.get(k) for k in ("model", "prompt_ver", "date", "batch")}
        for ti in data.get("items") or []:
            si = src.get(int(ti["id"]))
            if si is None:
                continue
            if ti.get("src_hash") != si["src_hash"]:
                stats["stale"] += 1
                continue
            rec = merge_item(si, ti, meta)
            out[str(si["id"])] = rec
            stats["items"] += 1
            stats["qa_low"] += rec["_meta"]["qa"] == "low"
    out = dict(sorted(out.items(), key=lambda kv: int(kv[0])))
    return out, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws")
    ap.add_argument("lang", choices=LANGS)
    ap.add_argument("--dest")
    ap.add_argument("--include", default="", help="them trang thai, vd: translated")
    a = ap.parse_args(argv)
    ws = workspace(a.ws)
    sts = OK_STATUSES + tuple(s for s in a.include.split(",") if s)
    data, st = merge_lang(ws, a.lang, sts)
    dest = Path(a.dest) if a.dest else ws / "merged" / f"grammar_text.{a.lang}.json"
    write_json(dest, data, indent=None)
    print(f"{a.lang}: {st['items']} mau tu {st['batches']}/{st['of']} lo, qa thap {st['qa_low']}, "
          f"bo qua (nguon doi) {st['stale']} -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
