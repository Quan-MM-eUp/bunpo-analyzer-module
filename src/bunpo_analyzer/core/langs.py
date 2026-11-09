"""Ngon ngu du phong cho phan chu lay tu kho va bang tro tu (BUNPO_TEXT_FALLBACK_LANG).

Gia tri cua lan goi hien tai nam trong ContextVar: `analyze_full(settings=...)` dat theo `settings`
cua no (moi request / task asyncio co ban rieng, khong lan sang nhau); ngoai lan goi do (vd
`grammar_detail()` goi truc tiep tu endpoint) thi doc `get_settings()`.

Thu tu chon chu khi `lang` chua co ban dich: `lang` -> ngon ngu du phong -> tieng Viet (ban goc).
Nguoi dung tieng Viet luon thay ban goc, khong bao gio rot sang ngon ngu du phong.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

_FALLBACK: ContextVar[Optional[str]] = ContextVar("bunpo_text_fallback_lang", default=None)


def text_fallback_lang() -> str:
    v = _FALLBACK.get()
    if v is None:
        from bunpo_analyzer.config import get_settings

        v = get_settings().text_fallback_lang
    return v


@contextmanager
def use_text_fallback(lang: str) -> Iterator[None]:
    token = _FALLBACK.set(lang)
    try:
        yield
    finally:
        _FALLBACK.reset(token)
