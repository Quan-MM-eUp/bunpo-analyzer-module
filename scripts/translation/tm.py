"""Quan ly tien do dich: manifest/<lang>.csv + locks/<lang>.lock (ke-hoach-dich-kho-ngu-phap.md, muc 6).

    python tm.py [--ws DIR] init                       tao / cap nhat manifest 15 ngon ngu tu source/index.json
    python tm.py [--ws DIR] status [lang]              bang tien do
    python tm.py [--ws DIR] claim <lang> --who ID      nhan khoa (gia han neu dang giu)
    python tm.py [--ws DIR] claim --auto --who ID      tu chon ngon ngu ke tiep con viec + chua ai giu, in ra ma
    python tm.py [--ws DIR] release <lang> --who ID    tra khoa (ghi de trang thai, khong xoa file)
    python tm.py [--ws DIR] next <lang> [--n 20]       cac lo can lam tiep (pending, failed con luot)
    python tm.py [--ws DIR] mark <lang> b001 b002 --status passed [--score 95] [--qa-low 1] [--note ...]
    python tm.py [--ws DIR] apply-report <report.json> --who ID   cap nhat manifest tu bao cao qa.py

Chi dung thu vien chuan. Thu muc mac dinh: BUNPO_TRANSLATION_DIR hoac <BUNPO_DATA_DIR>/translation.
Ma thoat: 0 ok, 2 khoa dang bi cuoc khac giu / khong con ngon ngu nao, 1 loi khac.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    LANGS,
    LOCK_STALE_S,
    STATUSES,
    read_json,
    workspace,
    write_json,
    write_text,
)

COLS = ["batch", "status", "items", "chars", "src_hash", "attempts", "score", "qa_low", "who", "updated", "note"]
MAX_ATTEMPTS = 3
TODO = ("pending", "failed")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------- manifest ----------------
def manifest_path(ws: Path, lang: str) -> Path:
    return ws / "manifest" / f"{lang}.csv"


def load_manifest(ws: Path, lang: str) -> list[dict]:
    p = manifest_path(ws, lang)
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def save_manifest(ws: Path, lang: str, rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in COLS})
    write_text(manifest_path(ws, lang), buf.getvalue())


def init_manifests(ws: Path, langs: list[str]) -> dict[str, dict]:
    """Tao manifest; neu da co thi giu trang thai lo co ma bam khong doi, lo doi nguon -> pending."""
    index = read_json(ws / "source" / "index.json")
    out = {}
    for lang in langs:
        old = {r["batch"]: r for r in load_manifest(ws, lang)}
        rows, changed = [], 0
        for b in index["batches"]:
            r = old.get(b["batch"])
            base = {"batch": b["batch"], "items": b["items"], "chars": b["chars"], "src_hash": b["hash"]}
            if r and r.get("src_hash") == b["hash"]:
                rows.append({**r, **base})
            else:
                if r:
                    changed += 1
                rows.append({**base, "status": "pending", "attempts": 0, "updated": now_iso(),
                             "note": "nguon doi" if r else ""})
        save_manifest(ws, lang, rows)
        out[lang] = {"batches": len(rows), "changed": changed}
    return out


def todo(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["status"] == "pending"
            or (r["status"] == "failed" and int(r.get("attempts") or 0) < MAX_ATTEMPTS)]


def counts(rows: list[dict]) -> dict[str, int]:
    c = {s: 0 for s in STATUSES}
    for r in rows:
        c[r["status"]] = c.get(r["status"], 0) + 1
    return c


# ---------------- khoa ----------------
def lock_path(ws: Path, lang: str) -> Path:
    return ws / "locks" / f"{lang}.lock"


def read_lock(ws: Path, lang: str) -> dict | None:
    p = lock_path(ws, lang)
    if not p.exists():
        return None
    try:
        return read_json(p)
    except (OSError, ValueError):
        return None


def lock_holder(ws: Path, lang: str, now: float | None = None) -> str | None:
    """Ai dang giu khoa con hieu luc (None neu tu do / da tra / qua han)."""
    lk = read_lock(ws, lang)
    if not lk or lk.get("state") != "held":
        return None
    if (now or time.time()) - float(lk.get("ts", 0)) > LOCK_STALE_S:
        return None
    return lk.get("who")


def claim(ws: Path, lang: str, who: str) -> bool:
    h = lock_holder(ws, lang)
    if h and h != who:
        return False
    old = read_lock(ws, lang) or {}
    since = old.get("since") if old.get("who") == who and old.get("state") == "held" else now_iso()
    write_json(lock_path(ws, lang), {"lang": lang, "who": who, "state": "held", "since": since,
                                     "heartbeat": now_iso(), "ts": time.time()})
    return True


def release(ws: Path, lang: str, who: str) -> bool:
    h = lock_holder(ws, lang)
    if h and h != who:
        return False
    write_json(lock_path(ws, lang), {"lang": lang, "who": who, "state": "released", "released": now_iso(),
                                     "ts": time.time()})
    return True


def auto_pick(ws: Path, who: str) -> str | None:
    """Ngon ngu dang do giu boi chinh minh truoc, roi ngon ngu dau tien theo thu tu nhom con viec + khoa tu do."""
    for lang in LANGS:
        if lock_holder(ws, lang) == who and todo(load_manifest(ws, lang)):
            return lang
    for lang in LANGS:
        if todo(load_manifest(ws, lang)) and lock_holder(ws, lang) is None:
            return lang
    return None


def mark(ws: Path, lang: str, batches: list[str], status: str, who: str = "", score: str = "",
         qa_low: str = "", note: str = "") -> list[str]:
    if status not in STATUSES:
        raise ValueError(f"status phai la mot trong {STATUSES}")
    rows = load_manifest(ws, lang)
    want, done = set(batches), []
    for r in rows:
        if r["batch"] in want:
            r["status"] = status
            if status == "failed":
                r["attempts"] = int(r.get("attempts") or 0) + 1
            elif status == "pending":
                r["attempts"] = 0
            for k, v in (("score", score), ("qa_low", qa_low), ("note", note), ("who", who)):
                if v != "":
                    r[k] = v
            r["updated"] = now_iso()
            done.append(r["batch"])
    save_manifest(ws, lang, rows)
    return done


def apply_report(ws: Path, report: dict, who: str = "") -> list[str]:
    lang = report["lang"]
    out = []
    for r in report["batches"]:
        note = "; ".join(r.get("errors") or [])[:200]
        mark(ws, lang, [r["batch"]], r["status"], who=who, score=str(r.get("score") if r.get("score") is not None else ""),
             qa_low=str(r.get("qa_low", "")), note=note)
        out.append(f"{r['batch']}:{r['status']}")
    return out


# ---------------- CLI ----------------
def _status_table(ws: Path, langs: list[str]) -> str:
    lines = [f"{'lang':5} {'lo':>4} " + " ".join(f"{s:>10}" for s in STATUSES) + "  khoa"]
    for lang in langs:
        rows = load_manifest(ws, lang)
        if not rows:
            continue
        c = counts(rows)
        h = lock_holder(ws, lang)
        lines.append(f"{lang:5} {len(rows):>4} " + " ".join(f"{c[s]:>10}" for s in STATUSES) + f"  {h or '-'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws", help="thu muc translation/")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--langs", default=",".join(LANGS))
    p = sub.add_parser("status"); p.add_argument("lang", nargs="?")
    p = sub.add_parser("claim"); p.add_argument("lang", nargs="?"); p.add_argument("--who", required=True)
    p.add_argument("--auto", action="store_true")
    p = sub.add_parser("release"); p.add_argument("lang"); p.add_argument("--who", required=True)
    p = sub.add_parser("next"); p.add_argument("lang"); p.add_argument("--n", type=int, default=20)
    p = sub.add_parser("mark"); p.add_argument("lang"); p.add_argument("batches", nargs="+")
    p.add_argument("--status", required=True); p.add_argument("--who", default="")
    p.add_argument("--score", default=""); p.add_argument("--qa-low", default=""); p.add_argument("--note", default="")
    p = sub.add_parser("apply-report"); p.add_argument("report"); p.add_argument("--who", default="")
    a = ap.parse_args(argv)
    ws = workspace(a.ws)

    if a.cmd == "init":
        langs = [l for l in a.langs.split(",") if l]
        bad = [l for l in langs if l not in LANGS]
        if bad:
            print(f"ngon ngu khong hop le: {bad}"); return 1
        for lang, info in init_manifests(ws, langs).items():
            print(f"{lang}: {info['batches']} lo" + (f", {info['changed']} lo doi nguon -> pending" if info["changed"] else ""))
        return 0
    if a.cmd == "status":
        print(_status_table(ws, [a.lang] if a.lang else LANGS)); return 0
    if a.cmd == "claim":
        if a.auto or not a.lang:
            lang = auto_pick(ws, a.who)
            if not lang:
                print("NONE"); return 2
        else:
            lang = a.lang
        if not claim(ws, lang, a.who):
            print(f"BUSY {lang} {lock_holder(ws, lang)}"); return 2
        print(lang); return 0
    if a.cmd == "release":
        ok = release(ws, a.lang, a.who)
        print("released" if ok else f"BUSY {lock_holder(ws, a.lang)}"); return 0 if ok else 2
    if a.cmd == "next":
        print(" ".join(r["batch"] for r in todo(load_manifest(ws, a.lang))[: a.n])); return 0
    if a.cmd == "apply-report":
        rep = read_json(Path(a.report))
        print(" ".join(apply_report(ws, rep, a.who)))
        print(_status_table(ws, [rep["lang"]]))
        return 0
    if a.cmd == "mark":
        done = mark(ws, a.lang, a.batches, a.status, a.who, a.score, a.qa_low, a.note)
        miss = sorted(set(a.batches) - set(done))
        print(f"{len(done)} lo -> {a.status}" + (f"; khong co: {miss}" if miss else "")); return 0 if not miss else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
