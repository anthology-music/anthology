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
    host: str = "0.0.0.0"  # noqa: S104 - reachable inside the pod only, no published port
    port: int = 8410

    def root_paths(self) -> list[Path]:
        return [Path(root).resolve() for root in self.roots.split(",") if root.strip()]

    def cache_path(self) -> Path:
        return Path(self.cache_root).resolve()
