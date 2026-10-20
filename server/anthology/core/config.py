"""Server configuration from environment variables with the prefix ``ANTHOLOGY_``."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

SERVER_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTHOLOGY_", extra="ignore")

    data_dir: Path = Path("data")
    database_url: str = ""
    # File with the database password (Podman/Compose secret); replaces the URL's password.
    database_password_file: Path | None = None
    # Built web client (client/dist/spa); served next to the API when set.
    web_dir: Path | None = None
    log_level: str = "INFO"
    migrations_dir: Path = SERVER_ROOT / "migrations"

    access_token_ttl_seconds: int = 15 * 60
    session_cache_ttl_seconds: float = 5.0
    media_url_client_ttl_seconds: int = 60 * 60
    media_url_output_max_ttl_seconds: int = 24 * 60 * 60
    media_key_overlap_seconds: int = 24 * 60 * 60
    sync_changelog_retention_days: int = 7
    background_tasks: bool = True
    ws_hello_timeout_seconds: float = 10.0
    dev_demo: bool = False
    jobs_throttle: Literal["gentle", "normal", "fast"] = "normal"
    jobs_interactive_slots: int = 2
    jobs_lease_seconds: float = 30.0

    tagger_url: str = "http://localhost:8410"
    tagger_batch_size: int = 200
    tagger_timeout_seconds: float = 30.0
    service_check_interval_seconds: float = 30.0
    service_retry_interval_seconds: float = 5.0
    # Metadata lookup (spec: metadata-lookup). The contact goes into the User-Agent that
    # MusicBrainz requires; without one, the project's address is sent.
    musicbrainz_contact: str = ""
    # Base URL of an optional local MusicBrainz mirror (docs/architecture/musicbrainz-mirror.md).
    musicbrainz_url: str = ""
    musicbrainz_mirror_check_interval_seconds: float = 60.0
    # AcoustID application key of this installation; without it, fingerprint lookups are skipped.
    acoustid_api_key: str = ""
    # FFmpeg with Chromaprint (ADR 0020); the server image contains it on the PATH.
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    omr_url: str = ""
    source_services: str = ""

    @model_validator(mode="after")
    def _default_database_url(self) -> "Settings":
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{self.data_dir / 'anthology.db'}"
        if self.database_password_file is not None:
            password = self.database_password_file.read_text().strip()
            url = make_url(self.database_url).set(password=password)
            self.database_url = url.render_as_string(hide_password=False)
        return self

    @property
    def source_service_urls(self) -> list[str]:
        """Configured source service base URLs (ADR 0017)."""
        return [url.strip() for url in self.source_services.split(",") if url.strip()]

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
