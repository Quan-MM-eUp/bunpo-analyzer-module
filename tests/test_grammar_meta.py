"""Buoc 4.1: short_label + confusable_ids (tables/grammar_meta.json)."""

import importlib.util
import json
from pathlib import Path

from bunpo_analyzer.core.canon import canon_id
from bunpo_analyzer.core.grammar_meta import PATH, confusable_ids, meta, short_label

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads(PATH.read_text(encoding="utf-8"))["grammar"]


def _builder():
    spec = importlib.util.spec_from_file_location("bgm", ROOT / "scripts" / "build_grammar_meta.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rules_short_label():
    b = _builder()
    assert b.short_label("～た　ことが　ある", "～たことがある") == ("～たことがある", "neutral")
    assert b.short_label("Trợ từ と", "と") == ("と", "neutral")
    assert b.short_label("Tính từ → Trạng từ", "Aい→Aく / Na→Naに") == ("Aい→Aく/Na→Naに", "neutral")
    assert b.short_label("～から（lý do）", "～から") == ("～から（lý do）", "vi")  # chu Viet chi trong ngoac: giu
    assert b.short_label("N1に N2を V", "N1にN2をV")[0] == "N1にN2をV"
    assert b.short_label("V thể ý chí と思っています", "V thể ý chí と思っています")[0] == "V thể ý chí と思っています"
    assert b.short_label("Mệnh đề bổ nghĩa danh từ", "Mệnh đề bổ nghĩa danh từ") == ("Mệnh đề bổ nghĩa danh từ", "vi")


def test_table():
    assert len(DATA) > 1500
    for gid, m in DATA.items():
        assert m["short_label"] and m["label_lang"] in ("vi", "neutral")
        assert int(gid) not in [canon_id(i) for i in m["confusable_ids"]] or canon_id(int(gid)) != int(gid)
        assert all(canon_id(i) == i for i in m["confusable_ids"])  # da tro ve mau chuan
    assert meta(252)["short_label"] == "～たことがある" and 350 in confusable_ids(252)
    assert short_label(999999) is None and confusable_ids(999999) == []
