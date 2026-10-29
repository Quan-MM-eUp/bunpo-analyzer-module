"""Buoc 0.2: kiem tra bo cau kiem thu tu nhat quan (chua cham module)."""

import json
import os
import re
from pathlib import Path
from typing import get_args

import pytest

from bunpo_analyzer.schema import GroupKind, Role

GOLDEN = Path(__file__).parent / "golden" / "golden_set.json"
ITEMS = json.loads(GOLDEN.read_text(encoding="utf-8"))["items"]
FULL = [it for it in ITEMS if "full" in it["tags"]]
PUNCT = re.compile(r"[、。？！?!\s　]")
REASONS = {"not_japanese", "multiple_sentences", "too_long"}


def flat(ids):
    for x in ids:
        yield from (x if isinstance(x, list) else [x])


def leaves(nodes):
    for n in nodes:
        if "group" in n:
            yield from leaves(n["children"])
        else:
            yield n


def walk(nodes):
    for n in nodes:
        yield n
        if "group" in n:
            yield from walk(n["children"])


def grammar_lib_ids():
    base = Path(os.environ.get("BUNPO_DATA_DIR", Path(__file__).resolve().parents[2]))
    p = base / "grammar" / "grammar_lib.json"
    if not p.exists():
        return None
    return {int(g["id"]) for g in json.loads(p.read_text(encoding="utf-8"))}


def test_ids_unique_and_basic_fields():
    ids = [it["id"] for it in ITEMS]
    assert len(ids) == len(set(ids))
    texts = [it["text"] for it in ITEMS]
    assert len(texts) == len(set(texts)), "trung cau"
    for it in ITEMS:
        assert it["status"] in ("draft", "approved")
        assert it["case"] in {"#7", "#8", "#9", "#10", "#13", "#14"}


def test_size():
    assert len(FULL) == 20
    assert len(ITEMS) >= 60


@pytest.mark.parametrize("it", FULL, ids=[it["id"] for it in FULL])
def test_full_structure_covers_sentence(it):
    st = it["expect"]["structure"]
    joined = "".join(n["text"] for n in leaves(st) if not n.get("hidden"))
    assert joined == PUNCT.sub("", it["text"]), "cac dong khong ghep lai dung cau"
    for n in walk(st):
        if "group" in n:
            assert n["group"] in get_args(GroupKind)
            inner = "".join(c["text"] for c in leaves(n["children"]) if not c.get("hidden"))
            assert inner == n["text"], f"nhom {n['text']}"
            if "head" in n:
                assert (n["text"] + n["head"]) in PUNCT.sub("", it["text"])
        else:
            assert n["role"] in get_args(Role)
            assert n.get("gloss")
    mains = [n for n in st if n.get("main")]
    assert len(mains) == 1 and mains[0]["role"] == "predicate"
    assert not any(n.get("main") for n in walk(st) if n not in st)


@pytest.mark.parametrize("it", FULL, ids=[it["id"] for it in FULL])
def test_node_grammar_declared(it):
    e = it["expect"]
    declared = set(flat(e["grammar_must"])) | set(flat(e["grammar_ok"]))
    for n in walk(e["structure"]):
        assert set(flat(n.get("grammar", []))) <= declared, n


def test_grammar_ids_exist_in_lib():
    lib = grammar_lib_ids()
    if lib is None:
        pytest.skip("khong tim thay grammar_lib.json")
    missing = set()
    for it in ITEMS:
        e = it["expect"]
        missing |= set(flat(e.get("grammar_must", []))) - lib
        missing |= set(flat(e.get("grammar_ok", []))) - lib
    assert not missing


def test_scenario_cases():
    for it in ITEMS:
        e = it["expect"]
        if it["case"] == "#8" and "auto_fix" in it["tags"]:
            assert e["auto_fix"] and e["auto_fix"] != it["text"]
        if it["case"] == "#9":
            assert e["error"]["code"] == "grammar_error" and e["correction"] != it["text"]
        if "invalid_input" in it["tags"]:
            assert e["error"]["reason"] in REASONS
            if e["error"]["reason"] == "too_long":
                assert len(it["text"]) > 100
