"""Kiem tra dau vao (buoc 1.2, muc 11.6 file ke hoach).

Thu tu:
1. Chuan hoa: bo khoang trang canh chu Nhat (kieu sach giao khoa), katakana
   nua do -> toan do. Khong bao cho nguoi dung (khong phai auto_fix).
2. Lop chan mong (chatbot da loc truoc): not_japanese, multiple_sentences,
   too_long -> error invalid_input, khong phan tich.
3. Tu sua furigana dinh (buoc 0a): 見みた -> 見た, 映画えいが -> 映画.
   Co sua thi ghi auto_fix de chatbot bao "Minh da sua cau cua ban thanh...".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from bunpo_analyzer.core.tokenizer import MorphToken, Tokenizer, get_tokenizer, has_kanji, kata_to_hira
from bunpo_analyzer.schema import AutoFix, ErrorInfo

_KANA = r"ぁ-ゖァ-ヺーｦ-ﾟ"
_KANJI = r"㐀-䶿一-鿿豈-﫿々〆ヶ"
_JP = f"{_KANA}{_KANJI}" + r"　-〿！-｠"  # gom ca dau cau Nhat
_HAS_KANA = re.compile(f"[{_KANA}]")
_HAS_KANJI = re.compile(f"[{_KANJI}]")
_HALF_KATA = re.compile(r"[ｦ-ﾟ]+")
_SPACE_JP = re.compile(f"(?<=[{_JP}])\\s+|\\s+(?=[{_JP}])")
_SPACES = re.compile(r"\s+")
_QUOTED = re.compile(r"「[^「」]*」|『[^『』]*』")
_END = "。！？!?．"
_KANJI_RUN = re.compile(f"[{_KANJI}]+")
_HIRA_RUN = re.compile(r"[ぁ-ゖー]+")

# Cau chi co chu Han (khong co kana) dai tu muc nay tro len thi coi la tieng Trung.
_KANJI_ONLY_MAX = 8


@dataclass(frozen=True)
class InputResult:
    original: str  # nguoi dung nhap
    text: str  # cau se phan tich (da chuan hoa, da sua)
    auto_fix: Optional[AutoFix] = None
    error: Optional[ErrorInfo] = None


def normalize(raw: str) -> str:
    s = _HALF_KATA.sub(lambda m: unicodedata.normalize("NFKC", m.group()), raw)
    s = s.replace("\r\n", "\n").strip()
    s = _SPACE_JP.sub("", s)  # 今夜　たくさんの　宿題 -> 今夜たくさんの宿題
    return _SPACES.sub(" ", s)


def is_japanese(text: str) -> bool:
    if _HAS_KANA.search(text):
        return True
    kanji = _HAS_KANJI.findall(text)
    return 0 < len(kanji) and len(text) < _KANJI_ONLY_MAX


def count_sentences(text: str) -> int:
    """Quy tac o muc 3 file kich ban: bo phan trong 「」『』, dem dau ket cau
    con chu phia sau. Cau thieu 。 o cuoi van la 1 cau."""
    s = text
    while True:  # bo ca ngoac long nhau
        t = _QUOTED.sub("", s)
        if t == s:
            break
        s = t
    s = _SPACES.sub("", s)
    n, i = 1, 0
    while i < len(s):
        if s[i] in _END:
            j = i
            while j < len(s) and s[j] in _END + "」』）)":  # ？！ lien nhau la 1 dau
                j += 1
            if j < len(s):
                n += 1
            i = j
        else:
            i += 1
    return n


def _kanji_reading(toks: list[MorphToken], start: int, end: int) -> Optional[str]:
    """Cach doc cua doan kanji [start, end) theo ket qua tach tu."""
    out = []
    for t in toks:
        if t.end <= start or t.start >= end:
            continue
        pos = t.start
        for seg, rd in t.furigana or [(t.surface, None)]:
            a, b = pos, pos + len(seg)
            pos = b
            if b <= start or a >= end:
                continue
            if a < start or b > end or not has_kanji(seg) or not rd:
                return None  # doan kanji khong tach rieng duoc
            out.append(rd)
    return "".join(out) or None


def _token_at(toks: list[MorphToken], start: int) -> Optional[MorphToken]:
    return next((t for t in toks if t.start == start), None)


def _covering(toks: list[MorphToken], start: int, end: int) -> list[MorphToken]:
    return [t for t in toks if t.start < end and t.end > start]


def fix_furigana(text: str, tokenizer: Optional[Tokenizer] = None) -> str:
    """Bo cach doc bi dinh ngay sau chu Han.

    Doan kana P ngay sau cum kanji K bi bo khi bo P di thi K doc dung bang P,
    va P that su la "cach doc thua" (W la tu chua K sau khi sua, r_W la cach doc cua W):
    - token bat dau o P co dang chuan hoa giong W (見み, 映画えいが, 言いわれた), hoac
    - token bat dau o P viet dung bang P hoac r_W (今いまから, 暑あつい), hoac
    - P trung khit ranh gioi tu, tu 2 token tro len (学生がくせい -> がく + せい), hoac
    - P ket thuc dung ranh gioi tu va ngay sau K la r_W (行いきたい).
    Khong sua: 今います (bo いま thi con す vo nghia), 起きます, 違いない
    (き, い la okurigana that), 母は, 人々が...
    """
    tk = tokenizer or get_tokenizer()
    pos = 0
    for _ in range(20):  # moi vong sua mot cho
        toks = tk.tokenize(text)
        fixed = None
        for km in _KANJI_RUN.finditer(text, pos):
            s, e = km.span()
            hm = _HIRA_RUN.match(text, e)
            if not hm:
                continue
            tail = hm.group()
            nxt = _token_at(toks, e)
            bounds = {t.end for t in toks}
            for n in range(min(len(tail), 4 * (e - s) + 2), 0, -1):
                p = tail[:n]
                cand = text[:e] + text[e + n:]
                ctoks = tk.tokenize(cand)
                if _kanji_reading(ctoks, s, e) != kata_to_hira(p):
                    continue
                inner = _covering(toks, e, e + n)
                aligned = bool(inner) and inner[0].start == e and inner[-1].end == e + n
                kword = _covering(ctoks, s, e)
                r_w = "".join(t.reading or "" for t in kword)
                same_word = nxt is not None and bool(nxt.norm) and any(t.norm == nxt.norm for t in kword)
                dup_token = nxt is not None and nxt.surface in (p, r_w)
                full_reading = (e + n) in bounds and bool(r_w) and text[e:].startswith(r_w)
                # K va phan dau cua P nam chung mot tu (起きます, 違いない): P co the
                # la okurigana that. Chi sua khi tu sau sua van con okurigana
                # rieng (行いきたい -> 行きたい), khong de lai chu Han tro troi (起ます).
                absorbed = any(t.start < e < t.end for t in toks)
                if absorbed and not (kword and kword[-1].end > e):
                    continue
                if same_word or dup_token or (aligned and len(inner) >= 2) or full_reading:
                    fixed = (cand, e)
                    break
            if fixed:
                break
        if not fixed:
            return text
        text, pos = fixed
    return text


def check_input(raw: str, max_chars: int = 100, tokenizer: Optional[Tokenizer] = None) -> InputResult:
    text = normalize(raw)
    if not is_japanese(text):
        return InputResult(raw, text, error=ErrorInfo(code="invalid_input", reason="not_japanese"))
    if count_sentences(text) > 1:
        return InputResult(raw, text, error=ErrorInfo(code="invalid_input", reason="multiple_sentences"))
    if len(text) > max_chars:
        return InputResult(raw, text, error=ErrorInfo(code="invalid_input", reason="too_long"))
    fixed = fix_furigana(text, tokenizer)
    if fixed != text:
        return InputResult(raw, fixed, auto_fix=AutoFix(original=raw.strip(), fixed=fixed))
    return InputResult(raw, text)
