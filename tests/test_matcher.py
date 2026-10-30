"""Buoc 1.5a: bo may do mau ngu phap + dinh dang luat."""

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

pytest.importorskip("sudachipy")

from bunpo_analyzer.core.input_check import normalize  # noqa: E402
from bunpo_analyzer.core.matcher import Cond, GrammarMatcher, Rule, RuleFile, get_matcher  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402

MATCHER = get_matcher()
EXAMPLES = [(r.id, ex, True) for r in MATCHER.rules for ex in r.examples] + \
           [(r.id, ex, False) for r in MATCHER.rules for ex in r.not_examples]


@pytest.mark.parametrize("gid,text,should", EXAMPLES, ids=[f"{g}-{'ok' if s else 'not'}-{t}" for g, t, s in EXAMPLES])
def test_rule_examples(gid, text, should):
    """Moi luat tu kiem tra bang examples / not_examples ghi ngay trong file luat."""
    got = gid in MATCHER.candidate_ids(tokenize(normalize(text)))
    assert got == should


def test_every_rule_has_examples():
    for r in MATCHER.rules:
        assert r.examples, f"luat {r.id} chua co examples"


def _m(rule: dict, text: str):
    toks = tokenize(text)
    return GrammarMatcher([Rule.model_validate(rule)]).match(toks), toks


def test_core_span_excludes_context():
    ms, toks = _m({"id": 1, "patterns": [[{"pos": "verb", "ctx": True}, {"surface": "て"}, {"base": "いる"}]]},
                  "雨が降っている。")
    m = ms[0]
    assert (m.start, m.core_start) == (2, 3) and m.text(toks) == "ている"


def test_optional_gap_not_and_prefix():
    rule = {"id": 2, "patterns": [[{"surface": "もし"}, {"gap": 4}, {"base": "た", "cform": "仮定形"}]]}
    assert _m(rule, "もし雨が降ったら、行かない。")[0]
    assert not _m(rule, "もし。雨が降ったら")[0]  # gap khong vuot qua 。
    rule = {"id": 3, "patterns": [[{"pos": "verb", "ctx": True}, {"surface": "て"}, {"surface": "も", "optional": True},
                                   {"base": "いい"}]]}
    assert _m(rule, "食べてもいい。")[0] and _m(rule, "食べていい。")[0]
    rule = {"id": 4, "patterns": [[{"pos": "noun", "not": {"surface": "雨"}}, {"surface": "が"}]]}
    ms, toks = _m(rule, "雨が降り、風が吹く。")
    assert [m.text(toks) for m in ms] == ["風が"]


def test_anchors_and_pos3():
    rule = {"id": 6, "patterns": [[{"bos": True}, {"pos": "noun"}]]}
    ms, toks = _m(rule, "雨だ。風も強い。")
    assert [m.text(toks) for m in ms] == ["雨", "風"]  # chi danh tu dau cau / sau 。
    rule = {"id": 7, "patterns": [[{"surface": "から"}, {"eos": True}]]}
    assert _m(rule, "時間がないから。")[0] and not _m(rule, "時間がないから、行かない。")[0]
    rule = {"id": 8, "patterns": [[{"pos": "noun", "pos3": "サ変可能"}, {"surface": "に"}, {"base": "行く"}]]}
    assert _m(rule, "買い物に行く。")[0] and not _m(rule, "駅に行く。")[0]
    with pytest.raises(ValidationError):
        Rule.model_validate({"id": 9, "patterns": [[{"bos": True, "surface": "で"}]]})
    with pytest.raises(ValidationError):
        Rule.model_validate({"id": 9, "patterns": [[{"bos": True}]]})


def test_literal_prefilter_and_dedupe():
    rule = {"id": 5, "patterns": [[{"surface": "か"}, {"surface": "も"}], [{"surface": "か"}, {"surface": "も"}, {"base": "しれる"}]]}
    ms, toks = _m(rule, "降るかもしれない。")
    assert len(ms) == 1 and ms[0].text(toks) == "かもしれ"  # giu phan dai hon


@pytest.mark.parametrize("bad", [
    {"id": 1, "patterns": [[]]},
    {"id": 1, "patterns": [[{"pos": "verb", "ctx": True}]]},  # khong co token thuoc mau
    {"id": 1, "patterns": [[{"gap": 2}, {"surface": "て"}]]},  # gap o dau
    {"id": 1, "patterns": [[{"surface": "て", "gap": 2}]]},
    {"id": 1, "patterns": [[{}]]},
    {"id": 1, "patterns": [[{"surfaces": "て"}]]},  # sai ten truong
])
def test_invalid_rules(bad):
    with pytest.raises(ValidationError):
        Rule.model_validate(bad)


def test_duplicate_ids(tmp_path):
    rf = {"rules": [{"id": 1, "patterns": [[{"surface": "て"}]], "examples": ["x"]}]}
    for n in ("a", "b"):
        (tmp_path / f"{n}.json").write_text(json.dumps(rf), encoding="utf-8")
    with pytest.raises(ValueError, match="trung id"):
        GrammarMatcher.from_dir(tmp_path)


def test_rule_files_valid():
    for f in sorted((Path(__file__).resolve().parents[1] / "src" / "bunpo_analyzer" / "rules").glob("*.json")):
        RuleFile.model_validate(json.loads(f.read_text(encoding="utf-8")))


def test_artifact_sentence():
    toks = tokenize("先生に言われたとおりに練習したら、上手に話せるようになった。")
    got = {m.grammar_id: m.text(toks) for m in MATCHER.match(toks)}
    assert got[169] == "たら" and got[613] == "ようになっ"


def _kho_dir():
    base = Path(os.environ.get("BUNPO_DATA_DIR", Path(__file__).resolve().parents[2]))
    return base if (base / "grammar" / "grammar_lib.json").exists() else None


@pytest.mark.kho
def test_rule_ids_exist_in_kho():
    base = _kho_dir()
    if base is None:
        pytest.skip("khong tim thay kho du lieu")
    ids = {int(g["id"]) for g in json.loads((base / "grammar" / "grammar_lib.json").read_text(encoding="utf-8"))}
    assert {r.id for r in MATCHER.rules} <= ids


def test_cond_alias_not():
    c = Cond.model_validate({"pos": "noun", "not": {"surface": "雨"}})
    assert c.not_ is not None


@pytest.mark.kho
def test_levels_fully_covered():
    """Moi mau cua cap da lam xong (N5-N1) deu co luat hoac nam trong llm_only."""
    base = _kho_dir()
    if base is None:
        pytest.skip("khong tim thay kho du lieu")
    lib = json.loads((base / "grammar" / "grammar_lib.json").read_text(encoding="utf-8"))
    covered = {r.id for r in MATCHER.rules} | {x.id for x in MATCHER.llm_only}
    for level in ("N5", "N4", "N3", "N2", "N1"):
        ids = {int(g["id"]) for g in lib if g["level"] == level}
        assert ids <= covered, sorted(ids - covered)[:20]


@pytest.mark.kho
def test_golden_must_found_for_covered_levels():
    """Cau kiem thu: moi mau bat buoc thuoc cap da co luat phai nam trong ung vien."""
    base = _kho_dir()
    if base is None:
        pytest.skip("khong tim thay kho du lieu")
    from bunpo_analyzer.core.input_check import check_input

    level = {int(g["id"]): g["level"] for g in json.loads((base / "grammar" / "grammar_lib.json").read_text(encoding="utf-8"))}
    items = json.loads((Path(__file__).parent / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]
    missing = []
    for it in items:
        e = it["expect"]
        if e.get("error") or not e.get("grammar_must"):
            continue
        ids = set(MATCHER.candidate_ids(tokenize(check_input(it["text"]).text)))
        for must in e["grammar_must"]:
            alts = must if isinstance(must, list) else [must]
            if not ids & set(alts):
                missing.append((it["id"], alts))
    assert not missing
