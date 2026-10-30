"""Gom token thanh cum (kieu bunsetsu) de LLM chia cau theo cum, khong theo token (prompt v3).

Ly do: o prompt v2, LLM hay cat sai ranh gioi token: tach tro tu khoi cum
(田中さん | は), tach duoi chia khoi dong tu (貯め | ています), lam roi mat
た cua 言われた. Neu LLM chi duoc chon CUM thi cac loi nay khong xay ra.

Quy tac (cum nho nhat; mot dong phan tich = mot hoac nhieu cum lien nhau):
- Tu noi dung (danh tu, dong tu, tinh tu, trang tu) bat dau cum moi.
- Tro tu, tro dong tu, hau to, dau cau dinh vao cum truoc.
- Tien to (お, ご) dinh vao cum sau.
- Dong tu phu sau て/で (いる, しまう, くれる...) dinh vao cum truoc: 食べている.
- Danh tu chi so dinh voi tu dem phia sau (3時, 2回).
- Tinh tu phu (ない sau 難しく) dinh vao cum truoc.
- Danh tu kieu サ変 + する la mot cum (練習したら, 勉強しています).
- ため sau dong tu / tinh tu dinh vao cum truoc (行くために).
"""

from __future__ import annotations

from dataclasses import dataclass

from bunpo_analyzer.core.tokenizer import MorphToken

_CONTENT = {"noun", "verb", "adj", "adv"}


@dataclass(frozen=True)
class Chunk:
    i: int
    start: int  # token dau
    end: int  # token cuoi + 1

    def text(self, toks: list[MorphToken]) -> str:
        return "".join(t.surface for t in toks[self.start:self.end])


def _starts_chunk(toks: list[MorphToken], k: int) -> bool:
    t = toks[k]
    if k == 0:
        return True
    prev = toks[k - 1]
    pd = t.pos_detail
    if prev.pos_detail and prev.pos_detail[0] == "接頭辞":
        return False  # お + 茶
    if t.pos not in _CONTENT:
        return False  # tro tu, tro dong tu, dau cau
    if pd and pd[0] == "接尾辞":
        return False  # さん, たち, やすい
    if t.pos == "verb" and len(pd) > 1 and pd[1] == "非自立可能" and prev.surface in ("て", "で") and prev.pos == "prt":
        return False  # 食べ + て + いる
    if t.pos == "noun" and "数詞" in prev.pos_detail and (len(pd) > 2 and pd[2] == "助数詞可能"):
        return False  # 3 + 時
    if t.pos == "aux":
        return False
    if t.base in ("ため", "為") and prev.pos in ("verb", "aux", "adj"):
        return False  # 行く + ために: muc dich / ly do di cung dong tu
    if t.base == "する" and prev.pos == "noun" and len(prev.pos_detail) > 2 and prev.pos_detail[2] == "サ変可能":
        return False  # 練習 + したら, 勉強 + しています: danh tu + する la mot dong tu
    if t.pos == "adj" and len(pd) > 1 and pd[1] == "非自立可能" and prev.pos in ("adj", "aux", "verb"):
        return False  # 難しく + ない, 食べたく + ない
    return True


def chunk(toks: list[MorphToken]) -> list[Chunk]:
    out: list[Chunk] = []
    start = 0
    for k in range(1, len(toks) + 1):
        if k == len(toks) or _starts_chunk(toks, k):
            # cum chi gom dau cau o dau cau (hiem) van giu de khong mat token
            out.append(Chunk(len(out), start, k))
            start = k
    return out


def token_to_chunk(chunks: list[Chunk]) -> dict[int, int]:
    return {t: c.i for c in chunks for t in range(c.start, c.end)}


def chunk_span_to_tokens(chunks: list[Chunk], span: list[int] | None, drop_punct_tail: list[MorphToken] | None = None):
    """[cum dau, cum cuoi + 1) -> [token dau, token cuoi + 1). Bo dau cau o cuoi neu co danh sach token."""
    if not span or len(span) != 2 or not (0 <= span[0] < span[1] <= len(chunks)):
        return None
    a, b = chunks[span[0]].start, chunks[span[1] - 1].end
    if drop_punct_tail is not None:
        while b > a and drop_punct_tail[b - 1].pos == "punct":
            b -= 1
    return [a, b]


def token_span_to_chunks(chunks: list[Chunk], span: list[int] | None):
    if not span:
        return None
    m = token_to_chunk(chunks)
    if span[0] not in m or span[1] - 1 not in m:
        return None
    return [m[span[0]], m[span[1] - 1] + 1]
