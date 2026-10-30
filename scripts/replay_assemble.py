"""Ghep lai AnalysisResult (buoc 2.5) tu mot file runs/prompt_*.json da chay - khong goi LLM.

    python scripts/replay_assemble.py runs/prompt_xxx_golden.json [G02 ...]

In moi cau: dung khuon hay khong, so node, cac mau ngu phap, tu chua co nghia.
Dua them ma cau (G02...) de in toan bo JSON cua cau do.
"""

from __future__ import annotations

import json
import sys

from bunpo_analyzer.config import get_settings
from bunpo_analyzer.core.assemble import assemble
from bunpo_analyzer.core.data import get_kho
from bunpo_analyzer.core.grammar_check import build_input_check
from bunpo_analyzer.core.llm_output import LLMOutput
from bunpo_analyzer.core.pipeline import StageResult, prepare
from bunpo_analyzer.core.validator import validate
from bunpo_analyzer.schema import AnalysisResult


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    kho = get_kho(get_settings().data_dir)
    show = set(sys.argv[2:])
    ok = tot = 0
    for rec in json.load(open(sys.argv[1], encoding="utf-8")):
        if not rec.get("output"):
            continue
        tot += 1
        lang = rec.get("lang") or "vi"
        p = prepare(rec["text"], lang, kho)
        if [t.surface for t in p.tokens] != rec.get("tokens"):
            print(rec["id"], "BO QUA: tach tu da doi so voi luc chay")
            continue
        rep = validate(LLMOutput.model_validate(rec["output"]), p.tokens, p.matches, p.input.text)
        if not rep.ok:
            print(rec["id"], "LOI KHUON (luc chay that se goi lai model du phong):", rep.errors[:2])
            continue
        status = "grammar_error" if rep.output.input_check.status == "error" else "ok"
        ic, _ = build_input_check(rep.output.input_check, p.input.text, p.tokens)
        r, notes = assemble(p, StageResult(status, output=rep.output, input_check=ic), kho, lang)
        AnalysisResult.model_validate_json(r.model_dump_json())
        ok += 1
        no_meaning = [t.surface for t in r.tokens if t.pos != "punct" and not t.meaning]
        print(rec["id"], "OK |", len(r.nodes), "node |", [(g.id, g.short_label) for g in r.grammar],
              "| chua co nghia:", no_meaning or "-", "| sua:", notes or "-")
        if rec["id"] in show:
            print(json.dumps(r.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=1))
    print(f"\nDUNG KHUON: {ok}/{tot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
