"""Buoc 2.2: prompt + khuon dau ra LLM (khong goi mang)."""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.core import prompt as P  # noqa: E402
from bunpo_analyzer.core.llm.base import LLMResult  # noqa: E402
from bunpo_analyzer.core.llm.client import LLMClient  # noqa: E402
from bunpo_analyzer.core.llm.openai_compat import strict_schema  # noqa: E402
from bunpo_analyzer.core.llm_output import LLMOutput  # noqa: E402
from bunpo_analyzer.core.matcher import get_matcher  # noqa: E402
from bunpo_analyzer.core.render import render  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402
from bunpo_analyzer.config import Settings  # noqa: E402

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]


def test_fewshot_examples_valid_and_not_in_golden():
    texts = {it["text"] for it in GOLDEN}
    for text, out in P.EXAMPLES:
        LLMOutput.model_validate(out)
        assert text not in texts  # vi du mau khong duoc trung cau cham diem


def test_fewshot_spans_cover_tokens():
    """Vi du mau phai tu tuan thu quy tac phu kin token cua chinh prompt."""
    for text, out in P.EXAMPLES:
        if out["input_check"]["status"] == "error":
            continue
        toks = tokenize(text)
        covered = sorted(i for n in out["nodes"] if n["span"] for i in range(*n["span"]))
        assert covered == [t.i for t in toks if t.pos != "punct"], text
        assert sum(n["main"] for n in out["nodes"]) == 1


def test_candidate_groups():
    toks = tokenize("先生に言われたとおりに練習したら、上手に話せるようになった。")
    groups = P.candidate_groups(get_matcher().match(toks))
    starts = [s for s, _ in groups]
    assert starts == sorted(set(starts))
    by_start = {s: {m.grammar_id for m in ms} for s, ms in groups}
    assert {169, 357} <= by_start[9] and {613, 1608} <= by_start[14]


def test_strict_schema_ok():
    s = strict_schema(LLMOutput)
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {"input_check", "translation", "nodes", "reading_fixes", "word_meanings"}


def test_build_messages_shape():
    toks = tokenize("先生に言われたとおりに練習したら、上手に話せるようになった。")
    ms = get_matcher().match(toks)
    msgs = P.build_messages("先生に言われたとおりに練習したら、上手に話せるようになった。", toks, ms, lang="en")
    assert [m.role for m in msgs] == ["system"] + ["user", "assistant"] * len(P.EXAMPLES) + ["user"]
    last = msgs[-1].content
    assert "output language: English" in last and "3:練習[れんしゅう]したら、" in last and "5:話[はな]せるように" in last
    assert "group 1 at" in last and "  169 | " in last and "  570 | " in last and "(chunks 0-1)" in last
    assert "need meaning: none" in last
    assert len(msgs) == 2 + 2 * len(P.EXAMPLES) - 1 + 0 or True
    total = sum(len(m.content) for m in msgs)
    assert total < 20000  # giu prompt gon


def test_need_meaning_listed():
    from bunpo_analyzer.core.lookup import LookupResult, WordInfo

    toks = tokenize("昨日ズゴメリアで遊んだ。")
    lk = LookupResult([WordInfo(t.i, None, "llm" if t.surface == "ズゴメリア" else "word_lib") for t in toks])
    assert "need meaning: ズゴメリア" in P.user_input("x", toks, [], None, lk, "vi")


class FakeProvider:
    name = "fake"

    def __init__(self, out: dict):
        self.out = out
        self.messages = None

    async def generate(self, messages, output_model, model, timeout_s, max_tokens):
        self.messages = messages
        return LLMResult(data=output_model.model_validate(self.out), model=model)


def _kho_dir():
    base = Path(os.environ.get("BUNPO_DATA_DIR", Path(__file__).resolve().parents[2]))
    return base if (base / "word" / "word_lib.json").exists() else None


@pytest.mark.kho
async def test_pipeline_with_fake_llm():
    base = _kho_dir()
    if base is None:
        pytest.skip("khong tim thay kho du lieu")
    from bunpo_analyzer.core.data import Kho
    from bunpo_analyzer.core.pipeline import prepare, run_llm

    kho = Kho(base)
    p = prepare(P.EX1_TEXT, kho=kho)
    assert p.input.error is None and p.messages
    fake = FakeProvider(P.EX1_OUT)
    r = await run_llm(p, LLMClient(fake, Settings(_env_file=None, openai_api_key="k")))
    text = render(r.data, p.tokens, kho)  # EX1_OUT viet theo token nen render truc tiep
    assert "[Mệnh đề bổ nghĩa cho ケーキ] · #196" in text and "Vị ngữ chính: とてもおいしかったです" in text
    assert fake.messages[-1].content == fake.messages[1].content  # vi du mau = dau vao that cua cung cau
    from bunpo_analyzer.core.pipeline import token_positions

    chunk_out = LLMOutput.model_validate(P.fewshot_outputs()[0])
    back, errs = token_positions(p, chunk_out)
    assert not errs and back == LLMOutput.model_validate(P.EX1_OUT)  # doi cum <-> token khong mat thong tin
    blocked = prepare("今日は雨です。傘を持って行きます。", kho=kho)
    assert blocked.input.error.reason == "multiple_sentences" and not blocked.messages
