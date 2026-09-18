"""Environment-backed settings. See .env.example for documentation of each field."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
PROMPTS_DIR = APP_DIR / "prompts"
SUBJECTS_DIR = APP_DIR / "subjects"
EVAL_DIR = BACKEND_DIR / "eval"
EVAL_CASES_DIR = EVAL_DIR / "cases"
EVAL_RESULTS_DIR = EVAL_DIR / "results"
CACHE_DIR = BACKEND_DIR / ".cache"
USAGE_LOG = BACKEND_DIR / "usage.jsonl"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    max_image_edge: int = Field(default=1600, ge=256, le=8000)
    verify_timeout_seconds: float = Field(default=10.0, gt=0)
    monthly_budget_usd: float = Field(default=20.0, ge=0)
    recognition_cache_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
