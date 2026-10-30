"""Du lieu cho bang ngu phap (buoc 4.2, muc 11.7 file ke hoach).

`grammar_detail(gid, lang)` tra moi thu bang ngu phap can, lay thang tu kho (khong goi
AI). Giai doan 5 dung cho API GET /ai/sensei/grammar/{id}?lang=...

Lam sach luc doc (kho giu nguyen, sua kho la hien ngay):
- examples_clean: tach `examples` thanh cap {jp, vi}; bo so thu tu (1., ①, ➂), bo khoang
  trang kieu sach giao khoa giua chu Nhat; bo trung; xep: cau don truoc hoi thoai A/B,
  cung loai thi khoi chinh (truoc ──────) truoc.
- mistakes: tach `common_mistakes` moi loi mot dong, bo dau dong (•, -, 1.).
- comparison: bang HTML trong kho -> {headers, rows}; o giu duy nhat the ruby.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional

from pydantic import BaseModel, Field

from bunpo_analyzer.core.canon import canon_id
from bunpo_analyzer.core.data import DEFAULT_LANG, Kho
from bunpo_analyzer.core.grammar_meta import confusable_ids, short_label

_JP = re.compile(r"[ぁ-ゖァ-ヺー㐀-䶿一-鿿々]")
_VI = re.compile(r"[à-ỹđĐ]|\b[a-zA-Z]{3,}\b")
_MARK = re.compile(r"^(\s*(\d+[\.\)．]|[①-⑳➀-➓❶-❿]|→)\s*)+")
_BLOCK = re.compile(r"\n\s*─{3,}\s*\n")
_SPEAKER = re.compile(r"^\s*([A-ZＡ-Ｚ])\s*[:：]\s*")
_JPCH = "ぁ-ゖァ-ヺー㐀-䶿一-鿿々、。「」『』！？（）～"
_SPACE_JP = re.compile(f"(?<=[{_JPCH}])[ 　]+(?=[{_JPCH}])")
_BULLET = re.compile(r"^\s*(?:[•・\-–*]|\d+[\.\)])\s*")
MAX_EXAMPLES = 6


# ---------------- vi du ----------------
class Example(BaseModel):
    jp: str
    vi: Optional[str] = None  # ban dich (tieng Viet trong kho)
    dialog: bool = False  # hoi thoai A/B: jp, vi gom nhieu dong


def _tidy_jp(s: str) -> str:
    s = s.strip()
    m = _SPEAKER.match(s)
    head = f"{m.group(1)}: " if m else ""  # A:　... -> "A: ..."
    return head + _SPACE_JP.sub("", s[m.end():] if m else s).strip()


def _is_jp(line: str) -> bool:
    return bool(_JP.search(line)) and not _VI.search(_SPEAKER.sub("", line))


def examples_clean(text: Optional[str], limit: int = MAX_EXAMPLES) -> list[Example]:
    out: list[tuple[int, int, Example]] = []
    seen: set[str] = set()
    for b, block in enumerate(_BLOCK.split(str(text or ""))):
        items: list[dict] = []
        for raw in block.split("\n"):
            line = raw.strip()
            if not line or line == "[]":
                continue
            if _MARK.match(line) or not items:
                items.append({"jp": [], "vi": []})
                line = _MARK.sub("", line)
            if not line:
                continue
            (items[-1]["jp"] if _is_jp(line) else items[-1]["vi"]).append(line)
        for it in items:
            if not it["jp"]:
                continue
            dialog = len(it["jp"]) > 1 or any(_SPEAKER.match(x) for x in it["jp"])
            jp = "\n".join(_tidy_jp(x) for x in it["jp"])
            key = re.sub(r"[\s「」『』。、！？A-ZＡ-Ｚ:：]", "", jp)
            if key in seen:
                continue
            seen.add(key)
            vi = "\n".join(it["vi"]) or None
            out.append((b > 0, dialog, Example(jp=jp, vi=vi, dialog=dialog)))
    out.sort(key=lambda x: (x[1], x[0]))  # cau don truoc hoi thoai; cung loai thi khoi chinh truoc
    return [e for *_, e in out[:limit]]


# ---------------- loi hay gap ----------------
def mistakes(text: Optional[str]) -> list[str]:
    out = []
    for line in str(text or "").split("\n"):
        line = _BULLET.sub("", line).strip()
        if line and line not in out:
            out.append(line)
    return out


# ---------------- bang so sanh ----------------
class Comparison(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)  # o: chu thuong + <ruby>…<rt>…</rt></ruby>


class _Table(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self.cell: Optional[list[str]] = None
        self.in_head = False

    def handle_starttag(self, tag, attrs):
        if tag == "thead":
            self.in_head = True
        elif tag == "tr" and not self.in_head:
            self.rows.append([])
        elif tag in ("td", "th"):
            self.cell = []
        elif tag in ("ruby", "rt") and self.cell is not None:
            self.cell.append(f"<{tag}>")
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "thead":
            self.in_head = False
        elif tag in ("td", "th") and self.cell is not None:
            txt = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            if self.in_head or (tag == "th" and not any(self.rows)):
                self.headers.append(txt)  # hang tieu de (co hoac khong co <thead>)
            elif self.rows:
                self.rows[-1].append(txt)
            self.cell = None
        elif tag in ("ruby", "rt") and self.cell is not None:
            self.cell.append(f"</{tag}>")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data.replace("<", "&lt;").replace(">", "&gt;"))


def comparison(html: Optional[str]) -> Optional[Comparison]:
    if not html or "<t" not in html:
        return None
    p = _Table()
    p.feed(html)
    rows = [r for r in p.rows if any(r)]
    return Comparison(headers=p.headers, rows=rows) if rows else None


# ---------------- bang ngu phap ----------------
class Label(BaseModel):
    code: str
    name: Optional[str] = None  # ten theo lang (i18n); tieng Viet chua co ten


class Confusable(BaseModel):
    id: int
    short_label: Optional[str] = None
    level: Optional[str] = None


class GrammarDetail(BaseModel):
    id: int
    lang: str
    text_lang: str  # ngon ngu thuc cua phan chu (vi neu chua co ban dich)
    short_label: Optional[str] = None
    name: Optional[str] = None
    reading: Optional[str] = None
    level: Optional[str] = None
    labels: list[Label] = Field(default_factory=list)
    connection: Optional[str] = None  # 接続
    meaning: Optional[str] = None  # meaning_vi nguyen van (muc 12.10)
    examples: list[Example] = Field(default_factory=list)
    explain: Optional[str] = None
    comparison: Optional[Comparison] = None
    mistakes: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    confusable: list[Confusable] = Field(default_factory=list)


def grammar_detail(gid: int, lang: str = DEFAULT_LANG, kho: Optional[Kho] = None) -> Optional[GrammarDetail]:
    """None neu khong co mau. id cua mau trung da gom van mo duoc (tra dung muc do)."""
    if kho is None:
        from bunpo_analyzer.core.data import get_kho

        kho = get_kho()
    g = kho.grammar(gid)
    if g is None:
        return None
    r = g.raw
    txt = kho.grammar_text(g.id, lang)
    conf = []
    for cid in confusable_ids(g.id):
        cg = kho.grammar(cid)
        if cg is not None and canon_id(cid) != canon_id(g.id):
            conf.append(Confusable(id=cid, short_label=short_label(cid, kho, lang), level=cg.level))
    return GrammarDetail(
        id=g.id, lang=lang, text_lang=txt.get("lang") or DEFAULT_LANG,
        short_label=short_label(g.id, kho, lang), name=txt.get("name") or g.name,
        reading=(r.get("grammar_reading") or None), level=g.level,
        labels=[Label(code=c, name=kho.label_name(c, lang)) for c in g.labels],
        connection=(r.get("接続") or None), meaning=txt.get("meaning"),
        examples=examples_clean(r.get("examples")),
        explain=txt.get("explain"), comparison=comparison(r.get("comparison")),
        mistakes=mistakes(txt.get("mistakes")), notes=(r.get("notes") or None),
        confusable=conf,
    )
