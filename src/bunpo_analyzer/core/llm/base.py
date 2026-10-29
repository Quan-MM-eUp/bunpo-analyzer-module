"""Interface chung cho moi nha cung cap LLM."""

from __future__ import annotations

from typing import Any, Protocol


class LLMProvider(Protocol):
    name: str

    async def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        timeout_s: float,
    ) -> dict[str, Any]:
        """Tra ve JSON dung khuon `schema` (structured output)."""
        ...
