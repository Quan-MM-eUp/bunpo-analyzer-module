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
    """Nhan ngan theo ngon ngu.

    label_lang: "neutral" (chi chu Nhat / ky hieu) dung cho moi ngon ngu; "vi" / "en": nhan co chu cua ngon
    ngu do. Ngon ngu khac: mau trung da gom lay nhan cua mau chuan; roi short_label da dich (nhan dich tay,
    translation/labels/<lang>.json); roi ten da dich; chua co thi dung nhan goc.
    `lang` chua co ban dich kho: dung nhan cua ngon ngu du phong (BUNPO_TEXT_FALLBACK_LANG, xem Kho.content_lang).
    """
    if kho is not None:
        lang = kho.content_lang(lang)
    m = meta(gid)
    label = m.get("short_label")
    if label and (m.get("label_lang", "neutral") in ("neutral", lang) or lang == "vi" or kho is None):
        return label
    if kho is not None:
        from bunpo_analyzer.core.canon import canon_id

        cid = canon_id(int(gid))
        if cid != int(gid) and kho.grammar(cid) is not None:
            return short_label(cid, kho, lang)
        tr = kho.grammar_tr(gid, lang)
        g = kho.grammar(gid)
        return tr.get("short_label") or tr.get("name") or label or (g.name if g else None)
    return label


def confusable_ids(gid: int) -> list[int]:
    return list(meta(gid).get("confusable_ids", []))
