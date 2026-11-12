"""0.2.1: ngon ngu du phong cho chu lay tu kho va bang tro tu (BUNPO_TEXT_FALLBACK_LANG).

Chatbot Migii dat "en": 13 ngon ngu chua dich kho hien tieng Anh thay vi tieng Viet. Mac dinh "vi"
giu nguyen hanh vi cu (toan bo test cu chay voi mac dinh nay).
"""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.data import Kho
from bunpo_analyzer.core.grammar_detail import grammar_detail
from bunpo_analyzer.core.grammar_meta import short_label
from bunpo_analyzer.core.langs import text_fallback_lang, use_text_fallback
from bunpo_analyzer.core.lookup import _TABLES, table_meaning


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def kho(tmp_path):
    """Kho nho: 252 co ban dich en + ko, 30 chi co ban dich en (ko thieu), 77 khong co ban dich nao."""
    _write(tmp_path / "word" / "word_lib.json", [])
    _write(tmp_path / "grammar" / "grammar_lib.json", [
        {"id": 252, "grammar": "～た　ことが　ある", "pattern": "～たことがある", "level": "N4", "接続": "Vた + ことがある",
         "meaning_vi": "Đã từng…", "examples": "1. この歌は聞いたことがあります。\nTôi từng nghe bài hát này.",
         "explain": "Giải thích.", "label": ["grammar_exper"]},
        {"id": 30, "grammar": "Thể て", "pattern": "て", "level": "N5", "meaning_vi": "Nối câu", "接続": "", "label": []},
        {"id": 77, "grammar": "Mẫu chưa dịch", "pattern": "x", "level": "N3", "meaning_vi": "Chưa dịch", "接続": "",
         "label": []},
    ])
    _write(tmp_path / "grammar" / "grammar_text.en.json", {
        "252": {"name": "Have done", "meaning": "Have done before", "explain": "Explanation.",
                "examples": [{"jp": "この歌は聞いたことがあります。", "tr": "I've heard this song before."}]},
        "30": {"name": "Te-form", "meaning": "Connecting clauses"}})
    _write(tmp_path / "grammar" / "grammar_text.ko.json", {"252": {"name": "~한 적이 있다", "meaning": "~한 적이 있다"}})
    _write(tmp_path / "i18n" / "en.json", {"label": {"grammar_exper": "experience"}})
    _write(tmp_path / "i18n" / "fr.json", {"label": {"grammar_exper": "expérience"}})
    return Kho(tmp_path)


# ---------------- cau hinh ----------------
def test_settings_default_and_validation():
    assert Settings(_env_file=None).text_fallback_lang == "vi"
    assert Settings(_env_file=None, text_fallback_lang=" EN ").text_fallback_lang == "en"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, text_fallback_lang="xx")


def test_context_overrides_and_restores():
    base = text_fallback_lang()
    with use_text_fallback("en"):
        assert text_fallback_lang() == "en"
        with use_text_fallback("ko"):
            assert text_fallback_lang() == "ko"
        assert text_fallback_lang() == "en"
    assert text_fallback_lang() == base


# ---------------- kho ngu phap ----------------
def test_content_lang(kho):
    with use_text_fallback("vi"):  # hanh vi cu
        assert [kho.content_lang(x) for x in ("vi", "en", "ko", "fr", "cn")] == ["vi", "en", "ko", "vi", "vi"]
    with use_text_fallback("en"):
        assert [kho.content_lang(x) for x in ("vi", "en", "ko", "fr", "cn")] == ["vi", "en", "ko", "en", "en"]
    with use_text_fallback("de"):  # ngon ngu du phong chua co ban dich -> tieng Viet, khong loi
        assert kho.content_lang("fr") == "vi"


def test_grammar_text_fallback(kho):
    with use_text_fallback("vi"):
        assert kho.grammar_text(252, "fr")["meaning"] == "Đã từng…"
        assert kho.grammar_text(252, "fr")["lang"] == "vi"
    with use_text_fallback("en"):
        fr = kho.grammar_text(252, "fr")
        assert (fr["meaning"], fr["lang"]) == ("Have done before", "en")
        assert kho.grammar_text(252, "vi")["meaning"] == "Đã từng…"  # nguoi dung tieng Viet khong doi
        assert kho.grammar_text(252, "ko")["meaning"] == "~한 적이 있다"  # ngon ngu da dich giu ban cua minh
        # Ngon ngu da co file ban dich nhung thieu mau nay: giu nhu cu (truong thieu -> tieng Viet)
        assert kho.grammar_text(30, "ko")["meaning"] == "Nối câu"
        # Mau chua dich o ca ngon ngu du phong: tieng Viet, lang = vi
        assert kho.grammar_text(77, "fr")["lang"] == "vi"


def test_short_label_fallback(kho):
    with use_text_fallback("en"):
        assert short_label(252, kho, "fr") == short_label(252, kho, "en")
        assert short_label(252, kho, "vi") == short_label(252, kho, "vi")


def test_grammar_detail_fallback(kho):
    with use_text_fallback("vi"):
        old = grammar_detail(252, "fr", kho)
        assert old.text_lang == "vi" and old.meaning == "Đã từng…"
    with use_text_fallback("en"):
        fr, en = grammar_detail(252, "fr", kho), grammar_detail(252, "en", kho)
        assert fr.lang == "fr" and fr.text_lang == "en"
        assert (fr.meaning, fr.name, fr.explain) == (en.meaning, en.name, en.explain)
        assert fr.examples[0].tr == "I've heard this song before."
        assert fr.labels[0].name == "expérience"  # ten loai mau van theo ngon ngu nguoi dung (i18n)
        vi = grammar_detail(252, "vi", kho)
        assert vi.text_lang == "vi" and vi.meaning == "Đã từng…"


# ---------------- bang tro tu ----------------
ENTRIES = json.loads((_TABLES / "particle_table.json").read_text(encoding="utf-8"))["entries"]
EN = json.loads((_TABLES / "particle_table.en.json").read_text(encoding="utf-8"))
CN = json.loads((_TABLES / "particle_table.cn.json").read_text(encoding="utf-8"))
E = next(e for e in ENTRIES if e["key"] in EN and e["key"] in CN)


def test_table_meaning_fallback():
    with use_text_fallback("vi"):
        assert table_meaning(E, "fr") == E["vi"]  # hanh vi cu
    with use_text_fallback("en"):
        assert table_meaning(E, "fr") == EN[E["key"]]
        assert table_meaning(E, "my") == EN[E["key"]]
        assert table_meaning(E, "cn") == CN[E["key"]]  # da co bang dich rieng -> giu
        assert table_meaning(E, "vi") == E["vi"]  # nguoi dung tieng Viet luon ban goc


def test_table_meaning_all_entries_no_vietnamese_for_fallback_langs():
    # chi chu rieng cua tieng Viet (a, e, o co dau dung chung voi es/pt/fr/pl khong tinh) - nhu VI_ONLY cua check.py
    vi_only = re.compile(r"[ăđơưĂĐƠƯẠ-ỹ]")
    with use_text_fallback("en"):
        for lang in ("fr", "de", "es", "pt", "ru", "pl", "th", "hi", "ne", "my"):
            for e in ENTRIES:
                m = table_meaning(e, lang)
                assert not vi_only.search(m), f"{lang}.{e['key']}: {m}"


# ---------------- ca luot phan tich (analyze_full) ----------------
pytest.importorskip("sudachipy")

from bunpo_analyzer.core import prompt as P  # noqa: E402
from bunpo_analyzer.core.analyzer import analyze_full  # noqa: E402
from bunpo_analyzer.core.llm import LLMClient  # noqa: E402
from bunpo_analyzer.core.pipeline import prepare  # noqa: E402
from tests.test_assemble import kho as kho_ex1  # noqa: E402,F401  (kho nho cho cau EX1, co ban dich en mau 19)
from tests.test_cache import Script  # noqa: E402


def _settings(fb):
    return Settings(_env_file=None, openai_api_key="k", llm_model="main", llm_fallback_model="fb",
                    llm_max_retries=0, cache_backend="none", text_fallback_lang=fb)


async def _run(kho, lang, fb):
    s = _settings(fb)
    return await analyze_full(P.EX1_TEXT, lang, settings=s, kho=kho,
                              client=LLMClient(Script([P.fewshot_outputs()[0]]), s, retry_delay_s=0))


async def test_analyze_full_uses_settings_fallback(kho_ex1):
    a_vi = await _run(kho_ex1, "fr", "vi")
    a_en = await _run(kho_ex1, "fr", "en")
    g_vi = {g.id: g.meaning for g in a_vi.result.grammar}
    g_en = {g.id: g.meaning for g in a_en.result.grammar}
    assert g_vi[19] == "Cùng với." and g_en[19] == "Together with."  # mau co ban dich en
    assert g_en[43] == g_vi[43] == "rất ~"  # mau chua dich o ca en: van tieng Viet
    # Nghia tro tu theo ngon ngu du phong; ngoai lan goi, gia tri cu duoc tra lai
    toks_en = {t.surface: t.meaning for t in a_en.result.tokens if t.meaning_source == "particle_table"}
    toks_vi = {t.surface: t.meaning for t in a_vi.result.tokens if t.meaning_source == "particle_table"}
    assert toks_en and toks_en != toks_vi
    assert text_fallback_lang() == Settings().text_fallback_lang


async def test_analyze_full_vi_user_unchanged(kho_ex1):
    a = await _run(kho_ex1, "vi", "en")
    b = await _run(kho_ex1, "vi", "vi")
    ra, rb = a.result.model_dump(), b.result.model_dump()
    ra.pop("id"), rb.pop("id")
    assert ra == rb


def test_prepare_particle_follows_context(kho_ex1):
    toks_vi = {w.i: w.meaning for w in prepare(P.EX1_TEXT, "fr", kho_ex1).lookup.words
               if w.meaning_source == "particle_table"}
    with use_text_fallback("en"):
        toks_en = {w.i: w.meaning for w in prepare(P.EX1_TEXT, "fr", kho_ex1).lookup.words
                   if w.meaning_source == "particle_table"}
    assert toks_vi.keys() == toks_en.keys() and toks_vi != toks_en
