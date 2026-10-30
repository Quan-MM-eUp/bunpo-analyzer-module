"""Buoc 2.5: ghep AnalysisResult day du (muc 11.5) - khong goi mang."""

import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.config import Settings  # noqa: E402
from bunpo_analyzer.core import prompt as P  # noqa: E402
from bunpo_analyzer.core.analyzer import analyze_full  # noqa: E402
from bunpo_analyzer.core.assemble import assemble, build_tokens  # noqa: E402
from bunpo_analyzer.core.data import Kho  # noqa: E402
from bunpo_analyzer.core.llm import LLMClient, LLMError  # noqa: E402
from bunpo_analyzer.core.llm.base import LLMResult  # noqa: E402
from bunpo_analyzer.core.llm_output import LLMOutput  # noqa: E402
from bunpo_analyzer.core.pipeline import StageResult, prepare  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402
from bunpo_analyzer.schema import AnalysisResult  # noqa: E402


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def kho(tmp_path):
    words = [(1, "先週", "せんしゅう", "tuần trước", "pos_noun"), (2, "姉", "あね", "chị gái", "pos_noun"),
             (3, "作る", "つくる", "làm, chế tạo", "pos_verb"), (4, "ケーキ", "ケーキ", "bánh ngọt", "pos_noun"),
             (5, "とても", "とても", "rất", "pos_adverb"), (6, "おいしい", "おいしい", "ngon", "pos_adjective_i")]
    _write(tmp_path / "word" / "word_lib.json", [
        {"id": i, "word": w, "reading": r, "meaning": m, "level": "N5", "pos": p, "han_viet": ""}
        for i, w, r, m, p in words])
    gram = [(196, "Mệnh đề bổ nghĩa danh từ", "Cách bổ nghĩa cho danh từ bằng mệnh đề."),
            (19, "Trợ từ と", "Cùng với."), (43, "とても", "rất ~"), (26, "Tính từ い (Aイ)", "Quá khứ: Aい → Aかった.")]
    _write(tmp_path / "grammar" / "grammar_lib.json", [
        {"id": i, "grammar": n, "pattern": n, "level": "N5", "meaning_vi": m, "接続": "", "label": []}
        for i, n, m in gram])
    _write(tmp_path / "grammar" / "grammar_text.en.json", {"19": {"name": "Particle と", "meaning": "Together with."}})
    return Kho(tmp_path)


def _prep(kho, text=P.EX1_TEXT, lang="vi"):
    return prepare(text, lang, kho)


def _out(d):
    """Dau ra vi du (vi tri token) -> LLMOutput nhu sau buoc kiem tra."""
    return LLMOutput.model_validate(copy.deepcopy(d))


def _stage(d):
    return StageResult("ok", output=_out(d))


def test_full_result_example(kho):
    p = _prep(kho)
    r, notes = assemble(p, _stage(P.EX1_OUT), kho, "vi", "an_test")
    AnalysisResult.model_validate(r.model_dump())  # dung khuon
    assert r.id == "an_test" and r.translation and r.error is None and r.input_check.status == "ok"
    # thu tu: nhom -> chu ngu an -> cac dong theo token
    assert [n.id for n in r.nodes] == ["g1", "r1", "r2", "r3", "r4", "r5", "r6"]
    g1 = r.nodes[0]
    assert g1.span == (0, 5) and g1.head == 5 and g1.head_text == "ケーキ"
    r1 = r.nodes[1]
    assert r1.hidden and r1.span is None and r1.jp == "（私が）"
    assert [n.id for n in r.nodes if n.main] == ["r6"]
    # mau ngu phap theo thu tu xuat hien, lay tu kho
    assert [g.id for g in r.grammar] == [196, 19, 43, 26]
    g19 = next(g for g in r.grammar if g.id == 19)
    # short_label tu tables/grammar_meta.json (buoc 4.1): "Trợ từ と" -> "と"
    assert (g19.short_label, g19.level, g19.meaning, g19.note) == ("と", "N5", "Cùng với.", None)
    # tokens: nghia + nguon
    tok = {t.surface: t for t in r.tokens}
    assert tok["姉"].meaning == "chị gái" and tok["姉"].meaning_source == "word_lib"
    assert tok["と"].meaning_source == "particle_table"
    assert tok["作っ"].pos_sub == "v1" and tok["作っ"].base == "作る"
    assert tok["。"].meaning is None and tok["。"].meaning_source is None
    assert not notes


def test_lang_en(kho):
    r, _ = assemble(_prep(kho, lang="en"), _stage(P.EX1_OUT), kho, "en")
    g19 = next(g for g in r.grammar if g.id == 19)
    assert (g19.short_label, g19.meaning) == ("と", "Together with.")  # nhan trung lap, dung chung
    g196 = next(g for g in r.grammar if g.id == 196)
    assert g196.short_label == "Mệnh đề bổ nghĩa danh từ"  # nhan tieng Viet, chua co ban dich -> tieng Viet
    g43 = next(g for g in r.grammar if g.id == 43)
    assert g43.meaning == "rất ~"  # chua dich -> tieng Viet


def test_nested_groups_order(kho):
    text, d = P.EX3_TEXT, P.EX3_OUT
    p = _prep(kho, text)
    r, _ = assemble(p, _stage(d), kho, "vi")
    toks = p.tokens
    # moi nhom dung truoc cac node con; node con theo thu tu token
    pos = {n.id: k for k, n in enumerate(r.nodes)}
    for n in r.nodes:
        if n.parent:
            assert pos[n.parent] < pos[n.id]
    rows = [n for n in r.nodes if n.type == "row" and n.span]
    assert [n.span[0] for n in rows] == sorted(n.span[0] for n in rows)
    covered = sorted(i for n in rows for i in range(*n.span))
    assert covered == [t.i for t in toks if t.pos != "punct"]


def test_grammar_error(kho):
    from bunpo_analyzer.core.grammar_check import build_input_check

    p = _prep(kho, P.EX2_TEXT)
    out = _out(P.EX2_OUT)
    ic, _ = build_input_check(out.input_check, p.input.text, p.tokens)
    r, _ = assemble(p, StageResult("grammar_error", output=out, input_check=ic), kho, "vi")
    assert r.error.code == "grammar_error" and not r.nodes and not r.grammar and r.translation is None
    assert r.tokens and r.input_check.status == "error" and r.input_check.correction_at == (4, 9)


@pytest.mark.parametrize("status", ["structure_failed", "llm_unavailable"])
def test_failed_keeps_tokens(kho, status):
    r, _ = assemble(_prep(kho), StageResult(status), kho, "vi")
    assert r.error.code == status and r.tokens and not r.nodes and r.translation is None
    assert r.tokens[1].furigana == [("姉", "あね")]


def test_invalid_input(kho):
    r, _ = assemble(prepare("hello", "vi", kho), None, kho, "vi")
    assert r.error.code == "invalid_input" and not r.tokens


def test_auto_fix_kept(kho):
    p = _prep(kho, "先週せんしゅう姉あねと作つくったケーキはとてもおいしかったです。")
    assert p.input.auto_fix is not None
    r, _ = assemble(p, _stage(P.EX1_OUT), kho, "vi")
    assert r.auto_fix.fixed == P.EX1_TEXT and r.text == P.EX1_TEXT


def test_reading_fix_and_word_meaning(kho):
    toks = tokenize("辛すぎる料理を食べた。")
    p = _prep(kho, "辛すぎる料理を食べた。")
    d = {"input_check": {"status": "ok", "at": None, "reason": None, "explain": None, "correction": None},
         "translation": "x", "nodes": [],
         "reading_fixes": [{"word": "辛い", "reading": "からい"}],
         "word_meanings": [{"word": "料理", "meaning": "món ăn"}, {"word": "食べる", "meaning": "ăn"}]}
    tokens, notes = build_tokens(toks, p.lookup, _out(d))
    t0 = tokens[0]
    assert t0.surface == "辛" and t0.reading == "から" and t0.furigana == [("辛", "から")] and notes
    tok = {t.surface: t for t in tokens}
    assert tok["料理"].meaning == "món ăn" and tok["料理"].meaning_source == "llm"
    assert tok["食べ"].meaning == "ăn"  # khop theo dang goc
    # khong co nghia -> bo nguon llm
    d["word_meanings"] = []
    tokens, _ = build_tokens(toks, p.lookup, _out(d))
    assert {t.surface: t for t in tokens}["料理"].meaning_source is None


# ---------------- analyze_full (LLM gia) ----------------
class Script:
    name = "fake"

    def __init__(self, script):
        self.script = list(script)

    async def generate(self, messages, output_model, model, timeout_s, max_tokens):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(data=output_model.model_validate(item), model=model, prompt_tokens=10,
                         completion_tokens=5, cost_usd=0.001, latency_ms=100)


def _settings():
    return Settings(_env_file=None, openai_api_key="k", llm_model="main", llm_fallback_model="fb", llm_max_retries=0,
                    cache_backend="none")


async def test_analyze_full_ok(kho):
    s = _settings()
    good = P.fewshot_outputs()[0]
    a = await analyze_full(P.EX1_TEXT, "vi", settings=s, kho=kho, client=LLMClient(Script([good]), s, retry_delay_s=0))
    assert a.result.error is None and len(a.result.nodes) == 7 and a.cost_usd == 0.001
    log = a.log_dict()
    assert log["models"] == ["main"] and log["error"] is None


async def test_analyze_full_unavailable(kho):
    s = _settings()
    c = LLMClient(Script([LLMError("timeout", "t"), LLMError("timeout", "t")]), s, retry_delay_s=0)
    a = await analyze_full(P.EX1_TEXT, "vi", settings=s, kho=kho, client=c)
    assert a.result.error.code == "llm_unavailable" and a.result.tokens


async def test_analyze_full_bad_config(kho):
    s = Settings(_env_file=None, llm_provider="nope", cache_backend="none")
    a = await analyze_full(P.EX1_TEXT, "vi", settings=s, kho=kho)
    assert a.result.error.code == "llm_unavailable"


def test_reading_fix_kanji_part_only(kho):
    toks = tokenize("窓が開いている。")
    p = _prep(kho, "窓が開いている。")
    d = {"input_check": {"status": "ok", "at": None, "reason": None, "explain": None, "correction": None},
         "translation": "x", "nodes": [], "reading_fixes": [{"word": "開", "reading": "あ"}], "word_meanings": []}
    tokens, _ = build_tokens(toks, p.lookup, _out(d))
    t = next(t for t in tokens if t.surface.startswith("開"))
    assert t.furigana[0] == ("開", "あ") and t.reading.startswith("あ")
