"""Tra nghia tu (buoc 1.4, muc 3.2 file ke hoach).

Thu tu cho moi token:
1. Tro tu, tro dong tu, tro dong tu sau て (～ている, ～てしまう...), hau to
   (さん, たち...): bang `tables/particle_table.json` -> particle_table.
2. Cum nhieu token co trong word_lib, uu tien cum dai nhat (気をつける...).
3. Mot token: tra word_lib theo dang goc / mat chu / dang chuan hoa.
4. Theo cach doc, chi nhan khi tu loai khop VA chu Han cua muc tu nam trong
   tu cua cau (tranh なる -> 鳴る, いる -> 要る; van nhan 子供 -> 子ども,
   つける -> 付ける).
5. Dang kha nang (話せる -> 話す), ra-nuki (見れる -> 見る): dung dang chuan
   hoa cua Sudachi (norm) o buoc 3, khong can luat rieng.
6. Tu ghep khong co trong kho: tach don vi ngan (子供たち -> 子供 + たち),
   nhan khi moi phan deu tra duoc.
7. Tu co ban kho chua co (なる, いる, よく): bang bo sung trong particle_table,
   van ghi vao `misses` de de nghi bo sung kho.
8. Khong tim thay: meaning = None, meaning_source = "llm" (LLM bo sung o
   buoc 2.x) va dua vao `misses` de bo sung kho sau.

Nghia hien nguyen van trong kho (tat ca cac nghia), khong chon theo ngu canh.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from bunpo_analyzer.core.data import DEFAULT_LANG, Kho, Word
from bunpo_analyzer.core.tokenizer import MorphToken, kata_to_hira

_TABLES = Path(__file__).resolve().parent.parent / "tables"
_CONTENT = ("noun", "verb", "adj", "adv")
_KANJI = re.compile(r"[㐀-鿿々]")
_ALL_KANA = re.compile(r"[ぁ-ゖァ-ヺー]+")
_MAX_SPAN = 4


@dataclass(frozen=True)
class WordInfo:
    i: int  # token dau tien
    meaning: Optional[str]
    meaning_source: str  # word_lib | particle_table | llm | none (dau cau, so)
    word_ids: tuple[int, ...] = ()
    span: tuple[int, int] = (0, 0)  # [token dau, token cuoi + 1) neu khop ca cum
    via: str = ""  # table | key | multi | reading | parts | core | number
    level: Optional[str] = None


@dataclass
class LookupResult:
    words: list[WordInfo]
    misses: list[str] = field(default_factory=list)  # dang goc chua co trong kho (de ghi log)


# ---------------- bang tro tu ----------------
@lru_cache(maxsize=None)
def _table() -> tuple[dict[str, Any], ...]:
    data = json.loads((_TABLES / "particle_table.json").read_text(encoding="utf-8"))
    return tuple(data["entries"])


@lru_cache(maxsize=None)
def _table_text(lang: str) -> dict[str, str]:
    p = _TABLES / f"particle_table.{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _after_te(toks: list[MorphToken], i: int) -> bool:
    return i > 0 and toks[i - 1].surface in ("て", "で") and toks[i - 1].pos == "prt"


def table_entry(toks: list[MorphToken], i: int) -> Optional[dict[str, Any]]:
    t = toks[i]
    pd = t.pos_detail
    for e in _table():
        if e["base"] not in (t.base, t.surface):
            continue
        if "pos" in e and e["pos"] != t.pos:
            continue
        if "pos1" in e and (not pd or pd[0] != e["pos1"]):
            continue
        if "pos2" in e and (len(pd) < 2 or pd[1] != e["pos2"]):
            continue
        if "cform" in e and not (t.cform or "").startswith(e["cform"]):
            continue
        if e.get("after_te") and not (_after_te(toks, i) and len(pd) > 1 and pd[1] == "非自立可能"):
            continue
        if "prev" in e and not (i > 0 and toks[i - 1].surface in e["prev"]):
            continue
        if "next" in e and not (i + 1 < len(toks) and toks[i + 1].surface in e["next"]
                                and toks[i + 1].pos == e.get("next_pos", toks[i + 1].pos)):
            continue
        if e.get("core"):
            continue  # tu co ban: chi dung sau khi tra kho that bai
        return e
    return None


def table_meaning(e: dict[str, Any], lang: str) -> str:
    if lang != DEFAULT_LANG:
        tr = _table_text(lang).get(e["key"])
        if tr:
            return tr
    return e["vi"]


# ---------------- word_lib ----------------
def _compatible(token_pos: str, word: Word) -> bool:
    if word.pos is None:
        return True
    if token_pos == "verb" or word.pos == "verb":
        return token_pos == word.pos
    return True  # danh tu / tinh tu / trang tu cua hai ben phan loai khac nhau kha nhieu


def _rank(cands: list[Word], token_pos: str, exact: tuple[str, ...]) -> list[Word]:
    lv = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}
    return sorted(
        {w.id: w for w in cands}.values(),
        key=lambda w: (not _compatible(token_pos, w), w.word not in exact, lv.get(w.level or "", 9), w.id),
    )


def _by_keys(kho: Kho, keys: list[str], pos: str, strict_pos: bool) -> list[Word]:
    found: list[Word] = []
    for k in keys:
        if k:
            found += kho.words_by_key(k)
    if strict_pos:
        found = [w for w in found if _compatible(pos, w)]
    return _rank(found, pos, tuple(keys))


def _kanji_ok(word: Word, forms: tuple[str, ...]) -> bool:
    """Moi chu Han cua muc tu phai co trong dang viet cua token."""
    kanji = set(_KANJI.findall(word.word))
    if not kanji or not any(_KANJI.search(f) for f in forms if f):
        return True  # tu viet bang kana (つける): nhan theo cach doc
    return any(kanji <= set(f) for f in forms if f)


def _by_reading(kho: Kho, reading: Optional[str], pos: str, forms: tuple[str, ...]) -> list[Word]:
    if not reading:
        return []
    kana_token = not any(_KANJI.search(f) for f in forms if f)
    # Tu viet bang kana, ngan: rat de trung am (て -> 手, とも -> 友, かぜ -> 風/風邪).
    # Chi nhan muc tu chu Han khi du dai: dong/tinh tu tu 3 kana, danh tu tu 4 kana.
    min_len = 3 if pos in ("verb", "adj") else 4

    def ok(w: Word) -> bool:
        if not (_compatible(pos, w) and _kanji_ok(w, forms)):
            return False
        if kana_token and _KANJI.search(w.word) and len(reading) < min_len:
            return False
        return True

    return _rank([w for w in kho.words_by_reading(reading) if ok(w)], pos, forms)


def _base_reading(t: MorphToken) -> Optional[str]:
    if _ALL_KANA.fullmatch(t.base):
        return kata_to_hira(t.base)
    if t.surface == t.base and t.reading:
        return t.reading
    return None


def _lookup_single(kho: Kho, t: MorphToken) -> tuple[list[Word], str]:
    forms = tuple(dict.fromkeys(x for x in (t.base, t.surface, t.norm) if x))
    ws = _by_keys(kho, list(forms), t.pos, strict_pos=True)
    if ws:
        return ws, "key"
    ws = _by_reading(kho, _base_reading(t), t.pos, forms)
    if ws:
        return ws, "reading"
    return [], ""


def core_entry(t: MorphToken) -> Optional[dict[str, Any]]:
    return next((e for e in _table() if e.get("core") and e["base"] == t.base and e.get("pos") == t.pos), None)


def _lookup_parts(kho: Kho, t: MorphToken, lang: str) -> Optional[tuple[str, list[int]]]:
    if not t.parts:
        return None
    pieces, ids = [], []
    for surface, base, norm, reading, pos1 in t.parts:
        if pos1 == "接尾辞":
            e = next((x for x in _table() if x.get("pos1") == "接尾辞" and x["base"] in (surface, base)), None)
            if e:
                pieces.append(f"{surface} ({table_meaning(e, lang)})")
                continue
        forms = tuple(dict.fromkeys(x for x in (base, surface, norm) if x))
        ws = _by_keys(kho, list(forms), "noun", strict_pos=False)
        if not ws and reading:
            ws = [w for w in kho.words_by_reading(reading) if _kanji_ok(w, forms)]
        if not ws:
            return None
        ids.append(ws[0].id)
        pieces.append(f"{surface} ({kho.word_text(ws[0].id, lang)['meaning']})")
    return " + ".join(pieces), ids


def _lookup_multi(kho: Kho, toks: list[MorphToken], i: int) -> Optional[tuple[int, list[Word]]]:
    """Cum 2-4 token co trong kho, dai nhat truoc. Token cuoi dung dang goc (chia)."""
    if toks[i].pos not in _CONTENT:
        return None
    for j in range(min(len(toks), i + _MAX_SPAN), i + 1, -1):
        seg = toks[i:j]
        if any(x.pos == "punct" for x in seg) or seg[-1].pos not in _CONTENT:
            continue
        head = "".join(x.surface for x in seg[:-1])
        for key in (head + seg[-1].base, head + seg[-1].surface):
            ws = kho.words_by_key(key)
            if ws:
                return j, _rank(ws, seg[-1].pos, (key,))
    return None


_NUM = re.compile(r"[0-9０-９.,．，万億千百十]+")


def _is_number(t: MorphToken) -> bool:
    return "数詞" in t.pos_detail or bool(_NUM.fullmatch(t.surface))


def lookup(toks: list[MorphToken], kho: Kho, lang: str = DEFAULT_LANG) -> LookupResult:
    out: list[Optional[WordInfo]] = [None] * len(toks)
    misses: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.pos == "punct":
            out[i] = WordInfo(i, None, "none", span=(i, i + 1))
            i += 1
            continue
        e = table_entry(toks, i)
        if e:
            out[i] = WordInfo(i, table_meaning(e, lang), "particle_table", span=(i, i + 1), via="table")
            i += 1
            continue
        multi = _lookup_multi(kho, toks, i)
        if multi:
            j, ws = multi
            w = ws[0]
            info = WordInfo(i, kho.word_text(w.id, lang)["meaning"], "word_lib", (w.id,), (i, j), "multi", w.level)
            for k in range(i, j):
                out[k] = WordInfo(k, info.meaning, info.meaning_source, info.word_ids, info.span, info.via, info.level)
            i = j
            continue
        if _is_number(t):
            out[i] = WordInfo(i, None, "none", span=(i, i + 1), via="number")
            i += 1
            continue
        ws, how = _lookup_single(kho, t) if t.pos in _CONTENT else ([], "")
        if ws:
            w = ws[0]
            out[i] = WordInfo(i, kho.word_text(w.id, lang)["meaning"], "word_lib", (w.id,), (i, i + 1), how, w.level)
        else:
            parts = _lookup_parts(kho, t, lang) if t.pos in _CONTENT else None
            core = core_entry(t)
            if parts:
                text, ids = parts
                out[i] = WordInfo(i, text, "word_lib", tuple(ids), (i, i + 1), "parts")
            elif core:
                out[i] = WordInfo(i, table_meaning(core, lang), "particle_table", span=(i, i + 1), via="core")
                misses.append(t.base)  # van ghi lai de bo sung kho
            else:
                out[i] = WordInfo(i, None, "llm", span=(i, i + 1))
                misses.append(t.base)
        i += 1
    return LookupResult([x for x in out if x is not None], misses)


def apply_to_tokens(toks: list[MorphToken], result: LookupResult) -> list:
    """Ghep vao Token cua khuon AnalysisResult (meaning, meaning_source)."""
    out = []
    for t, w in zip(toks, result.words):
        s = t.to_schema()
        if t.pos != "punct":
            s = s.model_copy(update={"meaning": w.meaning, "meaning_source": w.meaning_source if w.meaning_source != "none" else None})
        out.append(s)
    return out
