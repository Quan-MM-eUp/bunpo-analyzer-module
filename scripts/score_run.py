"""Cham mot file ket qua cua try_prompt.py so voi dap an trong bo cau kiem thu.

    python scripts/score_run.py runs/prompt_xxx_golden.json

Moi cau co dap an day du: ti le dong dung (vai tro + chu), nhom dung (loai + chu),
mau bat buoc tim thay, mau gan du, loi phu token. Mau trung nhau trong cung nhom
ung vien (cung vi tri) duoc tinh la dung.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bunpo_analyzer.core.matcher import get_matcher
from bunpo_analyzer.core.tokenizer import tokenize
from bunpo_analyzer.evaluation import score_structure

ROOT = Path(__file__).resolve().parents[1]


def score(rec, gold) -> dict:
    toks = tokenize(rec["text"])
    return score_structure(rec["text"], [t.surface for t in toks], rec["output"]["nodes"], gold,
                           get_matcher().match(toks))


def main(path: str) -> None:
    run = json.loads(Path(path).read_text(encoding="utf-8"))
    golden = {it["text"]: it for it in json.loads((ROOT / "tests" / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]}
    tot = {"rows": [0, 0, 0], "groups": [0, 0, 0], "must": [0, 0], "cov": 0, "n": 0, "extra": 0}
    checks = []
    for rec in run:
        g = golden.get(rec["text"])
        if g and g["case"] in ("#9", "#10") and "input_check" in rec:
            want = g["expect"]["input_check"]
            want = want if isinstance(want, list) else [want]
            ic = rec["input_check"]
            ok = ic["status"] in want
            if ok and g["expect"].get("correction"):
                ok = ic["correction"] == g["expect"]["correction"] and ic.get("correction_at") is not None
            checks.append(ok)
            c0, c1 = ic.get("correction_at") or (0, 0)
            corr = ic.get("correction") or ""
            print(f"{g['id']} {rec['text']} | can: {'/'.join(want)} | ra: {ic['status']} | {'DUNG' if ok else 'SAI'}"
                  + (f" | sua: {corr[:c0]}【{corr[c0:c1]}】{corr[c1:]}" if corr else ""))
            continue
        if not g or "full" not in g["tags"] or "output" not in rec:
            continue
        s = score(rec, g)
        tot["n"] += 1
        for k in ("rows", "groups"):
            for i in range(3):
                tot[k][i] += s[k][i]
        tot["must"][0] += s["must"][0]
        tot["must"][1] += s["must"][1]
        tot["cov"] += s["coverage_ok"]
        tot["extra"] += len(s["extra"])
        print(f"{g['id']} {rec['text']}\n   dong {s['rows'][0]}/{s['rows'][1]} (ra {s['rows'][2]}) | nhom {s['groups'][0]}/{s['groups'][1]} "
              f"(ra {s['groups'][2]}) | mau {s['must'][0]}/{s['must'][1]} | du {s['extra']} | phu token {'OK' if s['coverage_ok'] else 'LOI'}")
        if s["missing_rows"] or s["wrong_rows"]:
            print(f"   thieu {s['missing_rows']}\n   sai   {s['wrong_rows']}")
        if s["missing_groups"] or s["wrong_groups"]:
            print(f"   nhom thieu {s['missing_groups']} | nhom sai {s['wrong_groups']}")
    if checks:
        print(f"\nKIEM TRA CAU: dung {sum(checks)}/{len(checks)}")
    if tot["n"]:
        r, gr, m = tot["rows"], tot["groups"], tot["must"]
        print(f"\nTONG {tot['n']} cau: dong dung {r[0]}/{r[1]} ({r[0] / max(1, r[1]):.0%}), "
              f"nhom dung {gr[0]}/{gr[1]} ({gr[0] / max(1, gr[1]):.0%}), mau bat buoc {m[0]}/{m[1]} ({m[0] / max(1, m[1]):.0%}), "
              f"mau du {tot['extra']}, phu token dung {tot['cov']}/{tot['n']}")


if __name__ == "__main__":
    main(sys.argv[1])
