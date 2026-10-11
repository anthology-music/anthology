from pathlib import Path

import pytest

from anthology.core.config import Settings


def test_defaults_use_sqlite_in_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHOLOGY_DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHOLOGY_DATA_DIR", raising=False)

    settings = Settings()

    assert settings.data_dir == Path("data")
    assert settings.database_url == "sqlite+aiosqlite:///data/anthology.db"
    assert settings.is_sqlite
    assert settings.source_service_urls == []


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHOLOGY_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/anthology")
    monkeypatch.setenv("ANTHOLOGY_SOURCE_SERVICES", "http://localhost:8420, http://localhost:8421,")

    settings = Settings()

    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/anthology"
    assert not settings.is_sqlite
    assert settings.source_service_urls == ["http://localhost:8420", "http://localhost:8421"]
