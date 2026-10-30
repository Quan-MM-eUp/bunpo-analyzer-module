"""Doi vi tri trong dau ra LLM giua so thu tu cum (LLM dung) va so thu tu token (code dung)."""

from __future__ import annotations

from typing import Optional

from bunpo_analyzer.core.chunker import Chunk, chunk_span_to_tokens, token_span_to_chunks, token_to_chunk
from bunpo_analyzer.core.llm_output import LLMOutput
from bunpo_analyzer.core.tokenizer import MorphToken


def _head_token(chunks: list[Chunk], toks: list[MorphToken], c: Optional[int]) -> Optional[int]:
    if c is None or not 0 <= c < len(chunks):
        return None
    ch = chunks[c]
    return next((k for k in range(ch.start, ch.end) if toks[k].pos == "noun"), ch.start)


def to_token_positions(out: LLMOutput, toks: list[MorphToken], chunks: list[Chunk]) -> tuple[LLMOutput, list[str]]:
    """Dau ra LLM (vi tri theo cum) -> vi tri theo token. Tra kem danh sach loi vi tri (cho buoc 2.3)."""
    errors: list[str] = []
    d = out.model_dump()
    for n in d["nodes"]:
        if n["span"] is not None:
            sp = chunk_span_to_tokens(chunks, n["span"], toks)
            if sp is None:
                errors.append(f"{n['id']}: span {n['span']} khong hop le")
            n["span"] = sp
        if n["head"] is not None:
            h = _head_token(chunks, toks, n["head"])
            if h is None:
                errors.append(f"{n['id']}: head {n['head']} khong hop le")
            n["head"] = h
    ic = d["input_check"]
    if ic["at"] is not None:
        at = chunk_span_to_tokens(chunks, ic["at"], toks)
        if at is None:
            errors.append(f"input_check.at {ic['at']} khong hop le")
        ic["at"] = at
    return LLMOutput.model_validate(d), errors


def to_chunk_positions(out: dict, toks: list[MorphToken], chunks: list[Chunk]) -> dict:
    """Nguoc lai (dung cho vi du mau viet theo token). Vi tri phai trung ranh gioi cum."""
    d = LLMOutput.model_validate(out).model_dump()
    m = token_to_chunk(chunks)
    for n in d["nodes"]:
        if n["span"] is not None:
            sp = token_span_to_chunks(chunks, n["span"])
            if sp is None or chunk_span_to_tokens(chunks, sp, toks) != n["span"]:
                raise ValueError(f"{n['id']}: span {n['span']} khong trung ranh gioi cum")
            n["span"] = sp
        if n["head"] is not None:
            n["head"] = m[n["head"]]
    ic = d["input_check"]
    if ic["at"] is not None:
        ic["at"] = token_span_to_chunks(chunks, ic["at"])
    return d
