"""Async engine and session factory for SQLite (development, tests) and PostgreSQL."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine

from anthology.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    if settings.is_sqlite:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = _create_async_engine(settings.database_url)
        event.listen(engine.sync_engine, "connect", _sqlite_pragmas)
        return engine
    return _create_async_engine(settings.database_url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
