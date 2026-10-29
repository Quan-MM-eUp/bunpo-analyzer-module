"""Buoc 1.4: tra nghia tu."""

import json
import os
import random
from pathlib import Path

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.core.data import Kho  # noqa: E402
from bunpo_analyzer.core.input_check import check_input  # noqa: E402
from bunpo_analyzer.core.lookup import apply_to_tokens, lookup  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def mini(tmp_path):
    words = [
        (1, "映画", "えいが", "phim, điện ảnh", "pos_noun"),
        (2, "見る", "みる", "xem, nhìn", "pos_verb"),
        (3, "鳴る", "なる", "reo, kêu", "pos_verb"),
        (4, "要る", "いる", "cần", "pos_verb"),
        (5, "子ども", "こども", "trẻ con", "pos_noun"),
        (6, "話す", "はなす", "nói", "pos_verb"),
        (7, "練習する", "れんしゅうする", "luyện tập", "pos_verb"),
        (8, "手", "て", "tay", "pos_noun"),
        (9, "付ける", "つける", "gắn, đính", "pos_verb"),
        (10, "日本語", "にほんご", "tiếng Nhật", "pos_noun"),
    ]
    _write(tmp_path / "word" / "word_lib.json", [
        {"id": i, "word": w, "reading": r, "meaning": m, "level": "N5", "pos": p, "han_viet": ""}
        for i, w, r, m, p in words])
    _write(tmp_path / "word" / "word_text.en.json", {"1": {"meaning": "movie"}})
    _write(tmp_path / "grammar" / "grammar_lib.json", [])
    return Kho(tmp_path)


def _m(kho, text, lang="vi"):
    toks = tokenize(text)
    res = lookup(toks, kho, lang)
    return {t.surface: (w.meaning, w.meaning_source, w.via) for t, w in zip(toks, res.words)}, res


def test_particles_and_key(mini):
    got, res = _m(mini, "映画を見た。")
    assert got["映画"] == ("phim, điện ảnh", "word_lib", "key")
    assert got["見"][:2] == ("xem, nhìn", "word_lib")
    assert got["を"][1] == "particle_table" and "tân ngữ" in got["を"][0]
    assert got["た"][0].startswith("quá khứ")
    assert got["。"] == (None, "none", "")
    assert res.misses == []


def test_lang(mini):
    got, _ = _m(mini, "映画を見た。", "en")
    assert got["映画"][0] == "movie"  # co ban dich
    assert got["見"][0] == "xem, nhìn"  # chua dich -> tieng Viet


def test_reading_needs_matching_kanji(mini):
    got, res = _m(mini, "子供が上手になる。")
    assert got["子供"][:2] == ("trẻ con", "word_lib")  # 子ども: chu 子 co trong 子供
    assert got["なる"][0] != "reo, kêu"  # khong nhan 鳴る
    assert got["なる"][2] == "core" and "なる" in res.misses
    got, _ = _m(mini, "猫がいる。")
    assert got["いる"][0] != "cần"  # khong nhan 要る


def test_potential_and_ra_nuki_use_norm(mini):
    got, _ = _m(mini, "日本語が話せる。")
    assert got["話せる"][0] == "nói"
    got, _ = _m(mini, "映画が見れる？")
    assert got["見れる"][0] == "xem, nhìn"


def test_multi_token_and_after_te(mini):
    got, _ = _m(mini, "毎日練習して、日本語を見ている。")
    assert got["練習"][:3] == ("luyện tập", "word_lib", "multi") and got["し"][2] == "multi"
    assert got["いる"][1] == "particle_table" and "ている" in got["いる"][0]


def test_short_kana_not_matched_to_kanji(mini):
    got, _ = _m(mini, "気をつけて。")
    assert got["つけ"][0] == "gắn, đính"  # dong tu kana du dai: nhan
    toks = tokenize("それでも、て")
    assert all(w.meaning != "tay" for w in lookup(toks, mini).words)


def test_unknown_and_numbers(mini):
    got, res = _m(mini, "鈴木さんは3回来た。")
    assert got["鈴木"] == (None, "llm", "")
    assert got["さん"][1] == "particle_table"
    assert got["3"][1] == "none"
    assert "鈴木" in res.misses


def test_apply_to_tokens(mini):
    toks = tokenize("映画を見た。")
    s = apply_to_tokens(toks, lookup(toks, mini))
    assert s[0].meaning == "phim, điện ảnh" and s[0].meaning_source == "word_lib"
    assert s[-1].meaning is None and s[-1].meaning_source is None


def _kho_dir():
    base = Path(os.environ.get("BUNPO_DATA_DIR", Path(__file__).resolve().parents[2]))
    return base if (base / "word" / "word_lib.json").exists() else None


def _coverage(kho, texts):
    tot = hit = 0
    for tx in texts:
        r = check_input(tx)
        if r.error:
            continue
        toks = tokenize(r.text)
        for t, w in zip(toks, lookup(toks, kho).words):
            if t.pos == "punct" or w.meaning_source == "none":
                continue
            tot += 1
            hit += w.meaning_source != "llm"
    return hit / tot


@pytest.mark.kho
def test_coverage_real_kho():
    base = _kho_dir()
    if base is None:
        pytest.skip("khong tim thay kho du lieu")
    kho = Kho(base)
    items = json.loads((Path(__file__).parent / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]
    assert _coverage(kho, [it["text"] for it in items if not it["expect"].get("error")]) >= 0.95
    words = json.loads((base / "word" / "word_lib.json").read_text(encoding="utf-8"))
    ex = [e["example"] for x in words for e in x.get("example_sentences") or []]
    random.seed(1)
    assert _coverage(kho, random.sample(ex, 500)) >= 0.93
    # Artifact: nghia tu kho
    toks = tokenize("昨日友達と見た映画はとても面白かったです。")
    got = {t.surface: w for t, w in zip(toks, lookup(toks, kho).words)}
    assert got["映画"].meaning == "phim, điện ảnh" and got["面白かっ"].meaning_source == "word_lib"
