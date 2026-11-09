"""Nhan giao dien theo ngon ngu (tu loai, vai tro, loai menh de, ma loi) -> tables/ui_labels.json.

    python scripts/translation/export_ui_labels.py [--ws ../translation]

Nguon: glossary/<lang>.json (thuat ngu da duyet o C2) + ui/labels_extra.json (nhan khong co trong
glossary, dich tren Cowork; vi_base: tieng Viet). Thieu muc nao -> bao loi, khong ghi.
Module doc bang `bunpo_analyzer.labels(lang)`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LANGS, read_json, workspace, write_json

OUT = Path(__file__).resolve().parents[2] / "src" / "bunpo_analyzer" / "tables" / "ui_labels.json"
# ma trong ket qua -> id thuat ngu trong glossary
GLOSS = {
    "pos": {"noun": "noun", "verb": "verb", "adj": "adjective", "adv": "adverb", "prt": "particle", "aux": "aux_verb"},
    "pos_sub": {"v1": "verb_g1", "v2": "verb_g2", "v3": "verb_g3", "adj_i": "i_adj", "adj_na": "na_adj"},
    "role": {"subject": "subject", "topic": "topic", "object": "object", "complement": "complement",
             "predicate": "predicate"},
    "kind": {"rel": "relative_clause", "sub": "sub_clause", "quote": "quotation", "nominal": "nominalization"},
}
EXTRA_ROLE = ("main_predicate", "adv_time", "adv_place", "adv_manner", "adv_reason")


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def build(ws: Path) -> tuple[dict, list[str]]:
    ex = read_json(ws / "ui" / "labels_extra.json")
    errs: list[str] = []
    out = {}
    for lang in ("vi", *LANGS):
        e = ex["extra"].get(lang) or {}
        miss = [k for k in ex["keys"] if not str(e.get(k) or "").strip()]
        if miss:
            errs.append(f"{lang}: ui/labels_extra.json thieu {miss}")
            continue
        if lang == "vi":
            t = {k: dict(v) if isinstance(v, dict) else v for k, v in ex["vi_base"].items()}
        else:
            gp = ws / "glossary" / f"{lang}.json"
            g = {x["id"]: x["tr"] for x in read_json(gp)["terms"]} if gp.exists() else {}
            t = {}
            for sec, m in GLOSS.items():
                vals = {code: g.get(tid) for code, tid in m.items()}
                bad = [c for c, v in vals.items() if not v]
                if bad:
                    errs.append(f"{lang}: glossary thieu {[m[c] for c in bad]}")
                t[sec] = {c: (cap(v) if sec in ("role", "kind") else v) for c, v in vals.items() if v}
            t["base_form"] = g.get("dict_form") or ""
        t["role"].update({k: e[k] for k in EXTRA_ROLE})
        t["role_hidden"], t["kind_rel_for"] = e["role_hidden"], e["kind_rel_for"]
        t["check"] = {"suspect": e["check_suspect"], "error": e["check_error"]}
        t["error"] = {c: e[f"err_{c}"] for c in ("invalid_input", "grammar_error", "structure_failed", "llm_unavailable")}
        for k in ("role_hidden",):
            if "{role}" not in t[k]:
                errs.append(f"{lang}: {k} thieu {{role}}")
        if "{head}" not in t["kind_rel_for"]:
            errs.append(f"{lang}: kind_rel_for thieu {{head}}")
        out[lang] = t
    return out, errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws")
    a = ap.parse_args(argv)
    data, errs = build(workspace(a.ws))
    for e in errs:
        print("LOI " + e)
    if errs:
        return 1
    write_json(OUT, {"version": 1, "note": "Sinh boi scripts/translation/export_ui_labels.py. Doc bang labels(lang).",
                     "langs": data})
    print(f"{len(data)} ngon ngu -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
