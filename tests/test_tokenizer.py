"""Buoc 1.1: tach tu, tu loai, furigana, vi tri ky tu."""

import json
from pathlib import Path

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.core.tokenizer import kata_to_hira, split_furigana, tokenize  # noqa: E402

# Dap an lay tu artifact da duyet: (mat chu, tu loai, furigana)
ARTIFACT = {
    "今夜たくさんの宿題がある。": [
        ("今夜", "noun", [("今夜", "こんや")]), ("たくさん", "noun", None), ("の", "prt", None),
        ("宿題", "noun", [("宿題", "しゅくだい")]), ("が", "prt", None), ("ある", "verb", None),
        ("。", "punct", None)],
    "昨日友達と見た映画はとても面白かったです。": [
        ("昨日", "noun", [("昨日", "きのう")]), ("友達", "noun", [("友達", "ともだち")]),
        ("と", "prt", None), ("見", "verb", [("見", "み")]), ("た", "aux", None),
        ("映画", "noun", [("映画", "えいが")]), ("は", "prt", None), ("とても", "adv", None),
        ("面白かっ", "adj", [("面白", "おもしろ"), ("かっ", None)]), ("た", "aux", None),
        ("です", "aux", None), ("。", "punct", None)],
    "先生に言われたとおりに練習したら、上手に話せるようになった。": [
        ("先生", "noun", [("先生", "せんせい")]), ("に", "prt", None),
        ("言わ", "verb", [("言", "い"), ("わ", None)]), ("れ", "aux", None), ("た", "aux", None),
        ("とおり", "noun", None), ("に", "prt", None), ("練習", "noun", [("練習", "れんしゅう")]),
        ("し", "verb", None), ("たら", "aux", None), ("、", "punct", None),
        ("上手", "adj", [("上手", "じょうず")]), ("に", "prt", None),
        ("話せる", "verb", [("話", "はな"), ("せる", None)]), ("よう", "aux", None),
        ("に", "prt", None), ("なっ", "verb", None), ("た", "aux", None), ("。", "punct", None)],
}


@pytest.mark.parametrize("text", list(ARTIFACT))
def test_artifact_sentences(text):
    toks = tokenize(text)
    got = [(t.surface, t.pos, t.furigana if any(r for _, r in t.furigana) else None) for t in toks]
    want = [(s, p, f) for s, p, f in ARTIFACT[text]]
    assert got == want


def test_base_lemma_and_groups():
    toks = {t.surface: t for t in tokenize("先生に言われたとおりに練習したら、上手に話せるようになった。")}
    assert toks["言わ"].base == "言う" and toks["言わ"].verb_group == 1
    assert toks["し"].base == "する" and toks["し"].verb_group == 3
    assert toks["なっ"].base == "なる"
    assert toks["話せる"].base == "話せる"  # V kha nang -> V goc xu ly o buoc 1.4
    assert toks["上手"].adj_type == "na"
    toks = {t.surface: t for t in tokenize("昨日友達と見た映画はとても面白かったです。")}
    assert toks["見"].base == "見る" and toks["見"].verb_group == 2
    assert toks["面白かっ"].base == "面白い" and toks["面白かっ"].adj_type == "i"
    assert toks["とても"].lemma == "とても"


def test_schema_token():
    t = tokenize("映画を見た。")
    s = [x.to_schema().model_dump(exclude_none=True) for x in t]
    assert s[0] == {"i": 0, "surface": "映画", "base": "映画", "reading": "えいが", "pos": "noun",
                    "furigana": [("映画", "えいが")]}
    assert s[2]["pos_sub"] == "v2" and s[2]["base"] == "見る"
    assert s[-1] == {"i": 4, "surface": "。", "pos": "punct"}


def test_offsets_with_spaces():
    text = "今夜　たくさんの 宿題がある。"
    for t in tokenize(text):
        assert text[t.start:t.end] == t.surface


def test_unknown_and_katakana():
    toks = {t.surface: t for t in tokenize("昨日ズゴメリアでコーヒーを飲んだ。")}
    assert toks["ズゴメリア"].is_unknown and toks["ズゴメリア"].pos == "noun"
    assert toks["ズゴメリア"].reading is None
    assert toks["コーヒー"].furigana == [("コーヒー", None)]
    assert toks["コーヒー"].reading == "こーひー"


def test_compounds_and_preferred_readings():
    got = [(t.surface, t.reading) for t in tokenize("私は明日図書館で日本人の友達と富士山の話をした。")]
    assert ("私", "わたし") in got and ("明日", "あした") in got
    assert ("図書館", "としょかん") in got and ("日本人", "にほんじん") in got
    assert ("富士山", "ふじさん") in got
    assert ("日本", "にほん") in [(t.surface, t.reading) for t in tokenize("日本へ行く。")]


def test_hearsay_sou_is_aux():
    toks = {t.surface: t.pos for t in tokenize("明日雨が降るそうです。")}
    assert toks["そう"] == "aux"


@pytest.mark.xfail(reason="Doc theo ngu canh: tu dien chon つら/ひら; se de LLM kiem tra o buoc 2.2", strict=True)
def test_context_readings_known_limit():
    got = {t.surface: t.reading for t in tokenize("この料理は辛すぎます。窓が開いている。")}
    assert got["辛"] == "から" and got["開い"] == "あい"


def test_demonstrative_and_suffix_adj():
    toks = {t.surface: t for t in tokenize("あの人の本は読みやすい。")}
    assert toks["あの"].pos == "adj"
    assert toks["やすい"].pos == "adj" and toks["やすい"].adj_type == "i"


def test_na_adjective_and_no():
    toks = tokenize("いろいろな国の料理をたくさん食べた。")
    got = {t.surface: (t.pos, t.adj_type) for t in toks}
    assert got["いろいろ"] == ("adj", "na") and got["な"] == ("prt", None)
    assert got["たくさん"][0] == "adv"


def test_repeat_mark_and_ra_nuki():
    toks = tokenize("人々が駅に集まった。")
    assert toks[0].furigana == [("人々", "ひとびと")]
    assert [t.surface for t in tokenize("この魚、食べれる？")][3:5] == ["食べ", "れる"]


def test_split_furigana_helpers():
    assert kata_to_hira("センセイ") == "せんせい"
    assert split_furigana("お茶", "おちゃ") == [("お", None), ("茶", "ちゃ")]
    assert split_furigana("取り扱い", "とりあつかい") == [("取", "と"), ("り", None), ("扱", "あつか"), ("い", None)]
    assert split_furigana("ABC", "えーびーしー") == [("ABC", None)]
    # Khong khop duoc thi gan ca tu
    assert split_furigana("明日", "あす") == [("明日", "あす")]


def test_golden_set_tokenizes_cleanly():
    items = json.loads((Path(__file__).parent / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]
    for it in items:
        text = it["text"]
        toks = tokenize(text)
        assert toks, it["id"]
        for t in toks:
            assert text[t.start:t.end] == t.surface, it["id"]
            assert "".join(p for p, _ in t.furigana) == (t.surface if t.pos != "punct" else ""), it["id"]


def test_pos_sub():
    got = {t.surface: t.pos_sub for t in tokenize("先生に言われたとおりに練習したら、上手に話せるようになった。")}
    assert got["言わ"] == "v1" and got["し"] == "v3" and got["なっ"] == "v1"
    assert got["上手"] == "adj_na" and got["先生"] is None and got["に"] is None
    got = {t.surface: t.pos_sub for t in tokenize("昨日来た友達は面白かった。")}
    assert got["来"] == "v3" and got["面白かっ"] == "adj_i"
