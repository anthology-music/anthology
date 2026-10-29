"""Personal data (spec: personal-data): playlists with folders, entries and edits for undo,
favorites, play history and maintained play statistics."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.core.changes import IdType
from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow

NAME = 255
# Position keys sort by bytes (personal_data.keys): the "C" collation on PostgreSQL.
KEY = String(255).with_variant(String(255, collation="C"), "postgresql")


class Visibility(enum.StrEnum):
    PRIVATE = "private"
    SHARED = "shared"


class EditKind(enum.StrEnum):
    ADD = "add"
    REMOVE = "remove"
    MOVE = "move"


class FavoriteTarget(enum.StrEnum):
    RECORDING = "recording"
    RELEASE = "release"
    ARTIST = "artist"


class PlaylistFolder(Base):
    __tablename__ = "playlist_folders"
    __table_args__ = (Index("ix_playlist_folders_user_name", "user_id", "name", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(NAME))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (
        Index("ix_playlists_owner_name", "owner_id", "name", "id"),
        Index("ix_playlists_visibility_name", "visibility", "name", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(NAME))
    visibility: Mapped[Visibility] = mapped_column(
        str_enum(Visibility, "visibility"), default=Visibility.PRIVATE
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playlist_folders.id", ondelete="SET NULL"), index=True
    )
    # Changes when the keys are rewritten (rebalancing): clients subscribe again.
    generation: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PlaylistEntry(Base):
    """A track context in a playlist. ``track_id`` has no foreign key: entries of deleted
    tracks are removed with change entries before the commit (like play queue entries)."""

    __tablename__ = "playlist_entries"
    __table_args__ = (Index("ix_playlist_entries_order", "playlist_id", "position_key", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    playlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"))
    track_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    position_key: Mapped[str] = mapped_column(KEY)
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PlaylistEdit(Base):
    """One edit of a playlist's entries, kept for undo (``entries_json``: the entries with
    their keys before and after)."""

    __tablename__ = "playlist_edits"
    __table_args__ = (Index("ix_playlist_edits_playlist_created", "playlist_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    playlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[EditKind] = mapped_column(str_enum(EditKind, "kind"))
    entries_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    undone_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    target_type: Mapped[FavoriteTarget] = mapped_column(
        str_enum(FavoriteTarget, "target_type"), primary_key=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PlayHistory(Base):
    """A counted play (spec: Play history): on a device, or on an output zone."""

    __tablename__ = "play_history"
    __table_args__ = (Index("ix_play_history_user_played", "user_id", "played_at", "id"),)

    id: Mapped[int] = mapped_column(IdType, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL")
    )
    output_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("output_zones.id", ondelete="SET NULL")
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), index=True
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"), index=True
    )
    played_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PlayStats(Base):
    """Play counts per user and recording, maintained with every counted play."""

    __tablename__ = "play_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"), primary_key=True
    )
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    last_played_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
