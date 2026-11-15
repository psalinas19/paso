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
DATA_DIR = BACKEND_DIR / "data"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
USAGE_LOG = BACKEND_DIR / "usage.jsonl"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    #: How hard the model thinks before answering: low, medium, high, xhigh or
    #: max. Empty leaves the API default (high). Lower is faster and cheaper;
    #: whether reading and explanations stay as good has to be measured with
    #: `app.eval` (SPEC 12.4).
    anthropic_effort: str = ""
    #: Optional cheaper model for the chat (SPEC 4). Empty = the same model.
    #: It needs a price in app/llm/pricing.yaml like any other.
    anthropic_model_chat: str = ""

    max_image_edge: int = Field(default=1600, ge=256, le=8000)
    verify_timeout_seconds: float = Field(default=10.0, gt=0)
    monthly_budget_usd: float = Field(default=20.0, ge=0)
    recognition_cache_enabled: bool = True

    # --- HTTP API (phase 2) ---
    #: Shared secret the notebook sends as "Authorization: Bearer ...". Empty
    #: means the API refuses every request: an open proxy to a paid API is not
    #: a default anyone should get by accident.
    app_token: str = ""
    #: Comma-separated origins allowed to call the API from a browser.
    allowed_origins: str = (
        "https://paso-libreta.paso-frontend.workers.dev,http://localhost:4173,"
        # The last one is the native iPad shell (Capacitor).
        "http://localhost:5173,capacitor://localhost"
    )
    data_dir: Path = DATA_DIR
    #: Empty = SQLite file inside data_dir.
    database_url: str = ""

    # --- backups (phase 5) ---
    #: Run the daily backup from inside the API process. Off on a laptop, on in
    #: the server: there it is the only thing standing between a dead disk and
    #: every review ever made.
    backup_enabled: bool = False
    #: Where the archives are written. Empty = "backups" beside data_dir.
    backup_dir: Path | None = None
    #: An rclone destination (for example "r2:paso-respaldos") that is NOT on
    #: this server. Empty = the archives stay on this disk only, which protects
    #: against a bad day but not against losing the server.
    backup_remote: str = ""
    #: Keep every archive this many days, then one per week, then one per month.
    backup_keep_days: int = Field(default=14, ge=1)
    backup_keep_weeks: int = Field(default=8, ge=0)
    backup_keep_months: int = Field(default=12, ge=0)

    @property
    def resolved_backup_dir(self) -> Path:
        return self.backup_dir or self.data_dir.parent / "backups"

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'paso.db').as_posix()}"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
