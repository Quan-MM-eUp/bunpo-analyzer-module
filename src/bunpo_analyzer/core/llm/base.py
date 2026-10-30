"""Interface chung cho moi nha cung cap LLM (buoc 2.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# timeout / unavailable: tam thoi, goi lai duoc. bad_output: tra sai khuon.
# config: sai key / sai ten model / gateway tu choi -> khong goi lai.
ErrorKind = Literal["timeout", "unavailable", "bad_output", "config", "quota"]


class LLMError(Exception):
    def __init__(self, kind: ErrorKind, message: str, model: str = "") -> None:
        super().__init__(f"[{kind}] {model}: {message}")
        self.kind = kind
        self.model = model

    @property
    def retryable(self) -> bool:
        return self.kind in ("timeout", "unavailable")


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    data: T
    model: str
    prompt_tokens: int = 0
    cached_tokens: int = 0  # phan prompt trung voi lan goi truoc (nha cung cap tinh gia re hon)
    completion_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    attempts: int = 1  # tong so lan goi (ke ca lan loi)
    used_fallback: bool = False
    mode: str = "json_schema"  # json_schema | json_object (gateway khong ho tro schema)


class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        messages: list[Message],
        output_model: type[T],
        model: str,
        timeout_s: float,
        max_tokens: int,
    ) -> LLMResult[T]:
        """Goi model, tra du lieu da kiem tra theo `output_model` (structured output).

        Loi phai nem LLMError voi kind phu hop."""
        ...


# Ti le gia token vao da luu dem so voi gia thuong (OpenAI: dong 4.1 = 25%, dong 5 = 10%).
CACHED_RATIO = {"gpt-4.1": 0.25, "gpt-4o": 0.5, "gpt-5": 0.1}


def estimate_cost(prices: dict[str, tuple[float, float]], model: str, p_tok: int, c_tok: int, cached: int = 0) -> float:
    pin, pout = prices.get(model, (0.0, 0.0))
    ratio = next((r for k, r in CACHED_RATIO.items() if model.startswith(k)), 1.0)
    cached = min(cached, p_tok)
    return round(((p_tok - cached) * pin + cached * pin * ratio + c_tok * pout) / 1_000_000, 6)
