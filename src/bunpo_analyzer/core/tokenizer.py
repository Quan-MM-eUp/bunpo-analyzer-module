"""Tach tu (buoc 1.1): SudachiPy + SudachiDict-core, che do C (don vi dai).

Moi token co: vi tri ky tu trong cau, tu loai rut gon (ma chung voi i18n),
cach doc hiragana, furigana chi gan len kanji, va thong tin chia tu cho cac
buoc sau (tra tu 1.4, do mau ngu phap 1.5).

Vi sao Sudachi (thay Lindera trong ke hoach):
- Cai bang pip, tu dien di kem (khong phai tai rieng khi build Docker).
- Co cach doc dung mat chu (映画 -> えいが); tu dien cua Lindera chi co cach
  phat am (エーガ).
- Che do C giu tu ghep nguyen ven (日本人, 図書館, 東京スカイツリー) - hop voi
  nguoi hoc va tra tu; UniDic tach 日本 + 人 va doc sai 人 la にん.
- Cung bo tu loai kieu UniDic, tu dien cap nhat thuong xuyen.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Optional

from bunpo_analyzer.schema import Pos, PosSub, Token

_KANJI = r"㐀-䶿一-鿿豈-﫿々〆ヶ"
_HAS_KANJI = re.compile(f"[{_KANJI}]")
_SPLIT_KANJI = re.compile(f"([{_KANJI}]+)")


def kata_to_hira(s: str) -> str:
    """Katakana -> hiragana (giu nguyen ー va ky tu khac)."""
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def has_kanji(s: str) -> bool:
    return bool(_HAS_KANJI.search(s))


def split_furigana(surface: str, reading: Optional[str]) -> list[tuple[str, Optional[str]]]:
    """Chia mat chu thanh doan; chi doan kanji co cach doc.

    面白かっ + おもしろかっ -> [("面白","おもしろ"), ("かっ", None)]
    Khong can khop duoc thi gan ca cach doc cho ca tu.
    """
    if not has_kanji(surface) or not reading:
        return [(surface, None)]
    parts = [p for p in _SPLIT_KANJI.split(surface) if p]
    pattern = "".join(
        "(.+?)" if has_kanji(p) else f"({re.escape(kata_to_hira(p))})" for p in parts
    )
    m = re.fullmatch(pattern, reading)
    if not m:
        return [(surface, reading)]
    return [(p, r if has_kanji(p) else None) for p, r in zip(parts, m.groups())]


@dataclass(frozen=True)
class MorphToken:
    i: int
    surface: str
    start: int  # vi tri ky tu [start, end) trong cau dau vao
    end: int
    pos: Pos
    pos_detail: tuple[str, ...]  # pos1..pos4 cua UniDic
    lemma: str  # tu goc dung de tra tu (buoc 1.4 xu ly them V kha nang -> V goc)
    base: str  # dang goc hien thi: 見 -> 見る, し -> する
    reading: Optional[str]  # hiragana cua mat chu
    furigana: list[tuple[str, Optional[str]]] = field(default_factory=list)
    ctype: Optional[str] = None  # loai chia: 五段-ワア行, 上一段-マ行...
    cform: Optional[str] = None  # dang chia: 連用形-一般...
    verb_group: Optional[int] = None  # 1, 2, 3 (dong tu)
    adj_type: Optional[str] = None  # "i" | "na"
    is_unknown: bool = False
    norm: Optional[str] = None  # dang chuan hoa cua Sudachi: えいが -> 映画, いわ -> 言う
    # Tu ghep (che do C) tach thanh don vi ngan (che do A): 子供たち -> 子供 + たち.
    # Moi phan: (mat chu, dang goc, dang chuan hoa, cach doc hiragana, pos1). Rong neu khong ghep.
    parts: tuple[tuple[str, str, str, Optional[str], str], ...] = ()

    @property
    def pos_sub(self) -> Optional[PosSub]:
        if self.verb_group:
            return f"v{self.verb_group}"  # type: ignore[return-value]
        if self.adj_type:
            return "adj_i" if self.adj_type == "i" else "adj_na"
        return None

    def to_schema(self) -> Token:
        if self.pos == "punct":
            return Token(i=self.i, surface=self.surface, pos="punct")
        return Token(
            i=self.i,
            surface=self.surface,
            base=self.base,
            reading=self.reading,
            pos=self.pos,
            pos_sub=self.pos_sub,
            furigana=self.furigana,
        )


def _f(v) -> Optional[str]:
    return None if v in (None, "*", "") else str(v)


def _pos(pos1: str, pos2: Optional[str], lemma: str, cform: Optional[str]) -> Pos:
    if pos1 in ("補助記号", "記号", "空白"):
        return "punct"
    if pos1 == "助詞":
        return "prt"
    if pos1 == "助動詞":
        # Naに, Naな, ようになる: nguoi hoc quen goi に/な la tro tu (giong artifact).
        if lemma == "だ" and cform and cform.startswith(("連用形-ニ", "連体形")):
            return "prt"
        return "aux"
    if pos1 == "動詞":
        return "verb"
    if pos1 == "形容詞":
        return "adj"
    if pos1 == "形状詞":
        return "aux" if pos2 == "助動詞語幹" else "adj"  # よう(に)
    if pos1 == "連体詞":
        return "adj"  # この, あの
    if pos1 == "名詞" and pos2 == "助動詞語幹":
        return "aux"  # (降る)そう(です)
    if pos1 in ("副詞", "接続詞", "感動詞"):
        return "adv"
    if pos1 == "接尾辞":
        if pos2 == "形容詞的":
            return "adj"  # 読みやすい
        if pos2 == "動詞的":
            return "verb"
        if pos2 == "形状詞的":
            return "adj"
    return "noun"  # 名詞, 代名詞, 接頭辞, 接尾辞 danh tu


def _verb_group(ctype: Optional[str]) -> Optional[int]:
    if not ctype:
        return None
    if ctype.startswith("五段"):
        return 1
    if ctype.startswith(("上一段", "下一段")):
        return 2
    if ctype.startswith(("サ行変格", "カ行変格")):
        return 3
    return None


# Cach doc tu dien chon ma nguoi hoc it gap; doi sang cach doc giao trinh dung.
PREFERRED_READINGS: dict[str, str] = {
    "私": "わたし",
    "明日": "あした",
    "富士山": "ふじさん",
    "日本": "にほん",
}
# Chu Han doc theo ngu canh (辛い: からい/つらい, 開く: あく/ひらく) tu dien
# khong phan biet duoc; de xuat cho LLM kiem tra cach doc o buoc 2.2.


class Tokenizer:
    """Boc SudachiPy. Tokenizer cua Sudachi khong an toan da luong nen dung khoa."""

    def __init__(self) -> None:
        # nap cham: chi can khi thuc su tach tu
        from sudachipy import Dictionary, SplitMode

        self._split_a = SplitMode.A
        self._mode = SplitMode.C
        self._tok = Dictionary(dict="core").tokenizer(mode=self._mode)
        self._lock = threading.Lock()

    def _parts(self, m) -> tuple:
        sub = m.split(self._split_a)
        if len(sub) < 2:
            return ()
        return tuple(
            (x.surface(), x.dictionary_form(), x.normalized_form(),
             kata_to_hira(x.reading_form()) if x.reading_form() and not x.is_oov() else None,
             x.part_of_speech()[0])
            for x in sub
        )

    def tokenize(self, text: str) -> list[MorphToken]:
        with self._lock:
            ms = [
                (m.surface(), m.begin(), m.end(), m.part_of_speech(), m.dictionary_form(),
                 m.reading_form(), m.is_oov(), m.normalized_form(), self._parts(m))
                for m in self._tok.tokenize(text, self._mode)
            ]
        out: list[MorphToken] = []
        for surface, start, end, pos_t, dict_form, kana, oov, norm, parts in ms:
            if not surface.strip():
                continue  # khoang trang
            pos1, pos2 = pos_t[0], _f(pos_t[1])
            ctype, cform = _f(pos_t[4]), _f(pos_t[5])
            base = dict_form or surface
            reading = PREFERRED_READINGS.get(surface) or (kata_to_hira(kana) if kana and not oov else None)
            pos = _pos(pos1, pos2, base, cform)
            if pos == "punct":
                reading = None
            out.append(
                MorphToken(
                    i=len(out),
                    surface=surface,
                    start=start,
                    end=end,
                    pos=pos,
                    pos_detail=tuple(x for x in (pos1, pos2, _f(pos_t[2]), _f(pos_t[3])) if x),
                    lemma=base,
                    base=base,
                    reading=reading,
                    furigana=split_furigana(surface, reading) if pos != "punct" else [],
                    ctype=ctype,
                    cform=cform,
                    verb_group=_verb_group(ctype) if pos == "verb" else None,
                    adj_type="i" if (pos1 == "形容詞" or (pos1 == "接尾辞" and pos2 == "形容詞的")) else ("na" if pos == "adj" and pos1 == "形状詞" else None),
                    is_unknown=bool(oov),
                    norm=norm,
                    parts=parts,
                )
            )
        return _fix_no_adjectives(out)


def _fix_no_adjectives(toks: list[MorphToken]) -> list[MorphToken]:
    """UniDic xep たくさん, 一緒... la 形状詞; khi dung voi の (たくさんの宿題)
    thi nguoi hoc hieu la danh tu, khong phai tinh tu な."""
    from dataclasses import replace

    out = list(toks)
    for k, t in enumerate(toks[:-1]):
        if t.pos == "adj" and t.adj_type == "na" and toks[k + 1].surface == "の" and toks[k + 1].pos == "prt":
            out[k] = replace(t, pos="noun", adj_type=None)
    return out


_default: Optional[Tokenizer] = None
_default_lock = threading.Lock()


def get_tokenizer() -> Tokenizer:
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = Tokenizer()
    return _default


def tokenize(text: str) -> list[MorphToken]:
    return get_tokenizer().tokenize(text)
