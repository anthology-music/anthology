"""Server configuration from environment variables with the prefix ``ANTHOLOGY_``."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTHOLOGY_", extra="ignore")

    data_dir: Path = Path("data")
    database_url: str = ""
    log_level: str = "INFO"
    migrations_dir: Path = SERVER_ROOT / "migrations"

    tagger_url: str = "http://localhost:8410"
    omr_url: str = ""
    source_services: str = ""

    @model_validator(mode="after")
    def _default_database_url(self) -> "Settings":
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{self.data_dir / 'anthology.db'}"
        return self

    @property
    def source_service_urls(self) -> list[str]:
        """Configured source service base URLs (ADR 0017)."""
        return [url.strip() for url in self.source_services.split(",") if url.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
