"""Server configuration from environment variables with the prefix ``ANTHOLOGY_``."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator, model_validator
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
    # IANA time zone of the installation; schedules (e.g. the maintenance) run in it.
    time_zone: str = "UTC"

    # Set by the image build (change first-release): the release, or "edge" for builds of main,
    # and the commit.
    build_version: str = ""
    build_commit: str = ""
    # Where LICENSE and THIRD_PARTY_LICENSES.md are (default: the image's /app/licenses, else
    # the repository root).
    licenses_dir: Path | None = None
    # The port the server listens on (the container publishes 8400).
    port: int = 8400
    # Playback on network outputs (spec: playback, Output discovery and addresses). Discovery
    # needs multicast (host networking); without it, admins enter the systems' addresses.
    output_discovery: bool = True
    # Raumfeld host addresses (host or host:port), comma-separated; added as entered ones.
    raumfeld_hosts: str = ""
    # The URL the speakers fetch media from, e.g. http://192.168.1.10:8400; empty: this host's
    # address on the route to the system with ``port`` (wrong behind port forwarding).
    output_media_url: str = ""

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
    # The public MusicBrainz service; end-to-end tests point it at a closed port so that they
    # never reach the real service.
    musicbrainz_public_url: str = "https://musicbrainz.org"
    musicbrainz_mirror_check_interval_seconds: float = 60.0
    # AcoustID application key of this installation; without it, fingerprint lookups are skipped.
    acoustid_api_key: str = ""
    # FFmpeg with Chromaprint (ADR 0020); the server image contains it on the PATH.
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    # Library storage; managed originals live in <library_dir>/_originals.
    # Default <data_dir>/library.
    library_dir: Path | None = None
    # Folders admins may import from (spec: library-import, Import roots), comma-separated.
    # Default <data_dir>/imports.
    import_roots: str = ""
    # Size limit of the shared transcode cache (spec: transcoding, Transcode cache size).
    transcode_cache_gb: float = 20.0
    # Transcodes running at once per server process.
    transcode_parallel: int = 2
    # Size limit of the cover thumbnails (spec: covers, Sizes and delivery).
    thumbnail_cache_mb: float = 512.0
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

    @field_validator("time_zone")
    @classmethod
    def _known_time_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"unknown time zone {value!r}") from error
        return value

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.time_zone)

    @property
    def source_service_urls(self) -> list[str]:
        """Configured source service base URLs (ADR 0017)."""
        return [url.strip() for url in self.source_services.split(",") if url.strip()]

    @property
    def library_path(self) -> Path:
        return self.library_dir or self.data_dir / "library"

    @property
    def import_root_paths(self) -> list[Path]:
        roots = [Path(root.strip()) for root in self.import_roots.split(",") if root.strip()]
        return roots or [self.data_dir / "imports"]

    @property
    def transcodes_dir(self) -> Path:
        # In the cache volume, which the tagger shares (it writes the tagged copies there).
        return self.data_dir / "cache" / "transcodes"

    @property
    def images_dir(self) -> Path:
        # Primary data (covers, gallery images): next to the originals, in the library's backups.
        return self.library_path / "_images"

    @property
    def cache_dir(self) -> Path:
        # The cache volume, shared with the tagger.
        return self.data_dir / "cache"

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
