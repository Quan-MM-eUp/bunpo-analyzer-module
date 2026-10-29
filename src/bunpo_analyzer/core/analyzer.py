"""Ham duy nhat ben ngoai can goi.

Luong (muc 2): kiem tra dau vao (1.2) -> tach tu (1.1) -> tra tu (1.4)
-> do mau ngu phap (1.5) -> goi LLM (2.1-2.2) -> kiem tra (2.3-2.4)
-> ghep ket qua (2.5) -> cache (2.6).
"""

from __future__ import annotations

from typing import Optional

from bunpo_analyzer.schema import AnalysisResult


async def analyze(
    sentence: str,
    lang: Optional[str] = None,
    provider: Optional[str] = None,
) -> AnalysisResult:
    """Phan tich DUNG 1 cau tieng Nhat (chatbot da loc dau vao).

    lang: ngon ngu nguoi dung, mac dinh `Settings.default_lang`.
    provider: nha cung cap LLM, mac dinh `Settings.llm_provider`.
    """
    raise NotImplementedError("Lam o buoc 2.5")
