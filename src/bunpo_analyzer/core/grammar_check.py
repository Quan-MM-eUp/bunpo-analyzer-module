"""Cau sai / nghi sai ngu phap (buoc 2.4, muc 11.6 file ke hoach + muc 5.3 file kich ban).

LLM tu danh gia cau ngay trong lan goi phan tich (input_check). O day code:
- Tinh `correction_at`: vi tri KY TU cua phan da sua trong cau dung (de to xanh),
  bang cach so cau goc voi cau sua - khong de LLM dem ky tu.
- Kiem tra lai `at` (phan sai trong cau goc, theo TOKEN) bang chinh phep so do:
  neu LLM chi sai cho thi lay vi tri tu phep so.
- Doi sang InputCheck cua khuon AnalysisResult (muc 11.5).
"""

from __future__ import annotations

import difflib
from typing import Optional

from bunpo_analyzer.core.llm_output import LLMInputCheck
from bunpo_analyzer.core.tokenizer import MorphToken, has_kanji, tokenize
from bunpo_analyzer.schema import InputCheck


def diff_ranges(text: str, correction: str) -> Optional[tuple[tuple[int, int], tuple[int, int]]]:
    """((dau, cuoi) trong cau goc, (dau, cuoi) trong cau sua) bao tron moi cho khac nhau."""
    ops = [op for op in difflib.SequenceMatcher(None, text, correction, autojunk=False).get_opcodes() if op[0] != "equal"]
    if not ops:
        return None
    a0, a1 = min(o[1] for o in ops), max(o[2] for o in ops)
    b0, b1 = min(o[3] for o in ops), max(o[4] for o in ops)
    return (a0, a1), (b0, b1)


def _widen_empty(pos: int, toks: list[MorphToken]) -> tuple[int, int]:
    """Chi xoa ky tu (khong co gi moi o cau sua): to xanh tu dung ngay truoc cho xoa.
    本を読みるました -> 本を読みました: to 「読み」."""
    before = [t for t in toks if t.end <= pos and t.pos != "punct"]
    if before:
        return before[-1].start, before[-1].end
    after = [t for t in toks if t.start >= pos and t.pos != "punct"]
    return (after[0].start, after[0].end) if after else (pos, pos)


def correction_at(text: str, correction: str) -> Optional[tuple[int, int]]:
    rng = diff_ranges(text, correction)
    if rng is None:
        return None
    (_, _), (b0, b1) = rng
    toks = tokenize(correction)
    if b0 == b1:
        return _widen_empty(b0, toks)
    # Cat giua mot tu toan kana (です chi khac で) thi to ca tu; tu co chu Han
    # (面白かっ) giu nguyen phan duoi da sua: 面白【かったです】 nhu muc 5.3 file kich ban.
    for t in toks:
        if t.start < b1 and t.end > b0 and not has_kanji(t.surface):
            b0, b1 = min(b0, t.start), max(b1, t.end)
    return b0, b1


def tokens_of_chars(toks: list[MorphToken], a0: int, a1: int) -> Optional[tuple[int, int]]:
    hit = [t.i for t in toks if t.start < max(a1, a0 + 1) and t.end > a0]
    return (hit[0], hit[-1] + 1) if hit else None


def build_input_check(ic: LLMInputCheck, text: str, toks: list[MorphToken]) -> tuple[InputCheck, list[str]]:
    """LLMInputCheck (vi tri token) -> InputCheck cua khuon ket qua. Tra kem ghi chu tu sua."""
    fixes: list[str] = []
    at = tuple(ic.at) if ic.at else None
    corr_at = None
    if ic.status == "error" and ic.correction:
        rng = diff_ranges(text, ic.correction)
        if rng is not None:
            (a0, a1), _ = rng
            diff_tok = tokens_of_chars(toks, a0, a1)
            if diff_tok and (at is None or at[1] <= diff_tok[0] or at[0] >= diff_tok[1]):
                fixes.append(f"at {list(at) if at else None} -> {list(diff_tok)} (theo cho khac giua cau goc va cau sua)")
                at = diff_tok
            corr_at = correction_at(text, ic.correction)
    return InputCheck(status=ic.status, at=at, reason=ic.reason, explain=ic.explain,
                      correction=ic.correction, correction_at=corr_at), fixes
