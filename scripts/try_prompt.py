"""Chay that prompt buoc 2.2 tren may co mang toi gateway, luu ket qua de doi chieu.

    python scripts/try_prompt.py                      # 3 cau cua artifact
    python scripts/try_prompt.py --golden             # 20 cau co dap an day du
    python scripts/try_prompt.py --text "雨が降っている。"
    python scripts/try_prompt.py --model gpt-4.1      # thu model khac
    python scripts/try_prompt.py --golden --model gpt-5-mini --effort minimal

Ket qua: in cay phan tich ra man hinh va ghi file runs/prompt_<thoi gian>.json
(thu muc runs/ khong bi day len GitHub).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.data import get_kho
from bunpo_analyzer.core.llm import LLMClient
from bunpo_analyzer.core.assemble import assemble
from bunpo_analyzer.core.pipeline import analyze_llm, prepare
from bunpo_analyzer.core.prompt import PROMPT_VERSION
from bunpo_analyzer.core.render import render

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ["今夜たくさんの宿題がある。", "昨日友達と見た映画はとても面白かったです。",
            "先生に言われたとおりに練習したら、上手に話せるようになった。"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", action="store_true")
    ap.add_argument("--errors", action="store_true", help="cac cau sai / nghi sai ngu phap trong bo kiem thu (buoc 2.4)")
    ap.add_argument("--text", action="append")
    ap.add_argument("--model")
    ap.add_argument("--effort", help="model suy nghi (gpt-5*): minimal | low | medium | high")
    ap.add_argument("--lang", default="vi")
    a = ap.parse_args()
    s = Settings()
    if a.model:
        s = s.model_copy(update={"llm_model": a.model})
    if a.effort:
        s = s.model_copy(update={"llm_reasoning_effort": a.effort})
    if not s.openai_api_key:
        print("Chua co BUNPO_OPENAI_API_KEY trong .env")
        return 1
    items = [{"id": f"A{i + 1}", "text": t} for i, t in enumerate(ARTIFACT)]
    if a.golden:
        gs = json.loads((ROOT / "tests" / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]
        items = [{"id": it["id"], "text": it["text"]} for it in gs if "full" in it["tags"]]
    if a.errors:
        gs = json.loads((ROOT / "tests" / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]
        items = [{"id": it["id"], "text": it["text"]} for it in gs if it["case"] in ("#9", "#10")]
    if a.text:
        items = [{"id": f"T{i + 1}", "text": t} for i, t in enumerate(a.text)]
    kho = get_kho(s.data_dir)
    client = LLMClient(settings=s)
    results = []
    out = ROOT / "runs" / f"prompt_{time.strftime('%Y%m%d_%H%M%S')}{'_golden' if a.golden else ''}{'_errors' if a.errors else ''}.json"
    out.parent.mkdir(exist_ok=True)

    def save() -> None:  # luu sau moi cau: dung giua chung van con ket qua
        out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    for it in items:
        try:
            await one(it, a, s, kho, client, results)
        except Exception as e:  # khong de mot cau loi lam mat ca lan chay
            print(f"  LOI KHONG MONG DOI: {type(e).__name__}: {e}")
            results.append({"id": it["id"], "text": it["text"], "crash": f"{type(e).__name__}: {e}"})
        save()
    ok = [r for r in results if "usage" in r]
    if ok:
        print(f"\nTong: {len(ok)}/{len(results)} cau | trung binh {sum(r['usage']['ms'] for r in ok) / len(ok):.0f} ms | "
              f"{sum(r['usage']['cost'] for r in ok):.4f} $ | da luu {out.relative_to(ROOT)}")
    return 0


async def one(it, a, s, kho, client, results) -> None:
    if True:
        p = prepare(it["text"], a.lang, kho=kho)
        print(f"\n=== {it['id']} {it['text']}")
        rec = {"id": it["id"], "text": it["text"], "model": s.llm_model, "effort": s.llm_reasoning_effort,
               "prompt_version": PROMPT_VERSION,
               "lang": a.lang, "input_error": p.input.error.model_dump() if p.input.error else None}
        if p.input.error:
            print("  chan o buoc kiem tra dau vao:", p.input.error.reason)
            results.append(rec)
            return
        rec["tokens"] = [t.surface for t in p.tokens]
        rec["chunks"] = [c.text(p.tokens) for c in p.chunks]
        rec["candidates"] = sorted({m.grammar_id for m in p.matches})
        st = await analyze_llm(p, client)
        rec["status"] = st.status
        # buoc 2.5: ket qua day du tra cho app (khuon 11.5)
        rec["result"] = assemble(p, st, kho, a.lang)[0].model_dump(mode="json", exclude_none=True)
        rec["attempts"] = [a.__dict__ for a in st.attempts]
        for k, a_ in enumerate(st.attempts, 1):
            print(f"  lan {k}: {a_.model} | {a_.prompt_tokens} (cache {a_.cached_tokens})+{a_.completion_tokens} token | "
                  f"{a_.latency_ms} ms | ~${a_.cost_usd}" + (f" | LOI: {a_.errors[:3]}" if a_.errors else ""))
        if st.input_check is not None:
            ic = st.input_check
            rec["input_check"] = ic.model_dump()
            if ic.status != "ok":
                at = "".join(t.surface for t in p.tokens[ic.at[0]:ic.at[1]]) if ic.at else "-"
                line = f"  KIEM TRA CAU: {ic.status} | cho sai: 「{at}」 | {ic.explain or ic.reason or ''}"
                if ic.correction:
                    c0, c1 = ic.correction_at or (0, 0)
                    line += f"\n  cau dung: {ic.correction[:c0]}【{ic.correction[c0:c1]}】{ic.correction[c1:]}"
                print(line)
        if st.output is None or st.status == "grammar_error":
            print(f"  => {st.status}" + (f" ({st.error})" if st.error else ""))
            if st.attempts:
                last = st.attempts[-1]
                rec["usage"] = {"model": last.model, "prompt": sum(a_.prompt_tokens for a_ in st.attempts),
                                "completion": sum(a_.completion_tokens for a_ in st.attempts),
                                "cached": sum(a_.cached_tokens for a_ in st.attempts), "ms": st.latency_ms,
                                "cost": st.cost_usd, "fallback": len(st.attempts) > 1}
            results.append(rec)
            return
        if st.report and st.report.fixes:
            print("  tu sua:", st.report.fixes)
        print(render(st.output, p.tokens, kho))
        last = st.attempts[-1]
        rec.update(output=st.output.model_dump(), fixes=st.report.fixes if st.report else [],
                   usage={"model": last.model, "prompt": sum(a_.prompt_tokens for a_ in st.attempts),
                          "completion": sum(a_.completion_tokens for a_ in st.attempts),
                          "cached": sum(a_.cached_tokens for a_ in st.attempts), "ms": st.latency_ms,
                          "cost": st.cost_usd, "fallback": len(st.attempts) > 1})
        results.append(rec)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
