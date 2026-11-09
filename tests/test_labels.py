"""G2: nhan giao dien theo ngon ngu (bunpo_analyzer.labels)."""

from typing import get_args

from bunpo_analyzer import label_langs, labels
from bunpo_analyzer.schema import ErrorCode, GroupKind, Pos, PosSub, Role

LANGS = ("vi", "en", "cn", "tw", "ko", "fr", "de", "es", "pt", "ru", "pl", "id", "th", "hi", "ne", "my")


def test_all_langs_complete():
    assert sorted(LANGS) == label_langs()
    for lang in LANGS:
        L = labels(lang)
        assert set(L["pos"]) == set(get_args(Pos)) - {"punct"}
        assert set(L["pos_sub"]) == set(get_args(PosSub))
        assert set(L["role"]) == set(get_args(Role)) | {"main_predicate"}
        assert set(L["kind"]) == set(get_args(GroupKind))
        assert set(L["error"]) == set(get_args(ErrorCode)) and set(L["check"]) == {"suspect", "error"}
        assert "{role}" in L["role_hidden"] and "{head}" in L["kind_rel_for"] and L["base_form"]
        texts = [*L["pos"].values(), *L["pos_sub"].values(), *L["role"].values(), *L["kind"].values()]
        assert all(isinstance(t, str) and t.strip() for t in texts), lang
        if lang != "vi":
            assert not any(c in "ăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ" for t in texts for c in t.lower()), lang


def test_values_and_fallback():
    assert labels("vi")["kind"]["sub"] == "Vế phụ" and labels("vi")["role"]["main_predicate"] == "Vị ngữ chính"
    assert labels("en")["pos_sub"]["v1"] == "Group 1 verb" and labels("ko")["role"]["subject"] == "주어"
    assert labels("en")["role_hidden"].format(role="Subject") == "Subject (omitted)"
    assert labels("xx") == labels("en")  # ngon ngu chua co -> tieng Anh
    a = labels("en")
    a["pos"]["noun"] = "x"
    assert labels("en")["pos"]["noun"] == "noun"  # tra ban sao
