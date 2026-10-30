"""Ghep ket qua day du AnalysisResult (buoc 2.5, muc 11.5 file ke hoach).

Dau vao: Prepared (tach tu, tra tu, do mau) + StageResult (LLM da kiem tra).
Khong goi LLM, khong doc mang: ham thuan, test duoc bang dau ra gia.

- tokens: tu bo tach tu + nghia (word_lib / bang tro tu); sua cach doc theo
  `reading_fixes`, dien nghia LLM cho tu chua co trong kho (`word_meanings`).
- nodes: sap xep theo cay (nhom truoc, dong chu ngu an dau nhom, roi theo token);
  nhom co span tinh tu dong con; nhom rel co head_text.
- grammar: cac mau duoc gan, lay tu kho: nhan ngan, cap, nghia (nguyen van, muc 12.10).
- Cau sai ro rang (grammar_error): chi co tokens + input_check + error.
- structure_failed / llm_unavailable: phan khong can AI (tokens co furigana, nghia).
"""

from __future__ import annotations

import uuid
from typing import Optional

from bunpo_analyzer.core.data import Kho
from bunpo_analyzer.core.grammar_meta import short_label
from bunpo_analyzer.core.llm_output import LLMNode, LLMOutput
from bunpo_analyzer.core.lookup import apply_to_tokens
from bunpo_analyzer.core.tokenizer import MorphToken, has_kanji, kata_to_hira, split_furigana
from bunpo_analyzer.core.validator import group_token_span
from bunpo_analyzer.schema import AnalysisResult, ErrorInfo, GrammarItem, InputCheck, Node, Token

def new_id() -> str:
    return "an_" + uuid.uuid4().hex[:12]


# ---------------- tokens ----------------
def _kana_tail(s: str) -> str:
    k = len(s)
    while k > 0 and not has_kanji(s[k - 1]):
        k -= 1
    return s[k:]


def _surface_reading(t: MorphToken, word: str, reading: str) -> Optional[str]:
    """Cach doc moi cho mat chu cua token. LLM co the dua mat chu (辛) hoac dang goc (辛い)."""
    reading = kata_to_hira(reading)
    if word == t.surface:
        return reading
    rest = t.surface[len(word):]
    if word and t.surface.startswith(word) and rest and not has_kanji(rest):
        # chi dua phan chu Han: 開/あ cho mat chu 開い -> あい
        return reading + kata_to_hira(rest)
    if word != t.base:
        return None
    # 辛い/からい -> goc chu Han 辛/から -> mat chu 辛 (+ duoi kana cua mat chu)
    tail = _kana_tail(word)
    if tail and not reading.endswith(tail):
        return None
    stem = reading[: len(reading) - len(tail)] if tail else reading
    if not stem:
        return None
    return stem + _kana_tail(t.surface)


def build_tokens(toks: list[MorphToken], p_lookup, out: Optional[LLMOutput]) -> tuple[list[Token], list[str]]:
    """Tra kem ghi chu nhung gi da sua (de ghi log)."""
    tokens = apply_to_tokens(toks, p_lookup) if p_lookup is not None else [t.to_schema() for t in toks]
    notes: list[str] = []
    if out is None:
        return _clean_llm_source(tokens), notes
    for fx in out.reading_fixes:
        hit = False
        for t in toks:
            if t.pos == "punct" or not has_kanji(t.surface):
                continue
            r = _surface_reading(t, fx.word.strip(), fx.reading.strip())
            if r and r != t.reading:
                tokens[t.i] = tokens[t.i].model_copy(update={"reading": r, "furigana": split_furigana(t.surface, r)})
                notes.append(f"doc {t.surface}: {t.reading} -> {r}")
                hit = True
        if not hit:
            notes.append(f"bo reading_fix {fx.word}/{fx.reading} (khong khop token)")
    meanings = {m.word.strip(): m.meaning.strip() for m in out.word_meanings if m.meaning and m.meaning.strip()}
    for t in toks:
        tk = tokens[t.i]
        if tk.meaning_source == "llm" and not tk.meaning:
            m = meanings.get(t.surface) or meanings.get(t.base)
            if m:
                tokens[t.i] = tk.model_copy(update={"meaning": m})
    return _clean_llm_source(tokens), notes


def _clean_llm_source(tokens: list[Token]) -> list[Token]:
    """Tu chua co trong kho ma LLM cung khong cho nghia: khong ghi nguon."""
    return [t.model_copy(update={"meaning_source": None}) if t.meaning_source == "llm" and not t.meaning else t
            for t in tokens]


# ---------------- nodes ----------------
def _head_text(toks: list[MorphToken], head: int) -> str:
    """Cum danh tu bat dau tu head: 映画, 映画館, 田中さん."""
    end = head + 1
    while end < len(toks) and toks[end].pos == "noun":
        end += 1
    return "".join(t.surface for t in toks[head:end])


def build_nodes(out: LLMOutput, toks: list[MorphToken]) -> list[Node]:
    raw = out.nodes
    kids: dict[Optional[str], list[LLMNode]] = {}
    for n in raw:
        kids.setdefault(n.parent, []).append(n)
    gspan = {n.id: group_token_span(raw, n.id) for n in raw if n.type == "group"}

    def start(n: LLMNode) -> int:
        if n.type == "group":
            return (gspan.get(n.id) or (10**6, 0))[0]
        return -1 if n.hidden else n.span[0]

    ordered: list[LLMNode] = []

    def walk(pid: Optional[str]) -> None:
        for n in sorted(kids.get(pid, []), key=start):
            ordered.append(n)
            if n.type == "group":
                walk(n.id)

    walk(None)
    nodes: list[Node] = []
    for n in ordered:
        if n.type == "row":
            nodes.append(Node(
                id=n.id, type="row", parent=n.parent, role=n.role,
                span=None if n.hidden else tuple(n.span), grammar=list(n.grammar),
                jp=n.jp if n.hidden else None, gloss=n.gloss, main=n.main, hidden=n.hidden,
            ))
        else:
            head = n.head if n.kind == "rel" else None
            nodes.append(Node(
                id=n.id, type="group", parent=n.parent, kind=n.kind, span=gspan.get(n.id),
                grammar=list(n.grammar), gloss=n.gloss, head=head,
                head_text=_head_text(toks, head) if head is not None else None,
            ))
    return nodes


# ---------------- grammar ----------------
def build_grammar(nodes: list[Node], kho: Kho, lang: str) -> list[GrammarItem]:
    items: list[GrammarItem] = []
    seen: set[int] = set()
    for n in nodes:
        for gid in n.grammar:
            if gid in seen:
                continue
            seen.add(gid)
            g = kho.grammar(gid)
            if g is None:
                continue
            txt = kho.grammar_text(gid, lang)
            # short_label: kho chua co, sinh boi scripts/build_grammar_meta.py (buoc 4.1)
            label = short_label(gid, kho, lang) or txt.get("name") or g.name or None
            # note: cho leader (12.10), huong de xuat bo o ban 1 -> de trong.
            items.append(GrammarItem(id=gid, short_label=label, level=g.level, meaning=txt.get("meaning"), note=None))
    return items


# ---------------- ghep ----------------
def assemble(p, stage, kho: Optional[Kho], lang: str, result_id: Optional[str] = None) -> tuple[AnalysisResult, list[str]]:
    """p: pipeline.Prepared, stage: pipeline.StageResult | None (None khi dau vao loi).

    Tra (AnalysisResult, ghi chu da sua) - ghi chu dung de ghi log, khong tra cho app.
    """
    rid = result_id or new_id()
    inp = p.input
    if inp.error is not None:
        return AnalysisResult(id=rid, lang=lang, text=inp.text or inp.original, error=inp.error), []

    base = dict(id=rid, lang=lang, text=inp.text, auto_fix=inp.auto_fix)
    status = stage.status
    out = stage.output if status in ("ok", "grammar_error") else None
    tokens, notes = build_tokens(p.tokens, p.lookup, out)

    if status in ("structure_failed", "llm_unavailable"):
        reason = "quota" if stage.error and "[quota]" in stage.error else None  # het ngan sach LLM
        return AnalysisResult(**base, tokens=tokens, error=ErrorInfo(code=status, reason=reason)), notes

    ic = stage.input_check or InputCheck()
    if status == "grammar_error":
        return AnalysisResult(**base, tokens=tokens, input_check=ic, error=ErrorInfo(code="grammar_error")), notes

    nodes = build_nodes(out, p.tokens)
    return AnalysisResult(
        **base, translation=out.translation, tokens=tokens, nodes=nodes,
        grammar=build_grammar(nodes, kho, lang), input_check=ic,
    ), notes
