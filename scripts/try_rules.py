"""Thu mot file luat: kiem tra examples, do do phu tren cau vi du trong kho.

    python scripts/try_rules.py src/bunpo_analyzer/rules/n5.json [--data "../"] [--ids 169,245]
    python scripts/try_rules.py --show "先生に言われたとおりに練習したら"

In ra moi luat:
  ex     : so examples khop / tong (phai bang tong)
  not    : so not_examples bi khop nham (phai = 0)
  recall : ti le cau vi du CUA CHINH MAU NAY trong grammar_lib duoc bat (cang cao cang tot)
  broad  : ti le 1.500 cau vi du ngau nhien trong kho bi bat (qua cao = luat qua rong)
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from bunpo_analyzer.core.input_check import normalize
from bunpo_analyzer.core.matcher import GrammarMatcher, RuleFile
from bunpo_analyzer.core.tokenizer import tokenize

JP = re.compile(r"[぀-ヿ一-鿿]")
LATIN = re.compile(r"[a-zA-Zà-ỹĐđ]{3,}")


def sentences(text: str) -> list[str]:
    out = []
    for line in str(text or "").split("\n"):
        line = re.sub(r"^\s*(\d+[\.\)]|[①-⑳]|[A-ZＡ-Ｚ][:：]|→)\s*", "", line.strip())
        line = re.sub(r"^[A-ZＡ-Ｚ][:：「]?", "", line)
        for part in re.split(r"(?<=[。！？])", line):
            part = part.strip(" 「」")
            if len(part) >= 3 and JP.search(part) and not LATIN.search(part):
                out.append(normalize(part))
    return out


def show(text: str) -> None:
    for t in tokenize(normalize(text)):
        print(f"{t.i:>2} {t.surface:<8} base={t.base:<8} pos={t.pos:<5} detail={'/'.join(t.pos_detail):<20} cform={t.cform or '-'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--data", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--ids", default="")
    ap.add_argument("--show")
    a = ap.parse_args()
    if a.show:
        show(a.show)
        return 0
    rf = RuleFile.model_validate(json.loads(Path(a.file).read_text(encoding="utf-8")))
    only = {int(x) for x in a.ids.split(",") if x}
    gl = json.loads((Path(a.data) / "grammar" / "grammar_lib.json").read_text(encoding="utf-8"))
    own = {int(g["id"]): sentences(g.get("examples")) for g in gl}
    pool = [s for g in gl for s in sentences(g.get("examples"))]
    random.seed(7)
    sample = [tokenize(s) for s in random.sample(pool, min(1500, len(pool)))]
    bad = 0
    for r in rf.rules:
        if only and r.id not in only:
            continue
        m = GrammarMatcher([r])
        ex_ok = sum(r.id in m.candidate_ids(tokenize(normalize(e))) for e in r.examples)
        not_bad = [e for e in r.not_examples if r.id in m.candidate_ids(tokenize(normalize(e)))]
        mine = own.get(r.id, [])
        rec = sum(bool(m.match(tokenize(s))) for s in mine) / len(mine) if mine else float("nan")
        broad = sum(bool(m.match(t)) for t in sample) / len(sample)
        flag = []
        if ex_ok < len(r.examples):
            flag.append("EX-MISS")
        if not_bad:
            flag.append("NOT-HIT")
        if mine and rec < 0.6:
            flag.append("RECALL-LOW")
        if broad > 0.3:
            flag.append("BROAD")
        bad += bool(flag)
        print(f"{r.id:>5} {r.name[:22]:<22} ex {ex_ok}/{len(r.examples)} not {len(not_bad)} "
              f"recall {rec:.2f} ({len(mine)}) broad {broad:.2f} {' '.join(flag)}")
        if mine and rec < 0.6:
            for s in mine:
                if not m.match(tokenize(s)):
                    print("        miss:", s[:60])
    print(f"llm_only: {len(rf.llm_only)}; luat co canh bao: {bad}/{len(rf.rules)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
