"""Dung chung cho bo cong cu dich kho ngu phap (ke-hoach-dich-kho-ngu-phap.md).

Chi dung thu vien chuan Python: chay duoc tren may nguoi dung (device_bash) lan trong cloud.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

# Thu tu nhom ngon ngu (muc 1, quyet dinh 2)
LANG_GROUPS = [["en", "ko", "cn", "tw", "th", "id"], ["fr", "de", "es", "pt", "ru", "pl"], ["hi", "ne", "my"]]
LANGS = [l for g in LANG_GROUPS for l in g]
LOW_RESOURCE = {"hi", "ne", "my"}
LANG_NAMES = {
    "en": "English", "ko": "Korean", "cn": "Simplified Chinese", "tw": "Traditional Chinese (Taiwan)",
    "th": "Thai", "id": "Indonesian", "fr": "French", "de": "German", "es": "Spanish", "pt": "Portuguese",
    "ru": "Russian", "pl": "Polish", "hi": "Hindi", "ne": "Nepali", "my": "Burmese (Unicode)",
}

LOCK_STALE_S = 3 * 3600
STATUSES = ("pending", "translated", "passed", "qa_low", "failed")

# ---------------- nhan dien chu ----------------
VI = re.compile(r"[à-ỹđĐ]")
KANA = re.compile(r"[ぁ-ゖァ-ヺー]")
KANJI = re.compile(r"[㐀-䶿一-鿿々]")
# cum tieng Nhat lien tiep (co it nhat 1 kana) - phai giu nguyen trong ban dich
JP_RUN = re.compile(r"[ぁ-ゖァ-ヺー㐀-䶿一-鿿々〜～・「」『』（）、。！？]*[ぁ-ゖァ-ヺ][ぁ-ゖァ-ヺー㐀-䶿一-鿿々〜～・「」『』（）、。！？]*")
SYMBOLS = "×○◯✓✕→～⇔"
SCRIPT = {
    "ko": re.compile(r"[가-힣]"), "th": re.compile(r"[฀-๿]"), "hi": re.compile(r"[ऀ-ॿ]"),
    "ne": re.compile(r"[ऀ-ॿ]"), "my": re.compile(r"[က-႟]"), "ru": re.compile(r"[А-Яа-яЁё]"),
    "cn": KANJI, "tw": KANJI,
}
LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž]")
# Mot so chu chi co o gian the / phon the de bat nham cn <-> tw
SIMPLIFIED_ONLY = set("这说语时们动词问题对为个来开关学习过还没变实经应该让给认识读写听买卖东车门见长发")
TRADITIONAL_ONLY = set("這說語時們動詞問題對為個來開關學習過還沒變實經應該讓給認識讀寫聽買賣東車門見長發")


# Chu chi tieng Viet moi co (khong trung chu cai Phap / Duc / Ba Lan...): de bat chu Viet sot trong ban dich
VI_ONLY = re.compile(r"[ăđơưĂĐƠƯẠ-ỹ]")
RUBY = re.compile(r"<ruby>.*?</ruby>", re.DOTALL)
RT = re.compile(r"<(rt|rp)>.*?</\1>|<[^>]+>", re.DOTALL)
PUNCT_SPACE = re.compile(r"[\s、。！？!?「」『』（）()\[\]・,.:;]+")


def deruby(s: str) -> str:
    """<ruby>遊<rt>あそ</rt></ruby>び -> 遊び (bo furigana va moi the HTML)."""
    return RT.sub("", s or "")


def has_vi(s: str | None) -> bool:
    return bool(s and VI.search(s))


def is_ja_only(s: str | None) -> bool:
    return bool(s) and not has_vi(s) and bool(KANA.search(s) or KANJI.search(s))


def jp_runs(s: str) -> list[str]:
    """Cac cum tieng Nhat (co kana, dai >= 2) can giu nguyen trong ban dich."""
    out = []
    for m in JP_RUN.finditer(s or ""):
        r = m.group().strip("、。！？「」『』（）・ ")
        if len(r) >= 2 and KANA.search(r):
            out.append(r)
    return out


def src_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# ---------------- duong dan ----------------
def workspace(arg: str | None = None) -> Path:
    """Thu muc translation/ (mac dinh: BUNPO_TRANSLATION_DIR, hoac <BUNPO_DATA_DIR>/translation)."""
    if arg:
        return Path(arg)
    if os.environ.get("BUNPO_TRANSLATION_DIR"):
        return Path(os.environ["BUNPO_TRANSLATION_DIR"])
    return Path(os.environ.get("BUNPO_DATA_DIR", "..")) / "translation"


def read_json(p: Path) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p: Path, obj: Any, indent: int | None = 1) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=indent) + "\n"
    write_text(p, text)


def write_text(p: Path, text: str) -> None:
    """Ghi nguyen tu (file tam + doi ten) de khong de file do dang neu bi ngat. Thu muc cam
    xoa / ghi de bang doi ten (thu muc ket noi cua Cowork) thi ghi thang."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        p.write_text(text, encoding="utf-8")
