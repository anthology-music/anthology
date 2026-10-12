"""Configuration from environment variables (prefix ANTHOLOGY_TAGGER_)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTHOLOGY_TAGGER_")

    # Comma-separated roots the tagger may access (the shared volumes).
    roots: str = "/data/library,/data/cache,/data/imports"
    # Copies, extracted images and the journal must lie below this root.
    cache_root: str = "/data/cache"
    journal_dir: str = "/data/cache/tagger/journal"
    max_batch: int = 200
    # Empty = all interfaces, IPv4 and IPv6 (one socket each), so "localhost" works when it
    # resolves to ::1 first. The port is reachable inside the pod only, it is not published.
    host: str = ""
    port: int = 8410

    def root_paths(self) -> list[Path]:
        return [Path(root).resolve() for root in self.roots.split(",") if root.strip()]

    def cache_path(self) -> Path:
        return Path(self.cache_root).resolve()
