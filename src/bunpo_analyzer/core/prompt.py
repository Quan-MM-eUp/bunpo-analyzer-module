"""Dung prompt cho lan goi LLM phan tich cau (buoc 2.2, muc 3.4 file ke hoach).

Mot lan goi tra ca: kiem tra cau (input_check), ban dich, cau truc cau (nodes),
gan mau ngu phap (chi chon trong ung vien cua bo luat), sua cach doc chu Han theo
ngu canh, nghia cho tu chua co trong kho.

Doi noi dung prompt thi tang PROMPT_VERSION (nam trong khoa cache, muc 3.6).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from bunpo_analyzer.core.chunker import Chunk, chunk, token_to_chunk
from bunpo_analyzer.core.data import Kho
from bunpo_analyzer.core.llm.base import Message
from bunpo_analyzer.core.lookup import LookupResult
from bunpo_analyzer.core.matcher import GrammarMatcher, Match
from bunpo_analyzer.core.tokenizer import MorphToken, has_kanji

# v2: ung vien gom theo vi tri (moi nhom chon toi da 1 id), them vi du cau phuc,
# vi du mau dung lai dung pipeline that (khong viet tay dau vao).
# v3: LLM chia cau theo CUM (core/chunker.py) thay vi token; them luat ve vế phụ / trích dẫn.
# v4: cum gop danh tu サ変 + する (練習したら); vi du mau doi theo.
# v5: cum gop V + ために.
PROMPT_VERSION = "9"

LANG_NAMES = {
    "vi": "Vietnamese", "en": "English", "cn": "Simplified Chinese", "tw": "Traditional Chinese (Taiwan)",
    "ko": "Korean", "fr": "French", "de": "German", "es": "Spanish", "pt": "Portuguese", "ru": "Russian",
    "pl": "Polish", "id": "Indonesian", "th": "Thai", "hi": "Hindi", "ne": "Nepali", "my": "Burmese",
}

SYSTEM = """You analyze ONE Japanese sentence for a learner app. Return JSON only, following the schema.

INPUT: the sentence split into numbered CHUNKS (a content word with its particles/endings; [reading] after kanji words), grammar candidates found by rules (grouped by position), the output language, and words that need a dictionary meaning. All positions (span, head, at) are CHUNK numbers.

1. input_check (decide first)
- "error": ONLY for a clear, unambiguous mistake in conjugation, particle or vocabulary (e.g. 寒いでした, 読みるました, 静かいな). Give at = [first chunk, last chunk + 1) of the wrong part, explain = one short sentence in the output language that shows the correct form (do NOT name the verb group or adjective type unless you are certain; e.g. 読む is group 1, not irregular), correction = the whole corrected sentence keeping the SAME meaning and tense. Then translation = null and nodes = [].
- "suspect": natural but non-standard or uncertain usage (ら抜き like 食べれる, very casual speech, archaic style). Give at and a short reason written ONLY in the output language (Japanese words may be quoted), and still analyze fully.
- "ok": otherwise. Casual omissions (particle dropped, ？ questions) are ok. Writing a word in hiragana/katakana instead of kanji (くすりをのむ, みずをのみます) is NEVER an error or suspect. When unsure between error and suspect, choose suspect.

2. translation: one natural translation of the whole sentence in the output language.

3. nodes: the sentence structure as a FLAT list.
- row = one constituent made of one or more consecutive chunks. span = [first chunk, last chunk + 1). Every chunk belongs to exactly one row; rows never overlap and follow sentence order.
- role, decided by the particle at the end of the row: subject (が, or an omitted subject), topic (は), object (を), complement (に/へ/と/から/まで/より, agent of a passive; also で when it marks a means; the row 駅に / 日本へ marking a destination is complement, not adv_place), adv_place (で marking where an action happens), adv_time (time words, also with は/も: 今日は, 明日は → adv_time, not topic), adv_manner (manner/frequency words, ～に/～く adverbs, とおりに), adv_reason, predicate (the verb/adjective/noun+です that ends a clause, with all its endings).
- Number words and noun modifiers stay in the row of the noun they modify: たくさんの宿題が, 会議の資料を.
- group = a clause. kind:
  rel: clause modifying the noun right after it (見た映画, 言われたとおり). head = chunk of that noun; the noun is NOT in the group.
  sub: subordinate clause whose last chunk ends in たら, ば, と, ので, から, ために, ながら, のに, て、 (any length, even a single chunk such as 降っているので). The clause's last row is its predicate: 練習したら, 行くために, 聞きながら.
  quote: what is said/thought before と言う/と思う; the quote's predicate row keeps と (来ると); 言っていました is the main predicate outside the group.
  nominal: clause made into a noun by こと/の/かどうか (日本語を話す before こと; 彼が来るかどうか).
  A group has span = null; its child rows carry the spans. Groups nest (a rel inside a sub: parent = that sub group).
- A row is ONE constituent: it never has が/を/へ in the middle followed by a verb or adjective. 日本へ行くために = 日本へ | 行くために; 音楽を聞きながら = 音楽を | 聞きながら; 歌が上手です = 歌が | 上手です.
- Exactly one row has main = true: the predicate of the whole sentence, at top level (parent = null). Every group contains its own predicate row.
- Add a hidden subject row (hidden = true, span = null, jp like （私が）) only where the omitted subject helps understanding, as the first child of its clause.
- gloss: short meaning of that part IN THIS SENTENCE, in the output language. Groups get a gloss of the whole clause.

4. grammar: candidates are listed in groups by position. From EACH group choose AT MOST ONE id (often none): the one that best names what the learner should notice there (the most specific; if equal, the lowest JLPT level). Put it on the row or group where it appears; a clause-level pattern (rel, たら, ので, ために...) goes on its group. Never use ids that are not listed. Skip basic particles (は/が/を/に/の/で/と as plain case markers) and plain です/ます unless they are the main point of the sentence. Background patterns (Vます/ません/ました conjugation, NをV, N2のN1, このN/そのN/あのN, NがV) are used ONLY when the sentence has no other grammar point.

5. reading_fixes: readings in [ ] come from a dictionary and may be wrong in context (辛[つら]すぎる should be から, 開[ひら]いている should be あ). List only wrong ones: word = the kanji word as written in the chunk, reading = hiragana of that word.

6. word_meanings: for each word under "need meaning", a short dictionary-style meaning in the output language. Otherwise [].

Use null for fields that do not apply (role on groups, kind/head on rows, jp on visible rows)."""

# Vi du mau (few-shot): co y KHONG dung cau trong bo cau kiem thu de khong lam lech ket qua cham.
# Dau vao cua vi du duoc dung bang chinh pipeline (fewshot_inputs) nen luon cung dinh dang.
# Dau ra vi du viet theo vi tri TOKEN cho de doc; fewshot_outputs() doi sang vi tri CUM.
EX1_TEXT = "先週姉と作ったケーキはとてもおいしかったです。"
EX1_OUT = {
    "input_check": {"status": "ok", "at": None, "reason": None, "explain": None, "correction": None},
    "translation": "Cái bánh tuần trước tôi làm cùng chị gái rất ngon.",
    "nodes": [
        {"id": "g1", "type": "group", "parent": None, "role": None, "kind": "rel", "span": None, "head": 5,
         "hidden": False, "jp": None, "gloss": "cái bánh (mà) tuần trước tôi làm cùng chị gái", "main": False, "grammar": [196]},
        {"id": "r1", "type": "row", "parent": "g1", "role": "subject", "kind": None, "span": None, "head": None,
         "hidden": True, "jp": "（私が）", "gloss": "tôi", "main": False, "grammar": []},
        {"id": "r2", "type": "row", "parent": "g1", "role": "adv_time", "kind": None, "span": [0, 1], "head": None,
         "hidden": False, "jp": None, "gloss": "tuần trước", "main": False, "grammar": []},
        {"id": "r3", "type": "row", "parent": "g1", "role": "complement", "kind": None, "span": [1, 3], "head": None,
         "hidden": False, "jp": None, "gloss": "cùng chị gái", "main": False, "grammar": [19]},
        {"id": "r4", "type": "row", "parent": "g1", "role": "predicate", "kind": None, "span": [3, 5], "head": None,
         "hidden": False, "jp": None, "gloss": "đã làm", "main": False, "grammar": []},
        {"id": "r5", "type": "row", "parent": None, "role": "topic", "kind": None, "span": [5, 7], "head": None,
         "hidden": False, "jp": None, "gloss": "cái bánh", "main": False, "grammar": []},
        {"id": "r6", "type": "row", "parent": None, "role": "predicate", "kind": None, "span": [7, 11], "head": None,
         "hidden": False, "jp": None, "gloss": "(đã) rất ngon", "main": True, "grammar": [43, 26]},
    ],
    "reading_fixes": [],
    "word_meanings": [],
}

EX2_TEXT = "昨日は寒いでした。"
EX2_OUT = {
    "input_check": {"status": "error", "at": [2, 5], "reason": None,
                    "explain": "Tính từ い chia quá khứ ở chính tính từ: 寒い → 寒かった, không dùng でした.",
                    "correction": "昨日は寒かったです。"},
    "translation": None, "nodes": [], "reading_fixes": [], "word_meanings": [],
}

EX3_TEXT = "母に頼まれたとおりに部屋を掃除したら、弟が手伝ってくれた。"


def _n(id, type, parent, *, role=None, kind=None, span=None, head=None, hidden=False, jp=None, gloss=None,
       main=False, grammar=()):
    return {"id": id, "type": type, "parent": parent, "role": role, "kind": kind, "span": span, "head": head,
            "hidden": hidden, "jp": jp, "gloss": gloss, "main": main, "grammar": list(grammar)}


EX3_OUT = {
    "input_check": {"status": "ok", "at": None, "reason": None, "explain": None, "correction": None},
    "translation": "Khi tôi dọn phòng đúng như mẹ nhờ thì em trai đã giúp tôi.",
    "nodes": [
        _n("g1", "group", None, kind="sub", gloss="khi tôi dọn phòng đúng như mẹ nhờ", grammar=[169]),
        _n("r1", "row", "g1", role="subject", hidden=True, jp="（私が）", gloss="tôi"),
        _n("g2", "group", "g1", kind="rel", head=5, gloss="(điều) mẹ nhờ", grammar=[196]),
        _n("r2", "row", "g2", role="complement", span=[0, 2], gloss="bởi mẹ"),
        _n("r3", "row", "g2", role="predicate", span=[2, 5], gloss="được nhờ", grammar=[229]),
        _n("r4", "row", "g1", role="adv_manner", span=[5, 7], gloss="đúng như", grammar=[570]),
        _n("r5", "row", "g1", role="object", span=[7, 9], gloss="căn phòng"),
        _n("r6", "row", "g1", role="predicate", span=[9, 12], gloss="khi đã dọn"),  # 掃除したら: mot cum
        _n("r7", "row", None, role="subject", span=[13, 15], gloss="em trai"),
        _n("r8", "row", None, role="predicate", span=[15, 19], gloss="đã giúp (cho tôi)", main=True, grammar=[209]),
    ],
    "reading_fixes": [],
    "word_meanings": [],
}

EXAMPLES = ((EX1_TEXT, EX1_OUT), (EX2_TEXT, EX2_OUT), (EX3_TEXT, EX3_OUT))


def chunk_line(toks: list[MorphToken], chunks: list[Chunk]) -> str:
    parts = []
    for c in chunks:
        txt = ""
        for t in toks[c.start:c.end]:
            if has_kanji(t.surface) and t.furigana:
                txt += "".join(seg + (f"[{rd}]" if rd else "") for seg, rd in t.furigana)  # 作[つく]った
            else:
                txt += t.surface
        parts.append(f"{c.i}:{txt}")
    return " ".join(parts)


def candidate_groups(matches: list[Match]) -> list[tuple[int, list[Match]]]:
    """Gom ung vien theo token bat dau cua phan mau (core_start): moi nhom LLM chon toi da 1 id."""
    groups: dict[int, dict[int, Match]] = {}
    for m in matches:
        groups.setdefault(m.core_start, {}).setdefault(m.grammar_id, m)
    return [(start, list(g.values())) for start, g in sorted(groups.items())]


def candidate_lines(matches: list[Match], toks: list[MorphToken], kho: Optional[Kho],
                    chunks: Optional[list[Chunk]] = None) -> list[str]:
    chunks = chunks or chunk(toks)
    t2c = token_to_chunk(chunks)
    lines = []
    for k, (start, ms) in enumerate(candidate_groups(matches), 1):
        end = max(m.core_end for m in ms)
        text = "".join(t.surface for t in toks[start:end])
        c0, c1 = t2c.get(start, 0), t2c.get(end - 1, 0)
        where = f"chunk {c0}" if c0 == c1 else f"chunks {c0}-{c1}"
        lines.append(f"group {k} at 「{text}」 ({where}):")
        for m in ms:
            g = kho.grammar(m.grammar_id) if kho else None
            name = g.name if g else m.rule_name
            level = (g.level if g else "") or ""
            conn = (g.conn if g else "").replace("\n", " ")
            if len(conn) > 70:
                conn = conn[:70] + "…"
            lines.append(f"  {m.grammar_id} | {name} | {level} | {conn} | 「{m.text(toks)}」")
    return lines


def need_meaning(lookup: Optional[LookupResult], toks: list[MorphToken]) -> list[str]:
    if lookup is None:
        return []
    return list(dict.fromkeys(toks[w.i].surface for w in lookup.words if w.meaning_source == "llm"))


def user_input(text: str, toks: list[MorphToken], matches: list[Match], kho: Optional[Kho],
               lookup: Optional[LookupResult], lang: str) -> str:
    chunks = chunk(toks)
    cands = candidate_lines(matches, toks, kho, chunks)
    need = need_meaning(lookup, toks)
    return "\n".join([
        f"sentence: {text}",
        f"output language: {LANG_NAMES.get(lang, lang)}",
        f"chunks: {chunk_line(toks, chunks)}",
        "grammar candidates (choose at most one id per group):" + ("\n" + "\n".join(cands) if cands else " none"),
        f"need meaning: {', '.join(need) if need else 'none'}",
    ])


def fewshot_inputs(kho: Optional[Kho], matcher: Optional[GrammarMatcher] = None) -> list[str]:
    """Dau vao cua cac vi du mau, dung bang pipeline that (tieng Viet)."""
    from bunpo_analyzer.core.matcher import get_matcher
    from bunpo_analyzer.core.tokenizer import tokenize

    matcher = matcher or get_matcher()
    out = []
    for text, _ in EXAMPLES:
        toks = tokenize(text)
        out.append(user_input(text, toks, matcher.match(toks), kho, None, "vi"))
    return out


@lru_cache(maxsize=1)
def fewshot_outputs() -> tuple[dict, ...]:
    """Vi du mau viet theo token (de doc, de kiem tra) -> doi sang vi tri theo cum cho LLM."""
    from bunpo_analyzer.core.postprocess import to_chunk_positions
    from bunpo_analyzer.core.tokenizer import tokenize

    out = []
    for text, ex in EXAMPLES:
        toks = tokenize(text)
        out.append(to_chunk_positions(ex, toks, chunk(toks)))
    return tuple(out)


@lru_cache(maxsize=4)
def _fewshot_cached(kho_version: str, kho_id: int) -> tuple[str, ...]:
    return tuple(fewshot_inputs(_KHO_REF.get(kho_id)))


_KHO_REF: dict[int, Optional[Kho]] = {}


def build_messages(text: str, toks: list[MorphToken], matches: list[Match], kho: Optional[Kho] = None,
                   lookup: Optional[LookupResult] = None, lang: str = "vi") -> list[Message]:
    _KHO_REF[id(kho)] = kho
    ins = _fewshot_cached(kho.version if kho else "", id(kho))
    msgs = [Message("system", SYSTEM)]
    for inp, out in zip(ins, fewshot_outputs()):
        msgs += [Message("user", inp), Message("assistant", json.dumps(out, ensure_ascii=False))]
    msgs.append(Message("user", user_input(text, toks, matches, kho, lookup, lang)))
    return msgs
