"""Cham tu dong (buoc 3.1, muc 8 file ke hoach). Goi qua analyze_full() that: kiem tra
dau vao, goi lai model du phong, ghep ket qua - giong het luc chatbot goi. Khong dung cache.

    python scripts/eval.py                          # bo cau kiem thu + 20 cau vi du kho moi cap N5-N3
    python scripts/eval.py --models gpt-5-mini gpt-4.1   # so sanh nhieu model
    python scripts/eval.py --set golden             # chi bo cau kiem thu (76 cau)
    python scripts/eval.py --set kho --kho-n 50 --levels N5 N4 N3 N2 N1
    python scripts/eval.py --rules-only             # chi do bo luat tren toan bo cau vi du kho (khong goi LLM)

Ket qua: runs/eval_<thoi gian>.md (bao cao so sanh) + runs/eval_<thoi gian>_<model>.json (tung cau).
Chi phi tham khao: ~$0,002/cau voi gpt-5-mini -> bo mac dinh (~130 cau) ~$0,25 moi model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.analyzer import analyze_full
from bunpo_analyzer.core.cache import NoCache
from bunpo_analyzer.core.data import get_kho
from bunpo_analyzer.core.input_check import check_input
from bunpo_analyzer.core.matcher import get_matcher
from bunpo_analyzer.core.tokenizer import tokenize
from bunpo_analyzer.evaluation import (BASIC_IDS, check_status, kho_examples, kho_hit, latency_stats, pct,
                                       score_grammar, score_structure)

ROOT = Path(__file__).resolve().parents[1]
TARGET = {"rule": 0.95, "pick": 0.90, "first": 0.95}  # muc 8


def load_golden() -> list[dict]:
    return json.loads((ROOT / "tests" / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]


# ---------------- chay ----------------
async def run_one(item: dict, s: Settings, kho, sem: asyncio.Semaphore, client=None) -> dict:
    async with sem:
        t0 = time.perf_counter()
        try:
            a = await analyze_full(item["text"], "vi", settings=s, kho=kho, cache=NoCache(), client=client)
        except Exception as e:  # loi bat ngo: ghi lai, khong dung ca lan chay
            return {**item, "crash": repr(e)}
        ms = int((time.perf_counter() - t0) * 1000)
    r = a.result
    st = a.stage
    rec = {**item, "ms": ms, "cost": a.cost_usd,
           "attempts": [{"model": x.model, "errors": x.errors[:5], "ms": x.latency_ms, "cost": x.cost_usd}
                        for x in (st.attempts if st else [])],
           "result": r.model_dump(mode="json", exclude_none=True)}
    rec["llm"] = bool(rec["attempts"]) or (st is not None and st.status == "llm_unavailable")
    rec["first_ok"] = bool(rec["attempts"]) and not rec["attempts"][0]["errors"]
    surfaces = [t.surface for t in a.prepared.tokens]
    got = {g["id"] for g in rec["result"].get("grammar", [])}
    if item["set"] == "golden":
        gold = item["gold"]
        rec["status_ok"], rec["status_note"] = check_status(gold, rec["result"])
        if "full" in gold["tags"] and r.nodes:
            rec["structure"] = score_structure(r.text, surfaces, [n.model_dump() for n in r.nodes], gold,
                                               a.prepared.matches, kho)
        elif gold["expect"].get("grammar_must") and r.error is None:
            rec["grammar"] = score_grammar(got, gold, a.prepared.matches, kho)
    else:
        gid = item["grammar_id"]
        cands = {m.grammar_id for m in a.prepared.matches}
        # mau de LLM tu nhan (llm_only): khong co luat, khong tinh vao chi so bo luat
        llm_only = gid in {x.id for x in get_matcher().llm_only}
        rec["rule_hit"] = None if llm_only else (gid in cands or kho_hit(gid, cands, [], kho))
        rec["llm_hit"] = kho_hit(gid, got, a.prepared.matches, kho)
        rec["flagged"] = r.input_check.status
    return rec


QUOTA = asyncio.Event()


async def run_model(model: str, items: list[dict], base: Settings, kho, conc: int, effort: str | None) -> list[dict]:
    upd = {"llm_model": model}
    if effort:
        upd["llm_reasoning_effort"] = effort
    s = base.model_copy(update=upd)
    sem = asyncio.Semaphore(conc)
    done = 0
    out: list[dict] = []

    async def one(it):
        nonlocal done
        if QUOTA.is_set():  # het ngan sach gateway: cac cau con lai khong goi nua
            return
        rec = await run_one(it, s, kho, sem)
        done += 1
        if ((rec.get("result") or {}).get("error") or {}).get("reason") == "quota":
            if not QUOTA.is_set():
                print("\n!!! Gateway bao HET NGAN SACH (429). Dung danh gia, ket qua chua day du.", flush=True)
            QUOTA.set()
            return
        mark = "" if rec.get("status_ok", True) and rec.get("llm_hit", True) and "crash" not in rec else "  <-- xem lai"
        print(f"  [{model}] {done}/{len(items)} {it['id']} {rec.get('ms', 0)} ms{mark}", flush=True)
        out.append(rec)

    await asyncio.gather(*(one(it) for it in items))
    order = {it["id"]: k for k, it in enumerate(items)}
    return sorted(out, key=lambda r: order[r["id"]])


# ---------------- tong hop ----------------
def summarize(recs: list[dict]) -> dict:
    g = [r for r in recs if r["set"] == "golden" and "crash" not in r]
    k = [r for r in recs if r["set"] == "kho" and "crash" not in r]
    full = [r["structure"] for r in g if "structure" in r]
    pat = [r["grammar"] for r in g if "grammar" in r]
    llm = [r for r in recs if r.get("llm")]
    called = [r for r in llm if r["attempts"]]
    errs = [(r.get("result") or {}).get("error") or {} for r in llm]
    s = {
        "n": len(recs), "crash": sum("crash" in r for r in recs),
        "status": (sum(r["status_ok"] for r in g), len(g)),
        "full_n": len(full),
        "rows": tuple(sum(x["rows"][i] for x in full) for i in range(2)),
        "groups": tuple(sum(x["groups"][i] for x in full) for i in range(2)),
        "must_full": tuple(sum(x["must"][i] for x in full) for i in range(2)),
        "extra_full": sum(len(x["extra"]) for x in full),
        "cover": (sum(x["coverage_ok"] for x in full), len(full)),
        "must_pat": tuple(sum(x["must"][i] for x in pat) for i in range(2)),
        "extra_pat": sum(len(x["extra"]) for x in pat),
        "kho_n": len(k),
        "rule": (sum(bool(r["rule_hit"]) for r in k), sum(r["rule_hit"] is not None for r in k)),
        "pick": (sum(r["llm_hit"] for r in k), len(k)),
        "pick_nobasic": (sum(r["llm_hit"] for r in k if r["grammar_id"] not in BASIC_IDS),
                         sum(1 for r in k if r["grammar_id"] not in BASIC_IDS)),
        "pick_when_rule": (sum(r["llm_hit"] for r in k if r["rule_hit"] is not False),
                           sum(1 for r in k if r["rule_hit"] is not False)),
        "kho_flag": (sum(r["flagged"] == "error" for r in k), sum(r["flagged"] == "suspect" for r in k)),
        "llm_n": len(llm),
        "first": (sum(r["first_ok"] for r in called), len(called)),
        "fallback": sum(len(r["attempts"]) > 1 for r in called),
        "failed": sum(e.get("code") == "structure_failed" for e in errs),
        "unavail": sum(e.get("code") == "llm_unavailable" for e in errs),
        "lat": latency_stats([r["ms"] for r in called]),
        "cost": sum(r["cost"] for r in called) / max(1, len(called)),
    }
    return s


def fmt(model: str, s: dict) -> dict[str, str]:
    def fr(t):
        return f"{t[0]}/{t[1]} ({pct(*t)})" if t[1] else "-"

    lat = s["lat"]
    return {
        "Trạng thái đúng (lỗi, tự sửa, câu sai/nghi sai) – bộ câu kiểm thử": fr(s["status"]),
        f"Dòng đúng (vai trò + chữ) – {s['full_n']} câu đầy đủ": fr(s["rows"]),
        "Nhóm đúng (loại + chữ)": fr(s["groups"]),
        "Mẫu bắt buộc tìm thấy – câu đầy đủ": fr(s["must_full"]),
        "Mẫu bắt buộc tìm thấy – câu theo mẫu": fr(s["must_pat"]),
        "Mẫu gắn thừa (không tính trợ từ cơ bản)": str(s["extra_full"] + s["extra_pat"]),
        "Phủ kín token": fr(s["cover"]),
        f"Kho: bộ luật bắt được mẫu đúng (mục tiêu ≥ {TARGET['rule']:.0%})": fr(s["rule"]),
        f"Kho: LLM chọn đúng mẫu (mục tiêu ≥ {TARGET['pick']:.0%})": fr(s["pick"]),
        "Kho: LLM chọn đúng, bỏ trợ từ cơ bản": fr(s["pick_nobasic"]),
        "Kho: LLM chọn đúng khi luật đã bắt được (hoặc mẫu để LLM tự nhận)": fr(s["pick_when_rule"]),
        "Kho: câu ví dụ bị báo sai / nghi sai (nên = 0)": f"{s['kho_flag'][0]} / {s['kho_flag'][1]}",
        f"Đạt khuôn ngay lần đầu (mục tiêu ≥ {TARGET['first']:.0%})": fr(s["first"]),
        "Phải gọi model dự phòng": f"{s['fallback']}/{s['first'][1]}",
        "structure_failed / llm_unavailable": f"{s['failed']} / {s['unavail']}",
        "Độ trễ TB / p50 / p95 / max (s)": f"{lat['avg'] / 1000:.1f} / {lat['p50'] / 1000:.1f} / {lat['p95'] / 1000:.1f} / {lat['max'] / 1000:.1f}",
        "Chi phí TB / câu (1.000 câu)": f"${s['cost']:.4f} (${s['cost'] * 1000:.2f})",
    }


def problems(recs: list[dict], limit: int = 25) -> list[str]:
    out = []
    for r in recs:
        if "crash" in r:
            out.append(f"- {r['id']} {r['text']}: LỖI CHẠY {r['crash']}")
            continue
        notes = []
        if r["set"] == "golden" and not r["status_ok"]:
            notes.append(r["status_note"])
        st = r.get("structure")
        if st:
            if st["missing_rows"] or st["wrong_rows"]:
                notes.append(f"dòng thiếu {st['missing_rows']} / sai {st['wrong_rows']}")
            if st["missing_groups"] or st["wrong_groups"]:
                notes.append(f"nhóm thiếu {st['missing_groups']} / sai {st['wrong_groups']}")
        for key in ("structure", "grammar"):
            x = r.get(key)
            if x and x["missed"]:
                notes.append(f"thiếu mẫu {x['missed']}")
        if r["set"] == "kho":
            if r["rule_hit"] is False:
                notes.append(f"luật không bắt #{r['grammar_id']}")
            if r["rule_hit"] is not False and not r["llm_hit"]:
                got = [g["id"] for g in r["result"].get("grammar", [])]
                notes.append(f"LLM không chọn #{r['grammar_id']} (chọn {got})")
            if r["flagged"] != "ok":
                notes.append(f"bị báo {r['flagged']}")
        if r.get("attempts") and r["attempts"][0]["errors"]:
            notes.append(f"lần đầu sai khuôn: {r['attempts'][0]['errors'][:2]}")
        if notes:
            out.append(f"- {r['id']} {r['text']}: " + "; ".join(notes))
    return out[:limit] + ([f"- … còn {len(out) - limit} câu (xem file JSON)"] if len(out) > limit else [])


def rules_only(kho, levels) -> None:
    """Do bo luat tren MOI cau vi du trong kho (bo mau de LLM tu nhan).
    - Khoi chinh (truoc dong ──────): so chinh, so voi muc tieu 95%.
    - Khoi gop (sau ──────): thuong la nghia / mau khac bi gop vao, chi de tham khao.
    Vi du 1 cau: cau do phai co mau. Vi du hoi thoai: dung neu mot cau co mau."""
    from bunpo_analyzer.evaluation import example_blocks

    m = get_matcher()
    llm_only = {x.id for x in m.llm_only}
    print("Bo luat tren cau vi du trong kho (khong goi LLM):")
    for lv in levels:
        cnt = {k: [0, 0] for k in ("one", "multi", "merged")}
        misses, merged_miss = [], []
        for g in kho.grammars.values():
            if g.level != lv or g.id in llm_only:
                continue
            for b, items in enumerate(example_blocks(g.raw.get("examples"))):
                for it in items:
                    sents = [x for x in it if not check_input(x).error]
                    if not sents:
                        continue
                    hit = False
                    for sent in sents:
                        ids = {x.grammar_id for x in m.match(tokenize(sent))}
                        if g.id in ids or kho_hit(g.id, ids, [], kho):
                            hit = True
                            break
                    key = "merged" if b > 0 else ("one" if len(sents) == 1 else "multi")
                    cnt[key][0] += hit
                    cnt[key][1] += 1
                    if not hit and key == "one":
                        misses.append(f"#{g.id} {g.name}: {sents[0]}")
                    elif not hit and key == "merged":
                        merged_miss.append(f"#{g.id} {g.name} (khoi {b + 1}): {' / '.join(sents)}")
        o, mu, me = cnt["one"], cnt["multi"], cnt["merged"]
        print(f"  {lv}: vi du 1 cau {o[0]}/{o[1]} ({pct(*o)}) | hoi thoai {mu[0]}/{mu[1]} ({pct(*mu)})"
              f" | khoi gop {me[0]}/{me[1]} ({pct(*me)})")
        Path("runs").mkdir(exist_ok=True)
        (Path("runs") / f"rules_miss_{lv}.txt").write_text("\n".join(misses), encoding="utf-8")
        (Path("runs") / f"rules_miss_{lv}_gop.txt").write_text("\n".join(merged_miss), encoding="utf-8")
    print("Cau luat khong bat: runs/rules_miss_<cap>.txt (khoi chinh), runs/rules_miss_<cap>_gop.txt (khoi gop)")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+")
    ap.add_argument("--effort", help="minimal | low | medium | high (model suy nghi)")
    ap.add_argument("--set", choices=["golden", "kho", "all"], default="all")
    ap.add_argument("--kho-n", type=int, default=20, help="so mau moi cap")
    ap.add_argument("--levels", nargs="+", default=["N5", "N4", "N3"])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--limit", type=int, help="chi chay N cau dau (thu nhanh)")
    ap.add_argument("--rules-only", action="store_true")
    a = ap.parse_args()
    base = Settings()
    kho = get_kho(base.data_dir)
    if a.rules_only:
        rules_only(kho, a.levels)
        return 0
    if not base.openai_api_key:
        print("Thieu BUNPO_OPENAI_API_KEY trong .env")
        return 1
    items: list[dict] = []
    if a.set in ("golden", "all"):
        items += [{"set": "golden", "id": g["id"], "text": g["text"], "gold": g} for g in load_golden()]
    if a.set in ("kho", "all"):
        items += [{"set": "kho", "id": f"K{e.grammar_id}", "text": e.text, "grammar_id": e.grammar_id, "level": e.level}
                  for e in kho_examples(kho, a.levels, a.kho_n, a.seed, base.max_chars)]
    items = items[: a.limit] if a.limit else items
    models = a.models or [base.llm_model]
    ts = time.strftime("%Y%m%d_%H%M%S")
    Path("runs").mkdir(exist_ok=True)
    table: dict[str, dict[str, str]] = {}
    detail: list[str] = []
    for model in models:
        print(f"\n=== {model}: {len(items)} cau")
        recs = await run_model(model, items, base, kho, a.concurrency, a.effort)
        if QUOTA.is_set():
            print("Dung: het ngan sach gateway. Nho nguoi quan ly nang han muc / cap key moi roi chay lai.")
            return 2
        f = Path("runs") / f"eval_{ts}_{model}.json"
        f.write_text(json.dumps(recs, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        s = summarize(recs)
        table[model] = fmt(model, s)
        detail += [f"\n### {model}: câu cần xem lại\n", *problems(recs)]
        for k, v in table[model].items():
            print(f"  {k}: {v}")
    lines = [f"# Đánh giá {ts}", "",
             f"Bộ thử: {a.set}; kho {a.kho_n} mẫu/cấp {', '.join(a.levels)} (seed {a.seed}); "
             f"model dự phòng {base.llm_fallback_model}; effort {a.effort or base.llm_reasoning_effort}.", "",
             "| Chỉ số | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for key in next(iter(table.values())):
        lines.append(f"| {key} | " + " | ".join(table[m][key] for m in models) + " |")
    md = Path("runs") / f"eval_{ts}.md"
    md.write_text("\n".join(lines + detail) + "\n", encoding="utf-8")
    print(f"\nBao cao: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
