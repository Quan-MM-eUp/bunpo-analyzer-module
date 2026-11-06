"""Tao du lieu mau cho trang demo (che do khong noi server).

    python scripts/build_demo_mock.py runs/eval_xxx_gpt-5-mini.json [--out demo/mock_data.json]

Lay ket qua THAT cua mot lan chay eval.py cho cac cau goi y, gan lai nhan ngan theo
tables/grammar_meta.json, kem du lieu bang ngu phap (grammar_detail) cua moi mau
xuat hien va cac mau "De nham voi" cua chung. Khong goi LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bunpo_analyzer.config import get_settings
from bunpo_analyzer.core.data import get_kho
from bunpo_analyzer.core.grammar_detail import grammar_detail
from bunpo_analyzer.core.grammar_meta import short_label

ROOT = Path(__file__).resolve().parents[1]
# Cau goi y: thuong, menh de long nhau, cau sai, nghi sai, dinh furigana, khong phai tieng Nhat, nhieu cau
IDS = ["G02", "G03", "G06", "G13", "G07", "G31", "G37", "G21", "G46", "G44"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--out", default=str(ROOT / "demo" / "mock_data.json"))
    a = ap.parse_args()
    kho = get_kho(get_settings().data_dir)
    recs = {r["id"]: r for r in json.loads(Path(a.run).read_text(encoding="utf-8"))}
    results, order, gids = {}, [], set()
    for i in IDS:
        r = recs.get(i)
        if not r or "result" not in r:
            print("bo qua", i)
            continue
        res = r["result"]
        for g in res.get("grammar", []):
            g["short_label"] = short_label(g["id"], kho, "vi") or g.get("short_label")
            gids.add(g["id"])
        meta = {"cache": "miss", "models": [x["model"] for x in r.get("attempts", [])],
                "latency_ms": r.get("ms", 0), "cost_usd": r.get("cost", 0.0),
                "attempt_errors": [x["errors"] for x in r.get("attempts", [])], "fixes": [], "misses": []}
        results[r["text"]] = {"result": res, "meta": meta}
        order.append(r["text"])
    grammar = {}
    for gid in sorted(gids):
        d = grammar_detail(gid, "vi", kho)
        grammar[str(gid)] = d.model_dump(mode="json")
        for c in d.confusable:
            if str(c.id) not in grammar:
                grammar[str(c.id)] = grammar_detail(c.id, "vi", kho).model_dump(mode="json")
    out = {"source": Path(a.run).name, "suggestions": order, "results": results, "grammar": grammar}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{len(results)} cau, {len(grammar)} mau ngu phap -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
