"""Nhan giao dien theo ngon ngu cho cac ma trong ket qua (tu loai, vai tro, loai menh de, ma loi).

    from bunpo_analyzer import labels
    L = labels("en")
    L["pos"]["noun"]          # "noun"            Token.pos
    L["pos_sub"]["v1"]        # "Group 1 verb"    Token.pos_sub
    L["role"]["subject"]      # "Subject"         Node.role; Node.main -> L["role"]["main_predicate"]
    L["role_hidden"]          # "{role} (omitted)"  Node.hidden: .format(role=...)
    L["kind"]["sub"]          # "Subordinate clause"  Node.kind
    L["kind_rel_for"]         # "Clause modifying {head}"  kind = rel co head_text: .format(head=...)
    L["base_form"]            # "dictionary form" (dang goc, Token.base)
    L["check"]["suspect"]     # input_check.status
    L["error"]["grammar_error"]  # error.code

Bang tables/ui_labels.json sinh boi scripts/translation/export_ui_labels.py (16 ngon ngu).
Ngon ngu chua co (hoac thieu muc) -> dung tieng Anh. Ham tra ban sao, sua thoai mai.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PATH = Path(__file__).resolve().parent.parent / "tables" / "ui_labels.json"
FALLBACK_LANG = "en"


@lru_cache(maxsize=1)
def _table() -> dict[str, dict[str, Any]]:
    return json.loads(PATH.read_text(encoding="utf-8"))["langs"]


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def labels(lang: str = "vi") -> dict[str, Any]:
    t = _table()
    return _merge(t[FALLBACK_LANG], t.get(lang) or {})


def label_langs() -> list[str]:
    return sorted(_table())
