"""Buoc 1.2: chuan hoa, chan dau vao, tu sua furigana dinh."""

import json
import os
import re
from pathlib import Path

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.core.input_check import (  # noqa: E402
    check_input, count_sentences, fix_furigana, is_japanese, normalize,
)

ITEMS = json.loads((Path(__file__).parent / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]
CASES = [it for it in ITEMS if it["case"] in ("#8", "#14")]


@pytest.mark.parametrize("it", CASES, ids=[it["id"] for it in CASES])
def test_golden_input_cases(it):
    e = it["expect"]
    r = check_input(it["text"])
    want_err = e["error"]["reason"] if e.get("error") and e["error"]["code"] == "invalid_input" else None
    assert (r.error.reason if r.error else None) == want_err
    assert (r.auto_fix.fixed if r.auto_fix else None) == e.get("auto_fix")
    if r.auto_fix:
        assert r.auto_fix.original == it["text"] and r.text == e["auto_fix"]


def test_other_golden_sentences_pass_untouched():
    for it in ITEMS:
        if it["case"] in ("#8", "#14"):
            continue
        r = check_input(it["text"])
        assert r.error is None and r.auto_fix is None, it["id"]


@pytest.mark.parametrize("raw,fixed", [
    ("今いまから行く。", "今から行く。"),
    ("先生せんせいに言いわれた。", "先生に言われた。"),
    ("日本にほんへ行いきたい。", "日本へ行きたい。"),
    ("子供こどもたちが遊あそんでいる。", "子供たちが遊んでいる。"),
    ("毎日まいにち日本語にほんごを勉強べんきょうする。", "毎日日本語を勉強する。"),
    ("早はやく起おきる。", "早く起きる。"),
    ("朝あさ起おきました。", "朝起きました。"),
])
def test_fix_furigana(raw, fixed):
    assert fix_furigana(raw) == fixed


@pytest.mark.parametrize("text", [
    "今います。",  # bo いま thi con す vo nghia
    "朝、起きました。", "私はいつも7時に起きます。",  # き la okurigana
    "何かあったに違いない。", "店によって値段が違います。",
    "この靴は私には小さすぎる。", "多くの研究者が試みたが、成功していない。",
    "母は元気です。", "人々が駅に集まった。", "時々雨が降ります。", "大人は大きい。",
])
def test_no_false_fix(text):
    assert fix_furigana(text) == text


def test_normalize():
    assert normalize("  今夜　たくさんの　宿題が　ある。 ") == "今夜たくさんの宿題がある。"
    assert normalize("ﾃｽﾄです") == "テストです"
    assert normalize("iPhone 15を買った") == "iPhone 15を買った"
    assert normalize("今日は\n雨です") == "今日は雨です"


@pytest.mark.parametrize("text,n", [
    ("今夜たくさんの宿題がある", 1),
    ("今夜たくさんの宿題がある。", 1),
    ("本当？！", 1),
    ("彼は「明日行く。」と言った。", 1),
    ("彼は『「行く。」と言った。』と書いた。", 1),
    ("今日は雨です。傘を持って行きます。", 2),
    ("本当？本当に行くの？", 2),
    ("行こう！みんな！", 2),
])
def test_count_sentences(text, n):
    assert count_sentences(text) == n


def test_is_japanese():
    assert is_japanese("本日休業")
    assert is_japanese("Phân tích 今夜たくさんの宿題がある")
    assert not is_japanese("我们今天去学校了吗")
    assert not is_japanese("Hello! How are you?")


def test_too_long_and_order():
    long_one = "あ" * 101
    assert check_input(long_one).error.reason == "too_long"
    assert check_input(long_one, max_chars=200).error is None
    # Doan dai nhieu cau: nhac gui tung cau truoc
    assert check_input("今日は雨です。" * 20).error.reason == "multiple_sentences"


def _kho_dir():
    base = Path(os.environ.get("BUNPO_DATA_DIR", Path(__file__).resolve().parents[2]))
    return base if (base / "word" / "word_lib.json").exists() else None


@pytest.mark.kho
def test_no_false_fix_on_kho_examples():
    """Cau vi du trong kho deu dung: gan nhu khong duoc sua cau nao (~10 nghin cau, ~15 giay)."""
    base = _kho_dir()
    if base is None:
        pytest.skip("khong tim thay kho du lieu")
    jp = re.compile(r"[぀-ヿ一-鿿]")
    sents = set()

    def add(text):
        for line in str(text).split("\n"):
            line = re.sub(r"^\s*(\d+[\.\)]|[①-⑳]|[A-ZＡ-Ｚ][:：])\s*", "", line.strip())
            for part in re.split(r"(?<=[。！？])", line):
                part = part.strip()
                if len(part) >= 4 and jp.search(part) and not re.search(r"[a-zA-Zà-ỹĐđ]{3,}", part):
                    sents.add(part)

    for x in json.loads((base / "grammar" / "grammar_lib.json").read_text(encoding="utf-8")):
        add(x.get("examples", ""))
    for x in json.loads((base / "word" / "word_lib.json").read_text(encoding="utf-8")):
        add(x.get("example_sentences", ""))
    fixed = [s for s in sents if fix_furigana(normalize(s)) != normalize(s)]
    # 1 cau trong kho tu no da sai chinh ta (書かければならくて) nen cho phep sai so rat nho.
    assert len(fixed) <= max(2, len(sents) // 2000), fixed[:10]


# ---------------- buoc 3.2 ----------------
@pytest.mark.parametrize("raw,text", [
    ("➂病気がなおったら、食べられるようになるでしょう。", "病気がなおったら、食べられるようになるでしょう。"),
    ("①マンガを読みます。", "マンガを読みます。"),
    ("1. 本を読む。", "本を読む。"),
    ("（3）本を読む。", "本を読む。"),
    ("3時に起きる。", "3時に起きる。"),
    ("1つください。", "1つください。"),
])
def test_strip_list_markers(raw, text):
    assert normalize(raw) == text


def test_paren_reading_auto_fix():
    r = check_input("今、会議中（ちゅう）です。")
    assert r.text == "今、会議中です。" and r.auto_fix and r.auto_fix.fixed == r.text
    r = check_input("これ（ペン）です。")
    assert r.auto_fix is None
