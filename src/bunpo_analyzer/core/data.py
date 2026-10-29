"""Nap kho du lieu (buoc 1.3).

Bo cuc thu muc (Settings.data_dir, mac dinh la thu muc `Model bunpo`):

    word/word_lib.json              kho tu vung goc (tieng Viet)
    word/word_text.<lang>.json      ban dich theo id: {"1": {"meaning": "..."}}
    grammar/grammar_lib.json        kho ngu phap goc (tieng Viet)
    grammar/grammar_text.<lang>.json {"245": {"name", "meaning", "explain", "mistakes"}}
    i18n/<lang>.json                nhan giao dien, ten ma nhan ngu phap (label)

Nguyen tac (muc 12.4, 12.9, 12.10 file ke hoach):
- Noi dung kho hien nguyen trang, khong lam sach o day.
- Doc theo `lang`; chua co ban dich (thieu file, thieu id hoac thieu truong)
  thi dung tieng Viet. Am Han Viet chi tra cho tieng Viet.
- `version` la ma bam noi dung cac file da nap: doi kho la doi khoa cache.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bunpo_analyzer.core.tokenizer import kata_to_hira

DEFAULT_LANG = "vi"

# pos cua word_lib -> ma tu loai cua module (khop khi tra tu, buoc 1.4)
WORD_POS = {
    "pos_noun": "noun", "pos_pronoun": "noun", "pos_verb": "verb",
    "pos_adjective_i": "adj", "pos_adjective_na": "adj", "pos_adnominal": "adj",
    "pos_adverb": "adv", "pos_conjunction": "adv", "pos_interjection": "adv",
}

_ANNOT = re.compile(r"<[^<>]*>|\[[^\[\]]*[/／〜～・化][^\[\]]*\]")  # 堪能<な/する>, やたら[な/と], 一概に[〜ない]
_OPT = re.compile(r"\[([^\[\]]{1,3})\]")  # [お]しまい, ぐったり[と]する: co hoac khong
_PAREN = re.compile(r"[（(]([^（）()]*)[）)]")
_SPLIT = re.compile(r"[、,，/／]")
_STRIP = re.compile(r"[\s～〜~＿_]")
_KANJI = re.compile(r"[㐀-鿿々]")
_ALL_KANJI = re.compile(r"[㐀-鿿々]+")


def _expand(text: str) -> set[str]:
    """Mo tung cap ngoac: bo di, hoac thay bang tung lua chon ben trong."""
    m = _PAREN.search(text)
    if not m:
        return {text}
    head, tail = text[: m.start()], text[m.end():]
    inner = m.group(1)
    outside = _PAREN.sub("", head + tail)
    out: set[str] = set()
    for rest in _expand(tail):
        out.add(head + rest)  # bo phan trong ngoac
        if _KANJI.search(inner) and _ALL_KANJI.fullmatch(outside) and len(inner) >= len(outside) - 1:
            out.add(inner)  # cach viet khac: 足元(足下)
            continue
        for opt in re.split(r"[・/／]", inner):  # やたら(に・と) -> やたらに, やたらと
            out.add(head + opt + rest)
    return out


def headword_keys(text: str) -> tuple[str, ...]:
    """Cac dang viet de tra cua mot muc tu.

    堪能<な/する> -> 堪能; きまり(が)悪い -> きまり悪い, きまりが悪い;
    足元(足下) -> 足元, 足下; やたら(に・と) -> やたら, やたらに, やたらと.
    """
    if not text:
        return ()
    keys: list[str] = []
    for v in _expand(_OPT.sub(r"(\1)", _ANNOT.sub("", text))):
        for part in _SPLIT.split(v):
            k = _STRIP.sub("", part)
            if k and k not in keys:
                keys.append(k)
    return tuple(sorted(keys, key=lambda k: (-len(k), k)))


@dataclass(frozen=True)
class Word:
    id: int
    word: str
    reading: str
    level: Optional[str]
    pos: Optional[str]  # ma cua module: noun/verb/adj/adv
    pos_raw: str  # pos_noun, pos_adjective_na...
    keys: tuple[str, ...]  # dang viet de tra
    reading_keys: tuple[str, ...]  # cach doc (hiragana) de tra


@dataclass(frozen=True)
class Grammar:
    id: int
    name: str  # ten mau trong kho (171 mau dang viet bang tieng Viet - muc 12.9)
    reading: str
    pattern: str
    level: Optional[str]
    conn: str  # 接続 - dung viet luat do mau (buoc 1.5)
    labels: tuple[str, ...]
    raw: dict[str, Any]


def _sha(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


class Kho:
    """Kho tu vung + ngu phap da nap va lap chi muc. Chi doc, dung chung duoc."""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        wp = self.data_dir / "word" / "word_lib.json"
        gp = self.data_dir / "grammar" / "grammar_lib.json"
        if not wp.exists() or not gp.exists():
            raise FileNotFoundError(f"Khong tim thay kho trong {self.data_dir} (can word/word_lib.json, grammar/grammar_lib.json)")
        self._word_raw: dict[int, dict[str, Any]] = {int(x["id"]): x for x in _read_json(wp)}
        self._gram_raw: dict[int, dict[str, Any]] = {int(x["id"]): x for x in _read_json(gp)}

        self.words: dict[int, Word] = {}
        self._by_key: dict[str, list[int]] = {}
        self._by_reading: dict[str, list[int]] = {}
        for wid, x in self._word_raw.items():
            word = str(x.get("word") or "")
            reading = str(x.get("reading") or "")
            keys = headword_keys(word)
            rkeys = tuple(kata_to_hira(k) for k in headword_keys(reading or word))
            w = Word(wid, word, reading, x.get("level"), WORD_POS.get(x.get("pos", "")), x.get("pos", ""), keys, rkeys)
            self.words[wid] = w
            for k in keys:
                self._by_key.setdefault(k, []).append(wid)
            for k in rkeys:
                self._by_reading.setdefault(k, []).append(wid)

        self.grammars: dict[int, Grammar] = {
            gid: Grammar(
                gid, str(x.get("grammar") or ""), str(x.get("grammar_reading") or ""),
                str(x.get("pattern") or ""), x.get("level"), str(x.get("接続") or ""),
                tuple(x.get("label") or ()), x,
            )
            for gid, x in self._gram_raw.items()
        }

        files = [wp, gp]
        self._word_text: dict[str, dict[str, dict[str, Any]]] = {}
        self._gram_text: dict[str, dict[str, dict[str, Any]]] = {}
        for p in sorted((self.data_dir / "word").glob("word_text.*.json")):
            self._word_text[p.name.split(".")[1]] = _read_json(p)
            files.append(p)
        for p in sorted((self.data_dir / "grammar").glob("grammar_text.*.json")):
            self._gram_text[p.name.split(".")[1]] = _read_json(p)
            files.append(p)
        self._i18n: dict[str, dict[str, Any]] = {}
        for p in sorted((self.data_dir / "i18n").glob("*.json")):
            self._i18n[p.stem] = _read_json(p)
            files.append(p)
        self.version = _sha(files)

    # ---------- tra cuu ----------
    def word(self, wid: int) -> Optional[Word]:
        return self.words.get(wid)

    def words_by_key(self, key: str) -> list[Word]:
        return [self.words[i] for i in self._by_key.get(key, ())]

    def words_by_reading(self, reading: str) -> list[Word]:
        return [self.words[i] for i in self._by_reading.get(kata_to_hira(reading), ())]

    def grammar(self, gid: int) -> Optional[Grammar]:
        return self.grammars.get(int(gid))

    # ---------- noi dung theo ngon ngu ----------
    @property
    def langs(self) -> tuple[str, ...]:
        return tuple(sorted({DEFAULT_LANG, *self._word_text, *self._gram_text}))

    def word_text(self, wid: int, lang: str = DEFAULT_LANG) -> dict[str, Optional[str]]:
        raw = self._word_raw.get(wid)
        if raw is None:
            return {}
        tr = self._word_text.get(lang, {}).get(str(wid), {}) if lang != DEFAULT_LANG else {}
        return {
            "meaning": tr.get("meaning") or raw.get("meaning") or None,
            "han_viet": (raw.get("han_viet") or None) if lang == DEFAULT_LANG else None,
            "lang": lang if tr.get("meaning") else DEFAULT_LANG,
        }

    def grammar_text(self, gid: int, lang: str = DEFAULT_LANG) -> dict[str, Optional[str]]:
        raw = self._gram_raw.get(int(gid))
        if raw is None:
            return {}
        tr = self._gram_text.get(lang, {}).get(str(gid), {}) if lang != DEFAULT_LANG else {}
        vi = {
            "name": raw.get("grammar") or None,
            "meaning": raw.get("meaning_vi") or None,
            "explain": raw.get("explain") or None,
            "mistakes": raw.get("common_mistakes") or None,
        }
        out = {k: tr.get(k) or v for k, v in vi.items()}
        out["lang"] = lang if tr.get("meaning") else DEFAULT_LANG
        return out

    def label_name(self, code: str, lang: str = DEFAULT_LANG) -> Optional[str]:
        """Ten ma nhan ngu phap (grammar_basic...). Kho hien chua co ten tieng Viet."""
        return (self._i18n.get(lang, {}).get("label") or {}).get(code)


_cache: dict[Path, Kho] = {}
_lock = threading.Lock()


def get_kho(data_dir: Path | str | None = None) -> Kho:
    if data_dir is None:
        from bunpo_analyzer.config import get_settings

        data_dir = get_settings().data_dir
    key = Path(data_dir).resolve()
    with _lock:
        if key not in _cache:
            _cache[key] = Kho(key)
        return _cache[key]


def clear_kho_cache() -> None:
    with _lock:
        _cache.clear()
