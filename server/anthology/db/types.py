"""Column types that behave the same on SQLite and PostgreSQL."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC timestamps; SQLite returns naive values, which are marked as UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; use timezone-aware UTC values")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def sort_text(length: int) -> String:
    """Normalized sort keys: byte order on PostgreSQL ("C"), like SQLite's BINARY and Python."""
    return String(length).with_variant(String(length, collation="C"), "postgresql")
