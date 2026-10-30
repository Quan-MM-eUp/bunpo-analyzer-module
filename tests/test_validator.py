"""Buoc 2.3: kiem tra dau ra LLM bang code + goi lai model du phong."""

import copy

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.config import Settings  # noqa: E402
from bunpo_analyzer.core import prompt as P  # noqa: E402
from bunpo_analyzer.core.chunker import chunk  # noqa: E402
from bunpo_analyzer.core.llm import LLMClient, LLMError  # noqa: E402
from bunpo_analyzer.core.llm.base import LLMResult  # noqa: E402
from bunpo_analyzer.core.llm_output import LLMOutput  # noqa: E402
from bunpo_analyzer.core.matcher import get_matcher  # noqa: E402
from bunpo_analyzer.core.pipeline import Prepared, analyze_llm  # noqa: E402
from bunpo_analyzer.core.input_check import check_input  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402
from bunpo_analyzer.core.validator import validate  # noqa: E402

TEXT = P.EX1_TEXT  # 先週姉と作ったケーキはとてもおいしかったです。
TOKS = tokenize(TEXT)
MATCHES = get_matcher().match(TOKS)


def _v(d):
    return validate(LLMOutput.model_validate(d), TOKS, MATCHES, TEXT)


def _ex():
    return copy.deepcopy(P.EX1_OUT)


def _node(d, nid):
    return next(n for n in d["nodes"] if n["id"] == nid)


def test_valid_example():
    rep = _v(_ex())
    assert rep.ok and rep.output is not None and not rep.fixes


def test_examples_all_valid():
    for text, out in P.EXAMPLES:
        toks = tokenize(text)
        assert validate(LLMOutput.model_validate(out), toks, get_matcher().match(toks), text).ok, text


def test_missing_and_overlap():
    d = _ex()
    d["nodes"] = [n for n in d["nodes"] if n["id"] != "r5"]  # bo ケーキは
    rep = _v(d)
    assert not rep.ok and any("khong thuoc dong nao: ケーキは" in e for e in rep.errors)
    d = _ex()
    _node(d, "r5")["span"] = [4, 8]  # chong len r6
    assert any("nam trong ca" in e for e in _v(d).errors)


def test_main_rules():
    d = _ex()
    _node(d, "r6")["main"] = False  # chi 1 vi ngu ngoai cung -> tu dat lai
    rep = _v(d)
    assert rep.ok and any("dat main" in f for f in rep.fixes)
    d = _ex()
    _node(d, "r4")["main"] = True
    assert any("nhieu hon 1" in e for e in _v(d).errors)


def test_parent_and_group_rules():
    d = _ex()
    _node(d, "r2")["parent"] = "r9"
    assert any("parent r9" in e for e in _v(d).errors)
    d = _ex()
    _node(d, "g1")["head"] = 7  # とても: khong ngay sau menh de
    assert any("nhom rel khong dung ngay truoc" in e for e in _v(d).errors)
    d = _ex()
    d["nodes"] = [n for n in d["nodes"] if n["parent"] != "g1"]
    assert any("nhom khong co dong con" in e for e in _v(d).errors)


def test_grammar_fixes():
    d = _ex()
    _node(d, "r6")["grammar"] = [43, 26, 9999]
    rep = _v(d)
    assert rep.ok and 9999 not in _node(rep.output.model_dump(), "r6")["grammar"]
    d = _ex()
    _node(d, "r6")["grammar"] = [26, 26]  # trung nhom vi tri
    assert _node(_v(d).output.model_dump(), "r6")["grammar"] == [26]


def test_input_check_rules():
    d = _ex()
    d["input_check"] = {"status": "error", "at": [8, 11], "reason": None, "explain": "x", "correction": TEXT}
    assert any("giong het" in e for e in _v(d).errors)
    d["input_check"]["correction"] = None
    assert any("thieu correction" in e for e in _v(d).errors)
    d = _ex()
    d["input_check"] = {"status": "suspect", "at": [50, 60], "reason": "r", "explain": None, "correction": None}
    rep = _v(d)
    assert rep.ok and rep.output.input_check.at is None
    d = _ex()
    d["translation"] = None
    assert any("translation" in e for e in _v(d).errors)


# ---------------- goi lai ----------------
class Script:
    name = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def generate(self, messages, output_model, model, timeout_s, max_tokens):
        self.calls.append((model, len(messages)))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(data=output_model.model_validate(item), model=model, prompt_tokens=10, completion_tokens=5)


def _prepared(text=TEXT):
    inp = check_input(text)
    toks = tokenize(inp.text)
    ms = get_matcher().match(toks)
    return Prepared(inp, toks, None, ms, chunk(toks), P.build_messages(inp.text, toks, ms))


def _client(script):
    s = Settings(_env_file=None, openai_api_key="k", llm_model="main", llm_fallback_model="fb", llm_max_retries=0)
    return LLMClient(Script(script), s, retry_delay_s=0)


GOOD = P.fewshot_outputs()[0]  # vi tri theo cum


def _broken():
    d = copy.deepcopy(GOOD)
    d["nodes"] = [n for n in d["nodes"] if n["id"] != "r5"]
    return d


async def test_retry_with_fallback_then_ok():
    c = _client([_broken(), GOOD])
    st = await analyze_llm(_prepared(), c)
    assert st.status == "ok" and len(st.attempts) == 2 and st.attempts[0].errors and not st.attempts[1].errors
    calls = c.provider.calls
    assert calls[0][0] == "main" and calls[1][0] == "fb" and calls[1][1] == calls[0][1] + 2  # kem cau tra loi cu + loi


async def test_structure_failed():
    st = await analyze_llm(_prepared(), _client([_broken(), _broken()]))
    assert st.status == "structure_failed" and st.output is None and len(st.attempts) == 2


async def test_llm_unavailable():
    st = await analyze_llm(_prepared(), _client([LLMError("timeout", "t"), LLMError("timeout", "t")]))
    assert st.status == "llm_unavailable"


async def test_grammar_error_status():
    err = {"input_check": {"status": "error", "at": [1, 2], "reason": None, "explain": "x",
                           "correction": "昨日は寒かったです。"},
           "translation": None, "nodes": [], "reading_fixes": [], "word_meanings": []}
    st = await analyze_llm(_prepared("昨日は寒いでした。"), _client([err]))
    assert st.status == "grammar_error" and st.output.input_check.at == [2, 5]  # doi cum -> token


# ---------------- buoc 2.4 ----------------
from bunpo_analyzer.core.grammar_check import build_input_check, correction_at  # noqa: E402
from bunpo_analyzer.core.llm_output import LLMInputCheck  # noqa: E402


@pytest.mark.parametrize("text,corr,green", [
    ("映画は面白いでした。", "映画は面白かったです。", "かったです"),
    ("本を読みるました。", "本を読みました。", "読み"),
    ("静かいな部屋です。", "静かな部屋です。", "静か"),
    ("私は学生だです。", "私は学生です。", "学生"),
    ("先生に会いたいます。", "先生に会いたいです。", "です"),
    ("駅で行きます。", "駅に行きます。", "に"),
])
def test_correction_at(text, corr, green):
    c0, c1 = correction_at(text, corr)
    assert corr[c0:c1] == green


def test_build_input_check_fixes_wrong_at():
    text = "映画は面白いでした。"
    toks = tokenize(text)
    ic = LLMInputCheck(status="error", at=[0, 1], reason=None, explain="x", correction="映画は面白かったです。")
    out, fixes = build_input_check(ic, text, toks)
    assert "".join(t.surface for t in toks[out.at[0]:out.at[1]]) == "面白いでした" and fixes
    assert out.correction_at == (5, 10)
    ok = LLMInputCheck(status="ok", at=None, reason=None, explain=None, correction=None)
    assert build_input_check(ok, text, toks)[0].correction_at is None


async def test_grammar_error_has_correction_at():
    err = {"input_check": {"status": "error", "at": [1, 2], "reason": None, "explain": "x",
                           "correction": "昨日は寒かったです。"},
           "translation": None, "nodes": [], "reading_fixes": [], "word_meanings": []}
    st = await analyze_llm(_prepared("昨日は寒いでした。"), _client([err]))
    assert st.input_check.correction_at is not None
    c0, c1 = st.input_check.correction_at
    assert "昨日は寒かったです。"[c0:c1] == "かったです"


# ---------------- buoc 3.2: tu va loi khuon nho ----------------
from bunpo_analyzer.core.validator import repair  # noqa: E402


def _out(text, rows, ic="ok"):
    """rows: (id, role, chu, parent, main, hidden) -> LLMOutput vi tri token."""
    toks = tokenize(text)
    pos, k = {}, 0
    for t in toks:
        pos[k] = t.i
        k += len(t.surface)
    pos[k] = len(toks)
    nodes, cur = [], 0
    for rid, role, piece, parent, main, hidden in rows:
        if rid.startswith("g"):
            nodes.append({"id": rid, "type": "group", "parent": parent, "role": None, "kind": role, "span": None,
                          "head": None, "hidden": False, "jp": None, "gloss": "x", "main": False, "grammar": []})
            continue
        span = None
        if piece:
            a = text.index(piece, cur) if not hidden else text.index(piece)
            span = [pos[a], pos[a + len(piece)]]
            cur = a + len(piece) if not hidden else cur
        nodes.append({"id": rid, "type": "row", "parent": parent, "role": role, "kind": None, "span": span, "head": None,
                      "hidden": hidden, "jp": "（私が）" if hidden else None, "gloss": "x", "main": main, "grammar": []})
    d = {"input_check": {"status": ic, "at": None, "reason": None, "explain": None, "correction": None},
         "translation": "x", "nodes": nodes, "reading_fixes": [], "word_meanings": []}
    return LLMOutput.model_validate(d), toks


def _fix(text, rows):
    out, toks = _out(text, rows)
    fixed, notes = repair(out, toks)
    rep = validate(fixed, toks, [], text)
    spans = {n.id: "".join(t.surface for t in toks[n.span[0]:n.span[1]]) if n.span else None for n in rep.output.nodes} \
        if rep.ok else None
    return rep, notes, spans


def test_repair_gap_modifier_to_next():
    rep, notes, sp = _fix("いい風が入るように、窓を大きく開けた。", [
        ("g1", "sub", None, None, False, False), ("r1", "subject", "風が", "g1", False, False),
        ("r2", "predicate", "入るように", "g1", False, False), ("r3", "object", "窓を", None, False, False),
        ("r4", "predicate", "大きく開けた", None, True, False)])
    assert rep.ok and sp["r1"] == "いい風が" and notes


def test_repair_gap_clause_noun_to_prev():
    rep, _, sp = _fix("子どもが遊んでいる間に、夕飯を作ってしまった。", [
        ("g1", "sub", None, None, False, False), ("r1", "subject", "子どもが", "g1", False, False),
        ("r2", "predicate", "遊んでいる", "g1", False, False), ("r3", "object", "夕飯を", None, False, False),
        ("r4", "predicate", "作ってしまった", None, True, False)])
    assert rep.ok and sp["r2"] == "遊んでいる間に"


def test_repair_gap_after_rentaishi():
    rep, _, sp = _fix("この魚、食べれる？", [
        ("r1", "topic", "この", None, False, False), ("r2", "predicate", "食べれる", None, True, False)])
    assert rep.ok and sp["r1"] == "この魚"


def test_repair_leaves_whole_constituent():
    out, toks = _out("ご飯を食べてから、歯を磨きます。", [
        ("r1", "object", "ご飯を", None, False, False), ("r2", "predicate", "食べてから", None, False, False),
        ("r3", "object", "歯を", None, False, False)])
    fixed, _ = repair(out, toks)
    assert not validate(fixed, toks, [], "ご飯を食べてから、歯を磨きます。").ok  # thieu ca vi ngu: goi lai


def test_repair_hidden_span_overlap_parent_main():
    text = "ご飯を食べてから、歯を磨きます。"
    out, toks = _out(text, [
        ("g1", "sub", None, None, False, False), ("r0", "subject", "ご飯", "g1", False, True),  # dong an co span
        ("r1", "object", "ご飯を", "g1", False, False), ("r2", "predicate", "食べてから", "r1", False, False),  # parent = dong
        ("r3", "object", "歯を", None, False, False), ("r4", "predicate", "磨きます", None, False, False)])  # thieu main
    d = out.model_dump()
    d["nodes"][4]["span"] = [5, 7]  # 歯を chong 1 token voi 食べてから? -> tao chong [4,7) vs r2 [2,5)
    d["nodes"][4]["span"] = [4, 8]
    out = LLMOutput.model_validate(d)
    fixed, notes = repair(out, toks)
    rep = validate(fixed, toks, [], text)
    assert rep.ok, rep.errors
    n = {x.id: x for x in rep.output.nodes}
    assert n["r0"].span is None and n["r2"].parent == "g1" and n["r4"].main
    assert n["r3"].span == [5, 8] or n["r3"].span[0] == n["r2"].span[1]


def test_merged_row_and_group_without_predicate():
    text = "日本へ行くために、お金を貯めています。"
    out, toks = _out(text, [
        ("g1", "sub", None, None, False, False), ("r1", "complement", "日本へ行くために", "g1", False, False),
        ("r2", "object", "お金を", None, False, False), ("r3", "predicate", "貯めています", None, True, False)])
    errs = validate(out, toks, [], text).errors
    assert any("vi ngu rieng" in e for e in errs) and any("tach sau 日本へ" in e for e in errs)
    out, toks = _out("彼女は歌が上手です。", [
        ("r1", "topic", "彼女は", None, False, False), ("r2", "predicate", "歌が上手です", None, True, False)])
    assert any("tach sau 歌が" in e for e in validate(out, toks, [], "彼女は歌が上手です。").errors)
    out, toks = _out("そんな気がする。", [("r1", "predicate", "そんな気がする", None, True, False)])
    assert validate(out, toks, [], "そんな気がする。").ok  # thanh ngu


def test_explain_must_not_be_japanese():
    d = _ex()
    d["input_check"] = {"status": "suspect", "at": None, "reason": "「食」と「ベ」が分かれており不自然です。", "explain": None,
                        "correction": None}
    assert any("tieng Nhat" in e for e in _v(d).errors)
    d["input_check"]["reason"] = "Dạng ら抜き (食べれる) thường dùng trong văn nói."
    assert _v(d).ok


def test_background_patterns_dropped_when_other_grammar():
    d = _ex()
    _node(d, "r5")["grammar"] = [15]  # N2のN1 trong cau da co 196, 43, 26
    from bunpo_analyzer.core.matcher import Match

    rep = validate(LLMOutput.model_validate(d), TOKS, MATCHES + [Match(15, 5, 7, 5, 7, (5, 6))], TEXT)
    assert rep.ok and _node(rep.output.model_dump(), "r5")["grammar"] == [] and any("mau nen" in f for f in rep.fixes)


def test_repair_group_predicate_role():
    text = "約束したから、行かないわけにはいかない。"
    out, toks = _out(text, [
        ("g1", "sub", None, None, False, False), ("r1", "adv_reason", "約束したから", "g1", False, False),
        ("r2", "predicate", "行かないわけにはいかない", None, True, False)])
    fixed, notes = repair(out, toks)
    rep = validate(fixed, toks, [], text)
    assert rep.ok and any("-> predicate" in n for n in notes)
    out, toks = _out("子供のとき、よく遊んだ。", [
        ("g1", "sub", None, None, False, False), ("r1", "adv_time", "子供のとき", "g1", False, False),
        ("r2", "adv_manner", "よく", None, False, False), ("r3", "predicate", "遊んだ", None, True, False)])
    fixed, _ = repair(out, toks)
    assert not validate(fixed, toks, [], "子供のとき、よく遊んだ。").ok  # khong co dong tu: de goi lai


def test_repair_roles_by_particle():
    text = "今日は駅に音楽を聞きに行く。"
    out, toks = _out(text, [
        ("r1", "topic", "今日は", None, False, False), ("r2", "adv_place", "駅に", None, False, False),
        ("r3", "adv_manner", "音楽を", None, False, False), ("r4", "predicate", "聞きに行く", None, True, False)])
    fixed, notes = repair(out, toks)
    roles = {n.id: n.role for n in fixed.nodes}
    assert roles == {"r1": "adv_time", "r2": "complement", "r3": "object", "r4": "predicate"}
    out, toks = _out("彼は学校で勉強する。", [
        ("r1", "topic", "彼は", None, False, False), ("r2", "adv_place", "学校で", None, False, False),
        ("r3", "predicate", "勉強する", None, True, False)])
    fixed, notes = repair(out, toks)
    assert {n.id: n.role for n in fixed.nodes}["r1"] == "topic" and not notes
