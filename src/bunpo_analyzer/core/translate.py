""""Dich nhe" (buoc 2.6, muc 12.5 file ke hoach).

Cau truc cau tieng Nhat khong phu thuoc ngon ngu nguoi hoc. Khi cau da co trong
cache (bang ngon ngu A) va nguoi dung ngon ngu B mo, chi goi LLM dich phan chu:
ban dich cau, gloss tung dong / nhom, ly do nghi sai, giai thich loi, nghia tu
chua co trong kho. Cau truc (nodes, span, mau ngu phap) giu nguyen.
"""

from __future__ import annotations

import copy
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bunpo_analyzer.core.llm.base import Message
from bunpo_analyzer.core.llm_output import LLMOutput, WordMeaning
from bunpo_analyzer.core.prompt import LANG_NAMES
from bunpo_analyzer.core.tokenizer import MorphToken

TRANSLATE_VERSION = "2"  # trong khoa cache cua ban theo ngon ngu

SYSTEM = """You localize the text of an existing grammar analysis of ONE Japanese sentence for a learner app. Return JSON only, following the schema.

You get the sentence, its parts with their current text in the SOURCE language, and the TARGET language. Write every text in the TARGET language only (Japanese words may be quoted):
- translation: one natural translation of the whole sentence (null if the source has none).
- glosses: one item per part id given, same ids. gloss = short meaning of that part IN THIS SENTENCE, like the source gloss.
- reason / explain: translate the given text; null if not given.
- word_meanings: for each word under "need meaning", a short dictionary-style meaning.
Base the meaning on the Japanese, using the source text only as a guide. Do not add or remove parts.
NEVER copy the Japanese sentence or the SOURCE text as the answer: every field must be newly written in the TARGET language."""


class NodeGloss(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    gloss: str


class LLMTextOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    translation: Optional[str] = Field(description="ban dich ca cau; null neu ban goc khong co")
    glosses: list[NodeGloss]
    reason: Optional[str]
    explain: Optional[str]
    word_meanings: list[WordMeaning]


_KIND = {"rel": "relative clause", "sub": "subordinate clause", "quote": "quote", "nominal": "nominal clause"}


def _part_text(n, toks: list[MorphToken], out: LLMOutput) -> str:
    if n.type == "row":
        if n.hidden:
            return n.jp or ""
        return "".join(t.surface for t in toks[n.span[0]:n.span[1]])
    from bunpo_analyzer.core.validator import group_token_span

    sp = group_token_span(out.nodes, n.id)
    return "".join(t.surface for t in toks[sp[0]:sp[1]]) if sp else ""


def build_messages(text: str, toks: list[MorphToken], out: LLMOutput, src_lang: str, lang: str,
                   need_meaning: list[str]) -> list[Message]:
    src = LANG_NAMES.get(src_lang, src_lang)
    lines = [f"sentence: {text}", f"SOURCE language: {src}", f"TARGET language: {LANG_NAMES.get(lang, lang)}",
             f"translation ({src}): {out.translation if out.translation else 'null'}"]
    if out.nodes:
        lines.append("parts (id | type | Japanese | source gloss):")
        for n in out.nodes:
            typ = (("hidden " if n.hidden else "") + (n.role or "")) if n.type == "row" else _KIND.get(n.kind or "", "group")
            lines.append(f"  {n.id} | {typ} | {_part_text(n, toks, out)} | {n.gloss or ''}")
    ic = out.input_check
    lines.append(f"reason ({src}): {ic.reason or 'null'}")
    lines.append(f"explain ({src}): {ic.explain or 'null'}")
    lines.append(f"need meaning: {', '.join(need_meaning) if need_meaning else 'none'}")
    tgt = LANG_NAMES.get(lang, lang)
    lines.append(f"Write translation, glosses, reason, explain and meanings in {tgt}, not in Japanese or {src}.")
    return [Message("system", SYSTEM), Message("user", "\n".join(lines))]


_KANA = re.compile(r"[ぁ-ゖァ-ヺー]")
_KANJI = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3005]")
_SKIP = re.compile(r"[\s\W\d_]")


def jp_ratio(text: str, lang: str) -> float:
    """Ti le ky tu tieng Nhat. Tieng Trung (cn, tw) dung chu Han nen chi tinh kana."""
    chars = [c for c in text if not _SKIP.fullmatch(c)]
    if not chars:
        return 0.0
    jp = sum(1 for c in chars if _KANA.fullmatch(c) or (lang not in ("cn", "tw") and _KANJI.fullmatch(c)))
    return jp / len(chars)


def _wrong_lang(new: Optional[str], old: Optional[str], lang: str) -> bool:
    """Chep nguyen ban goc, hoac phan lon la tieng Nhat (LLM chep lai cau)."""
    if not new:
        return False
    return (old is not None and new.strip() == old.strip()) or jp_ratio(new, lang) > 0.5


def merge(out: LLMOutput, tr: LLMTextOutput, lang: str = "vi") -> tuple[Optional[LLMOutput], list[str]]:
    """Ghep phan chu moi vao cau truc cu. Tra (None, loi) neu thieu phan bat buoc hoac sai ngon ngu."""
    errors: list[str] = []
    d = copy.deepcopy(out.model_dump())
    if out.translation and not (tr.translation or "").strip():
        errors.append("thieu translation")
    elif out.translation and _wrong_lang(tr.translation, out.translation, lang):
        errors.append("translation khong viet bang ngon ngu dich (chep cau goc / ban cu)")
    d["translation"] = tr.translation if out.translation else None
    gl = {g.id: g.gloss for g in tr.glosses if g.gloss.strip()}
    missing = [n["id"] for n in d["nodes"] if n["gloss"] and n["id"] not in gl]
    if missing:
        errors.append("thieu gloss: " + ", ".join(missing))
    olds = {n["id"]: n["gloss"] for n in d["nodes"]}
    bad = [i for i, g in gl.items() if _wrong_lang(g, olds.get(i), lang) and jp_ratio(g, lang) > 0.5]
    copied = [i for i, g in gl.items() if olds.get(i) and g.strip() == olds[i].strip()]
    if bad or len(copied) > max(1, len(gl) // 2):  # mot vai gloss trung (ten rieng, so) thi chap nhan
        errors.append("gloss khong viet bang ngon ngu dich: " + ", ".join(bad or copied))
    for n in d["nodes"]:
        n["gloss"] = gl.get(n["id"]) if n["gloss"] else None
    ic = d["input_check"]
    for k, val in (("reason", tr.reason), ("explain", tr.explain)):
        if ic[k]:
            if not val:
                errors.append(f"thieu {k}")
            elif _wrong_lang(val, ic[k], lang):
                errors.append(f"{k} khong viet bang ngon ngu dich")
            ic[k] = val or None
    d["word_meanings"] = [m.model_dump() for m in tr.word_meanings]
    if errors:
        return None, errors
    return LLMOutput.model_validate(d), []
