"""In ket qua LLM thanh cay chu de nguoi doc doi chieu voi artifact (khong dung cho app)."""

from __future__ import annotations

from typing import Optional

from bunpo_analyzer.core.data import Kho
from bunpo_analyzer.core.llm_output import LLMNode, LLMOutput
from bunpo_analyzer.core.tokenizer import MorphToken

ROLE = {"subject": "Chủ ngữ", "topic": "Chủ đề", "object": "Tân ngữ", "complement": "Bổ ngữ",
        "predicate": "Vị ngữ", "adv_time": "TN thời gian", "adv_place": "TN nơi chốn",
        "adv_manner": "TN cách thức", "adv_reason": "TN lý do"}
KIND = {"rel": "Mệnh đề bổ nghĩa", "sub": "Vế phụ", "quote": "Trích dẫn", "nominal": "Danh từ hoá"}


def span_text(toks: list[MorphToken], span: Optional[list[int]]) -> str:
    if not span or len(span) != 2:
        return "?"
    return "".join(t.surface for t in toks[span[0]:span[1]])


def render(out: LLMOutput, toks: list[MorphToken], kho: Optional[Kho] = None) -> str:
    def gname(ids: list[int]) -> str:
        if not ids:
            return ""
        names = []
        for i in ids:
            g = kho.grammar(i) if kho else None
            names.append(f"#{i} {g.name if g else ''}".strip())
        return " · " + "; ".join(names)

    ic = out.input_check
    lines = [f"input_check: {ic.status}"]
    if ic.status != "ok":
        lines.append(f"  at: {span_text(toks, ic.at)} | {ic.reason or ic.explain or ''}")
        if ic.correction:
            lines.append(f"  correction: {ic.correction}")
    if out.translation:
        lines.append(f"Dịch: {out.translation}")
    children: dict[Optional[str], list[LLMNode]] = {}
    for n in out.nodes:
        children.setdefault(n.parent, []).append(n)

    def walk(parent: Optional[str], depth: int) -> None:
        for n in children.get(parent, []):
            pad = "  " * depth
            if n.type == "group":
                head = f" cho {toks[n.head].surface}" if n.head is not None and 0 <= n.head < len(toks) else ""
                lines.append(f"{pad}- [{KIND.get(n.kind or '', n.kind)}{head}]{gname(n.grammar)}")
                walk(n.id, depth + 1)
            else:
                role = "Vị ngữ chính" if n.main else ROLE.get(n.role or "", n.role or "?")
                if n.hidden:
                    role += " (ẩn)"
                jp = n.jp if n.hidden else span_text(toks, n.span)
                lines.append(f"{pad}- {role}: {jp} — {n.gloss or ''}{gname(n.grammar)}")

    walk(None, 0)
    for f in out.reading_fixes:
        lines.append(f"Sửa cách đọc: {f.word} → {f.reading}")
    for w in out.word_meanings:
        lines.append(f"Nghĩa bổ sung: {w.word} = {w.meaning}")
    return "\n".join(lines)
