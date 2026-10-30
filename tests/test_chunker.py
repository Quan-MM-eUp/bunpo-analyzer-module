"""Prompt v3: gom token thanh cum."""

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.core.chunker import chunk, chunk_span_to_tokens, token_span_to_chunks  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402

PUNCT = re.compile(r"[、。？！?!\s　]")


@pytest.mark.parametrize("text,want", [
    ("田中さんは明日来ると言っていました。", ["田中さんは", "明日", "来ると", "言っていました。"]),
    ("日本へ行くために、お金を貯めています。", ["日本へ", "行くために、", "お金を", "貯めています。"]),
    ("日本語を話すことは難しくないです。", ["日本語を", "話す", "ことは", "難しくないです。"]),
    ("先生に言われたとおりに練習したら、", ["先生に", "言われた", "とおりに", "練習したら、"]),
    ("駅に着いたら、電話してください。", ["駅に", "着いたら、", "電話してください。"]),
    ("電話をする", ["電話を", "する"]),
])
def test_chunks(text, want):
    toks = tokenize(text)
    assert [c.text(toks) for c in chunk(toks)] == want


def test_golden_rows_align_with_chunks():
    """Moi dong trong dap an phai bat dau / ket thuc dung ranh gioi cum (neu khong LLM khong the tra dung)."""
    items = json.loads((Path(__file__).parent / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]

    def leaves(ns):
        for n in ns:
            yield from (leaves(n["children"]) if "group" in n else [n])

    for it in items:
        if "full" not in it["tags"]:
            continue
        toks = tokenize(it["text"])
        bounds, pos = {0}, 0
        for c in chunk(toks):
            pos += len(PUNCT.sub("", c.text(toks)))
            bounds.add(pos)
        pos = 0
        for n in leaves(it["expect"]["structure"]):
            if not n.get("hidden"):
                pos += len(PUNCT.sub("", n["text"]))
                assert pos in bounds, (it["id"], n["text"])


def test_span_conversion_roundtrip_and_punct():
    toks = tokenize("雨が降っているので、今日は出かけません。")
    cs = chunk(toks)
    assert chunk_span_to_tokens(cs, [1, 2], toks)[1] < cs[1].end  # bo dau 、 o cuoi
    for c in cs:
        sp = chunk_span_to_tokens(cs, [c.i, c.i + 1])
        assert token_span_to_chunks(cs, sp) == [c.i, c.i + 1]
    assert chunk_span_to_tokens(cs, [3, 9], toks) is None
