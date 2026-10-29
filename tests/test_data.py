"""Buoc 1.3: nap kho, chi muc, doc theo ngon ngu."""

import json
import os
import time
from pathlib import Path

import pytest

from bunpo_analyzer.core.data import Kho, clear_kho_cache, get_kho, headword_keys


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def mini(tmp_path):
    """Kho nho, co ban dich tieng Anh gia dinh da dich xong."""
    _write(tmp_path / "word" / "word_lib.json", [
        {"id": 1, "word": "映画", "reading": "えいが", "meaning": "phim, điện ảnh", "level": "N5",
         "pos": "pos_noun", "han_viet": "ÁNH HỌA"},
        {"id": 2, "word": "見る", "reading": "みる", "meaning": "xem, nhìn", "level": "N5", "pos": "pos_verb", "han_viet": ""},
        {"id": 3, "word": "診る", "reading": "みる", "meaning": "khám bệnh", "level": "N3", "pos": "pos_verb", "han_viet": ""},
        {"id": 4, "word": "やたら(に・と)", "reading": "", "meaning": "bừa bãi", "level": "N1", "pos": "pos_adverb", "han_viet": ""},
    ])
    _write(tmp_path / "word" / "word_text.en.json", {"1": {"meaning": "movie, film"}})
    _write(tmp_path / "grammar" / "grammar_lib.json", [
        {"id": 245, "grammar": "～が　ある", "grammar_reading": "", "pattern": "Nがある", "level": "N4",
         "接続": "Nがある", "meaning_vi": "~ có", "explain": "giải thích", "common_mistakes": "", "label": ["grammar_basic"]},
        {"id": 19, "grammar": "Trợ từ と", "grammar_reading": "", "pattern": "Nと", "level": "N5",
         "接続": "N + と", "meaning_vi": "Cùng với", "explain": "", "common_mistakes": "", "label": ["grammar_prt"]},
    ])
    _write(tmp_path / "grammar" / "grammar_text.en.json", {"245": {"name": "N ga aru", "meaning": "there is ~"}})
    _write(tmp_path / "i18n" / "en.json", {"label": {"grammar_basic": "basic grammar"}})
    return tmp_path


def test_indexes(mini):
    k = Kho(mini)
    assert [w.id for w in k.words_by_key("映画")] == [1]
    assert sorted(w.id for w in k.words_by_reading("みる")) == [2, 3]
    assert sorted(w.id for w in k.words_by_reading("ミル")) == [2, 3]  # katakana cung tra duoc
    assert [w.id for w in k.words_by_key("やたらと")] == [4]
    assert k.word(2).pos == "verb" and k.word(4).pos == "adv"
    assert k.grammar(245).conn == "Nがある" and k.grammar("19").labels == ("grammar_prt",)
    assert k.word(99) is None and k.grammar(99) is None and k.words_by_key("無い語") == []


def test_lang_fallback(mini):
    k = Kho(mini)
    assert k.langs == ("en", "vi")
    assert k.word_text(1, "vi") == {"meaning": "phim, điện ảnh", "han_viet": "ÁNH HỌA", "lang": "vi"}
    # Co ban dich: dung ban dich, khong tra Han Viet
    assert k.word_text(1, "en") == {"meaning": "movie, film", "han_viet": None, "lang": "en"}
    # Thieu id trong file dich / thieu ca file ngon ngu: dung tieng Viet
    assert k.word_text(2, "en")["meaning"] == "xem, nhìn" and k.word_text(2, "en")["lang"] == "vi"
    assert k.word_text(1, "ko")["meaning"] == "phim, điện ảnh"
    g = k.grammar_text(245, "en")
    assert (g["name"], g["meaning"], g["explain"], g["lang"]) == ("N ga aru", "there is ~", "giải thích", "en")
    assert k.grammar_text(19, "en")["meaning"] == "Cùng với"
    assert k.label_name("grammar_basic", "en") == "basic grammar"
    assert k.label_name("grammar_basic", "vi") is None


def test_version_changes_with_content(mini):
    v1 = Kho(mini).version
    assert v1 == Kho(mini).version
    _write(mini / "word" / "word_text.en.json", {"1": {"meaning": "movie"}})
    assert Kho(mini).version != v1


def test_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        Kho(tmp_path)


def test_get_kho_cached(mini):
    clear_kho_cache()
    assert get_kho(mini) is get_kho(str(mini))
    clear_kho_cache()


@pytest.mark.parametrize("raw,keys", [
    ("堪能<な/する>", {"堪能"}),
    ("きまり(が)悪い", {"きまり悪い", "きまりが悪い"}),
    ("足元(足下)", {"足元", "足下"}),
    ("(それ)にもかかわらず", {"にもかかわらず", "それにもかかわらず"}),
    ("やたら(に・と)", {"やたら", "やたらに", "やたらと"}),
    ("ぐったり[と]する", {"ぐったりする", "ぐったりとする"}),
    ("[お]しまい", {"しまい", "おしまい"}),
    ("一概に[〜ない]", {"一概に"}),
    ("～について", {"について"}),
])
def test_headword_keys(raw, keys):
    assert set(headword_keys(raw)) == keys


def _kho_dir():
    base = Path(os.environ.get("BUNPO_DATA_DIR", Path(__file__).resolve().parents[2]))
    return base if (base / "word" / "word_lib.json").exists() else None


@pytest.mark.kho
def test_real_kho():
    base = _kho_dir()
    if base is None:
        pytest.skip("khong tim thay kho du lieu")
    t0 = time.perf_counter()
    k = Kho(base)
    load_s = time.perf_counter() - t0
    assert len(k.words) > 12000 and len(k.grammars) > 1600
    assert load_s < 5
    assert any(w.word == "見る" for w in k.words_by_key("見る"))
    assert k.grammar(245) is not None and k.grammar_text(245)["meaning"]
    t0 = time.perf_counter()
    for _ in range(1000):
        k.words_by_key("映画"), k.words_by_reading("えいが"), k.grammar(245), k.word_text(1), k.grammar_text(245)
    per_call_ms = (time.perf_counter() - t0) / 5000 * 1000
    assert per_call_ms < 1, per_call_ms
