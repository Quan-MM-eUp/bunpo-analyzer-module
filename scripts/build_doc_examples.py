"""Sinh tai lieu tich hop: docs/schema/*.json (khuon JSON Schema) va docs/examples/*.json (ket qua chay that).

    python scripts/build_doc_examples.py               # can mang: LLM gateway + Mazii (~1 phut, ~$0.02)
    python scripts/build_doc_examples.py --schema-only

Moi file vi du: {"call": cach goi, "meta": {cache, latency_ms, cost_usd}, "result": ket qua}. Khong ghi key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from bunpo_analyzer import SCHEMA_VERSION, AnalysisResult, GrammarDetail, check_ready, grammar_detail, labels
from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.analyzer import analyze_full
from bunpo_analyzer.core.cache import MemoryCache

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

CASES = [  # (ten file, cau, lang) - chay theo thu tu: en sau vi cung cau -> "dich nhe" tu cache
    ("analyze_ok_vi", "雨が降りそうなので、傘を持っていきます。", "vi"),
    ("analyze_ok_en_light", "雨が降りそうなので、傘を持っていきます。", "en"),
    ("analyze_ok_ko", "昨日友達と見た映画はとても面白かったです。", "ko"),
    ("analyze_grammar_error_en", "映画は面白いでした。", "en"),
    ("analyze_auto_fix_vi", "見みた映画は面白かった。", "vi"),
    ("analyze_invalid_not_japanese", "Hello, how are you?", "en"),
    ("analyze_invalid_multiple", "今日は晴れです。明日は雨です。", "vi"),
]


def dump(name: str, obj) -> None:
    p = DOCS / "examples" / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def write_schema() -> None:
    d = DOCS / "schema"
    d.mkdir(parents=True, exist_ok=True)
    for name, model in (("analysis_result", AnalysisResult), ("grammar_detail", GrammarDetail)):
        sch = model.model_json_schema()
        sch["$comment"] = f"bunpo-analyzer, khuon {SCHEMA_VERSION}. Sinh boi scripts/build_doc_examples.py"
        (d / f"{name}.schema.json").write_text(json.dumps(sch, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"-> {d}")


async def run() -> None:
    s = Settings()
    cache = MemoryCache(100)
    rep = await check_ready(s, ping=True)
    dump("check_ready", {"call": "await check_ready(ping=True)", "result": rep})
    print("check_ready:", rep["ok"], {k: (v["ok"], v.get("warn", False)) for k, v in rep["checks"].items()})
    for name, text, lang in CASES:
        t = time.perf_counter()
        a = await analyze_full(text, lang, settings=s, cache=cache)
        meta = {"cache": a.cache, "models": a.log_dict().get("models"), "latency_ms": round(a.latency_ms),
                "cost_usd": round(a.cost_usd, 5),
                "wall_ms": round((time.perf_counter() - t) * 1000)}
        dump(name, {"call": f"await analyze({text!r}, lang={lang!r})", "meta": meta,
                    "result": a.result.model_dump(mode="json", exclude_none=True)})
        print(f"{name}: {meta} error={a.result.error.code if a.result.error else None}")
    for gid, lang in ((252, "en"), (338, "ko"), (252, "fr")):
        d = grammar_detail(gid, lang)
        dump(f"grammar_detail_{gid}_{lang}", {"call": f"grammar_detail({gid}, {lang!r})",
                                               "result": d.model_dump(mode="json") if d else None})
    for lg in ("en", "ko", "vi"):
        dump(f"labels_{lg}", {"call": f"labels({lg!r})", "result": labels(lg)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema-only", action="store_true")
    a = ap.parse_args()
    write_schema()
    if not a.schema_only:
        asyncio.run(run())
        print(f"-> {DOCS / 'examples'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
