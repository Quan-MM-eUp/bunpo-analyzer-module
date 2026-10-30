"""Du lieu phu cua mau ngu phap cho the va bang ngu phap (buoc 4.1, muc 11.7).

Sinh boi scripts/build_grammar_meta.py tu kho (kho giu nguyen):
- short_label: nhan ngan tren the (～たことがある, と, Aい→Aく / Na→Naに).
- confusable_ids: mau "De nham voi" da doi sang id (mau chuan neu da gom mau trung).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

PATH = Path(__file__).resolve().parent.parent / "tables" / "grammar_meta.json"


@lru_cache(maxsize=1)
def _table() -> dict[int, dict[str, Any]]:
    if not PATH.exists():
        return {}
    data = json.loads(PATH.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data.get("grammar", {}).items()}


def meta(gid: int) -> dict[str, Any]:
    return _table().get(int(gid), {})


def short_label(gid: int, kho=None, lang: str = "vi") -> Optional[str]:
    """Nhan ngan theo ngon ngu. Nhan con chu Viet (label_lang = vi): ngon ngu khac lay ten da dich."""
    m = meta(gid)
    label = m.get("short_label")
    if label and (m.get("label_lang") != "vi" or lang == "vi" or kho is None):
        return label
    if kho is not None:
        name = kho.grammar_text(gid, lang).get("name")
        g = kho.grammar(gid)
        return name or label or (g.name if g else None)
    return label


def confusable_ids(gid: int) -> list[int]:
    return list(meta(gid).get("confusable_ids", []))
