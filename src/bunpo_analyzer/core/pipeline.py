"""Chay cac buoc truoc va lan goi LLM cho mot cau.

- prepare(): kiem tra dau vao, tach tu, tra tu, do mau, dung prompt (buoc 1.x, 2.2).
- analyze_llm(): goi LLM, kiem tra bang code, goi lai model du phong khi sai (buoc 2.3).
Buoc 2.5 (core/assemble.py) ghep ket qua thanh AnalysisResult day du.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from bunpo_analyzer.core.canon import canonicalize
from bunpo_analyzer.core.chunker import Chunk, chunk
from bunpo_analyzer.core.data import Kho, get_kho
from bunpo_analyzer.core.input_check import InputResult, check_input
from bunpo_analyzer.core.llm import LLMClient, LLMError
from bunpo_analyzer.core.llm.base import LLMResult, Message
from bunpo_analyzer.core.llm_output import LLMOutput
from bunpo_analyzer.core.lookup import LookupResult, lookup
from bunpo_analyzer.core.matcher import GrammarMatcher, Match, get_matcher
from bunpo_analyzer.core.postprocess import to_token_positions
from bunpo_analyzer.core.prompt import build_messages
from bunpo_analyzer.core.tokenizer import MorphToken, tokenize
from bunpo_analyzer.core.validator import Report, repair, validate
from bunpo_analyzer.core.grammar_check import build_input_check
from bunpo_analyzer.schema import InputCheck


@dataclass
class Prepared:
    input: InputResult
    tokens: list[MorphToken] = field(default_factory=list)
    lookup: Optional[LookupResult] = None
    matches: list[Match] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    lang: str = "vi"


def prepare(raw: str, lang: str = "vi", kho: Optional[Kho] = None,
            matcher: Optional[GrammarMatcher] = None, max_chars: int = 100) -> Prepared:
    inp = check_input(raw, max_chars=max_chars)
    if inp.error:
        return Prepared(inp, lang=lang)
    kho = kho or get_kho()
    matcher = matcher or get_matcher()
    toks = tokenize(inp.text)
    lk = lookup(toks, kho, lang)
    ms = canonicalize(matcher.match(toks))  # mau trung -> mau chuan (docs/mau_trung.md)
    return Prepared(inp, toks, lk, ms, chunk(toks), build_messages(inp.text, toks, ms, kho, lk, lang), lang)


async def run_llm(p: Prepared, client: LLMClient, use_fallback: bool = False) -> LLMResult[LLMOutput]:
    """Ket qua tho cua LLM (vi tri theo CUM)."""
    return await client.generate(p.messages, LLMOutput, use_fallback=use_fallback)


def token_positions(p: Prepared, raw: LLMOutput) -> tuple[LLMOutput, list[str]]:
    """Doi vi tri theo cum -> theo token; tra kem loi vi tri (buoc 2.3 dung de quyet dinh goi lai)."""
    return to_token_positions(raw, p.tokens, p.chunks)


# ---------------- buoc 2.3: kiem tra + goi lai ----------------
StageStatus = Literal["ok", "grammar_error", "structure_failed", "llm_unavailable"]


@dataclass
class Attempt:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    latency_ms: int
    cost_usd: float
    errors: list[str]


@dataclass
class StageResult:
    status: StageStatus
    output: Optional[LLMOutput] = None  # vi tri theo token, da kiem tra (None neu that bai)
    report: Optional[Report] = None
    input_check: Optional[InputCheck] = None  # khuon ket qua (11.5), co correction_at (buoc 2.4)
    attempts: list[Attempt] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def cost_usd(self) -> float:
        return round(sum(a.cost_usd for a in self.attempts), 6)

    @property
    def latency_ms(self) -> int:
        return sum(a.latency_ms for a in self.attempts)


def _retry_messages(p: Prepared, raw: LLMOutput, errors: list[str]) -> list[Message]:
    import json

    note = ("Your previous answer has these problems:\n- " + "\n- ".join(errors[:10]) +
            "\nPositions are CHUNK numbers. Return the whole corrected JSON.")
    return p.messages + [Message("assistant", json.dumps(raw.model_dump(), ensure_ascii=False)),
                         Message("user", note)]


async def analyze_llm(p: Prepared, client: LLMClient) -> StageResult:
    """Goi model chinh -> kiem tra; loi nang thi goi model du phong (manh hon) kem danh sach loi.

    Van loi -> structure_failed. Khong goi duoc model nao -> llm_unavailable.
    """
    res = StageResult("structure_failed")
    messages = p.messages
    raw: Optional[LLMOutput] = None
    for use_fallback in (False, True):
        try:
            r = await client.generate(messages, LLMOutput, use_fallback=use_fallback)
        except LLMError as e:
            if res.attempts:  # da co ket qua sai khuon truoc do -> coi la that bai cau truc
                res.error = str(e)
                return res
            return StageResult("llm_unavailable", attempts=res.attempts, error=str(e))
        raw = r.data
        out, pos_errors = token_positions(p, raw)
        out, repaired = repair(out, p.tokens) if not pos_errors else (out, [])
        rep = validate(out, p.tokens, p.matches, p.input.text, pos_errors, p.lang)
        rep.fixes[:0] = repaired
        res.attempts.append(Attempt(r.model, r.prompt_tokens, r.completion_tokens, r.cached_tokens,
                                    r.latency_ms, r.cost_usd, rep.errors))
        res.report = rep
        if rep.ok:
            status: StageStatus = "grammar_error" if rep.output.input_check.status == "error" else "ok"
            res.status, res.output = status, rep.output
            res.input_check, ic_fixes = build_input_check(rep.output.input_check, p.input.text, p.tokens)
            rep.fixes.extend(ic_fixes)
            return res
        messages = _retry_messages(p, raw, rep.errors)
    return res
