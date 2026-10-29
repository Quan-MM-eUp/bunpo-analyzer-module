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

    # LLM chua chot: tam dung Gemini. Ten model kiem tra lai khi lam buoc 2.1.
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.1-flash-lite"
    llm_fallback_model: str = "gemini-3-flash"
    llm_timeout_s: float = Field(default=20, gt=0)
    gemini_api_key: str = ""

    # Tang khi doi prompt: nam trong khoa cache (muc 3.6).
    prompt_version: str = "1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
