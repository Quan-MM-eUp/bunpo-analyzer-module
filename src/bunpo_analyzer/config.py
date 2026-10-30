"""Cau hinh module, doc tu bien moi truong co tien to BUNPO_ (xem .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# vi + 15 ngon ngu trong thu muc i18n (muc 12.6 file ke hoach).
SUPPORTED_LANGS: tuple[str, ...] = (
    "vi", "en", "cn", "tw", "ko", "fr", "de", "es", "pt",
    "ru", "pl", "id", "th", "hi", "ne", "my",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUNPO_", env_file=".env", extra="ignore")

    # Kho du lieu: grammar/grammar_lib.json, word/word_lib.json, i18n/*.json.
    # Module khong chep kho vao package; kho sua den dau thi doc ban moi den do.
    data_dir: Path = Path("..")

    default_lang: str = "vi"
    # Gioi han do dai mot cau (muc 8 file kich ban). Chatbot da chan truoc,
    # module kiem tra lai de an toan.
    max_chars: int = Field(default=100, gt=0)

    # LLM chua chot nha cung cap. Tam dung OpenAI qua LLM gateway noi bo (key dev,
    # khong dung cho production). Doi nha cung cap / model chi can sua bien moi truong.
    llm_provider: str = "openai"
    # Chon tam (30/10): gpt-5-mini (suy nghi thap) - cau truc tot, re; ~8 s/cau.
    # Du phong / goi lai khi sai khuon: gpt-4.1 (nhanh, chinh xac nhat trong lan thu).
    llm_model: str = "gpt-5-mini"
    llm_fallback_model: str = "gpt-4.1"
    llm_timeout_s: float = Field(default=30, gt=0)
    llm_max_retries: int = Field(default=1, ge=0, le=3)  # goi lai khi loi tam thoi
    llm_max_tokens: int = Field(default=2000, gt=0)
    # Chi cho model "suy nghi" (gpt-5*, o-series): minimal | low | medium | high.
    llm_reasoning_effort: str = "low"
    openai_api_key: str = ""
    openai_base_url: str = "https://llm-api.eup.ai/v1"
    gemini_api_key: str = ""
    # Gia uoc tinh (USD / 1 trieu token: [vao, ra]) de ghi chi phi moi lan goi.
    # Kiem tra lai bang gia that cua gateway.
    llm_prices: dict[str, tuple[float, float]] = {
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-5-mini": (0.25, 2.00),
        "gpt-5-nano": (0.05, 0.40),
        "gpt-5": (1.25, 10.00),
    }

    # "Dich nhe" (muc 12.5): cau da co trong cache, nguoi dung ngon ngu khac mo ->
    # chi dich phan chu. Khong can suy nghi nen dung model nhanh, re.
    llm_light_model: str = "gpt-4.1-mini"

    # Cache (buoc 2.6, muc 3.6): memory (mac dinh, trong tien trinh) | redis | none.
    # Phien ban prompt, kho, tu dien, model nam trong khoa nen khong can xoa tay khi doi.
    cache_backend: str = "memory"
    cache_url: str = ""  # redis://host:6379/0 khi cache_backend=redis
    cache_ttl_s: int = Field(default=30 * 86400, gt=0)
    cache_max_items: int = Field(default=5000, gt=0)  # chi cho memory


@lru_cache
def get_settings() -> Settings:
    return Settings()
