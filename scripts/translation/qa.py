"""Ghi ket qua cham (tang 2) vao file dich + kiem tra tang 1 lan cuoi + bao cao dot.

    python qa.py [--ws DIR] <lang> --results results.json [--report reports/<lang>/<ten>.json]

results.json (do workflow tra ve): [{"batch": "b001", "judge": "<model>", "rounds": 1,
    "items": [{"id": 120, "score": 98, "qa": "ok"|"fix", "issues": [...]}], "note": "..."}]
Moi muc trong out/<lang>/<batch>.json duoc gan "qa": {judge, score, qa: ok|low, issues}.
"fix" con lai sau cac vong sua -> "low". Trang thai lo: failed (con loi tang 1 / thieu file / thieu
diem), qa_low (co muc low), passed. Bao cao .json (cho tm.py apply-report) va .md (cho nguoi doc).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import check_batch
from common import LANGS, read_json, workspace, write_json, write_text


def apply_batch(ws: Path, lang: str, res: dict) -> dict:
    batch = res["batch"]
    p = ws / "out" / lang / f"{batch}.json"
    rep = {"batch": batch, "status": "failed", "score": None, "qa_low": 0, "items": 0, "errors": [], "low_ids": []}
    if not p.exists():
        rep["errors"] = ["chua co file dich"]
        return rep
    data = read_json(p)
    judged = {int(i["id"]): i for i in res.get("items") or []}
    scores = []
    for it in data.get("items") or []:
        j = judged.get(int(it["id"]))
        if j is None:
            rep["errors"].append(f"#{it['id']}: chua duoc cham")
            continue
        ok = j.get("qa") == "ok"
        it["qa"] = {"judge": res.get("judge"), "score": j.get("score"), "qa": "ok" if ok else "low",
                    "issues": [x for x in j.get("issues") or [] if x.get("severity") != "minor"] if not ok else []}
        scores.append(float(j.get("score") or 0))
        if not ok:
            rep["low_ids"].append(int(it["id"]))
    data["qa_rounds"] = res.get("rounds")
    write_json(p, data)
    chk = check_batch(ws, lang, batch)
    rep["errors"] += chk["errors"]
    rep["warnings"] = len(chk["warnings"])
    rep["items"] = chk.get("items", 0)
    rep["qa_low"] = len(rep["low_ids"])
    rep["score"] = round(sum(scores) / len(scores), 1) if scores else None
    if rep["errors"]:
        rep["status"] = "failed"
    elif rep["qa_low"]:
        rep["status"] = "qa_low"
    else:
        rep["status"] = "passed"
    return rep


def render_md(lang: str, reps: list[dict], note: str = "") -> str:
    lines = [f"# Đợt dịch {lang}", "", note, "", "| Lô | Trạng thái | Điểm TB | Mục qa thấp | Lỗi |", "|---|---|---|---|---|"]
    for r in reps:
        lines.append(f"| {r['batch']} | {r['status']} | {r['score'] if r['score'] is not None else '-'} | "
                     f"{', '.join(map(str, r['low_ids'])) or '-'} | {'; '.join(r['errors'][:3]) or '-'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws")
    ap.add_argument("lang", choices=LANGS)
    ap.add_argument("--results", required=True)
    ap.add_argument("--report", help="duong dan bao cao .json (mac dinh reports/<lang>/last_round.json)")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    ws = workspace(a.ws)
    reps = [apply_batch(ws, a.lang, r) for r in read_json(Path(a.results))]
    rp = Path(a.report) if a.report else ws / "reports" / a.lang / "last_round.json"
    write_json(rp, {"lang": a.lang, "batches": reps})
    write_text(rp.with_suffix(".md"), render_md(a.lang, reps, a.note))
    for r in reps:
        print(f"{r['batch']} {r['status']:7} diem={r['score']} qa_low={r['qa_low']} loi={len(r['errors'])}")
    print(f"-> {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
