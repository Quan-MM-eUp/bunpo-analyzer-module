"""Buoc 3.2: mau trung -> mau chuan (tables/grammar_canon.json)."""

import json

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.core.canon import PATH, canon_id, canonicalize, group_of  # noqa: E402
from bunpo_analyzer.core.matcher import Match, get_matcher  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402

DATA = json.loads(PATH.read_text(encoding="utf-8"))


def test_table_shape():
    seen = set()
    for g in DATA["groups"]:
        assert g["canon"] in g["members"] and len(g["members"]) >= 2
        assert not seen & set(g["members"]), "mot id chi thuoc mot nhom"
        seen |= set(g["members"])


def test_canon_lookup():
    g = DATA["groups"][0]
    other = next(i for i in g["members"] if i != g["canon"])
    assert canon_id(other) == g["canon"] and canon_id(g["canon"]) == g["canon"]
    assert set(group_of(other)) == set(g["members"]) and canon_id(999999) == 999999


def test_canonicalize_dedupes():
    g = DATA["groups"][0]
    ms = [Match(i, 0, 2, 0, 2, (0, 1)) for i in g["members"]] + [Match(43, 3, 4, 3, 4, (3,))]
    out = canonicalize(ms)
    assert [m.grammar_id for m in out] == [g["canon"], 43]


def test_real_sentence_one_candidate_per_duplicate():
    toks = tokenize("日本語が話せるようになった。")
    ids = [m.grammar_id for m in canonicalize(get_matcher().match(toks))]
    for g in DATA["groups"]:
        assert len(set(ids) & set(g["members"])) <= 1
