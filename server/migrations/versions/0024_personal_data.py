"""Playlists with folders, entries and edits, favorites, play history and play statistics.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
KEY = sa.String(255).with_variant(sa.String(255, collation="C"), "postgresql")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def _fk(column: str, table: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{target}.id"],
        name=op.f(f"fk_{table}_{column}_{target}"),
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.create_table(
        "playlist_folders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _fk("user_id", "playlist_folders", "users", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playlist_folders")),
    )
    op.create_index(
        "ix_playlist_folders_user_name", "playlist_folders", ["user_id", "name", "id"]
    )
    op.create_table(
        "playlists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("folder_id", sa.Uuid(), nullable=True),
        sa.Column("generation", sa.Uuid(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            _allowed("visibility", ("private", "shared")), name=op.f("ck_playlists_visibility")
        ),
        _fk("owner_id", "playlists", "users", "CASCADE"),
        _fk("folder_id", "playlists", "playlist_folders", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playlists")),
    )
    op.create_index("ix_playlists_owner_name", "playlists", ["owner_id", "name", "id"])
    op.create_index("ix_playlists_visibility_name", "playlists", ["visibility", "name", "id"])
    op.create_index(op.f("ix_playlists_folder_id"), "playlists", ["folder_id"])
    op.create_table(
        "playlist_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("playlist_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=False),
        sa.Column("position_key", KEY, nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=True),
        sa.Column("added_at", TIMESTAMP, nullable=False),
        _fk("playlist_id", "playlist_entries", "playlists", "CASCADE"),
        _fk("added_by", "playlist_entries", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playlist_entries")),
    )
    op.create_index(
        "ix_playlist_entries_order", "playlist_entries", ["playlist_id", "position_key", "id"]
    )
    op.create_index(op.f("ix_playlist_entries_track_id"), "playlist_entries", ["track_id"])
    op.create_table(
        "playlist_edits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("playlist_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("entries_json", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("undone_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            _allowed("kind", ("add", "remove", "move")), name=op.f("ck_playlist_edits_kind")
        ),
        _fk("playlist_id", "playlist_edits", "playlists", "CASCADE"),
        _fk("user_id", "playlist_edits", "users", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playlist_edits")),
    )
    op.create_index(
        "ix_playlist_edits_playlist_created", "playlist_edits", ["playlist_id", "created_at"]
    )
    op.create_index(op.f("ix_playlist_edits_created_at"), "playlist_edits", ["created_at"])
    op.create_table(
        "favorites",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            _allowed("target_type", ("recording", "release", "artist")),
            name=op.f("ck_favorites_target_type"),
        ),
        _fk("user_id", "favorites", "users", "CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "target_type", "target_id", name=op.f("pk_favorites")),
    )
    op.create_table(
        "play_history",
        sa.Column("id", ID, sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("output_zone_id", sa.Uuid(), nullable=True),
        sa.Column("track_id", sa.Uuid(), nullable=True),
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("played_at", TIMESTAMP, nullable=False),
        _fk("user_id", "play_history", "users", "CASCADE"),
        _fk("device_id", "play_history", "devices", "SET NULL"),
        _fk("output_zone_id", "play_history", "output_zones", "SET NULL"),
        _fk("track_id", "play_history", "tracks", "SET NULL"),
        _fk("recording_id", "play_history", "recordings", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_play_history")),
    )
    op.create_index(
        "ix_play_history_user_played", "play_history", ["user_id", "played_at", "id"]
    )
    op.create_index(op.f("ix_play_history_track_id"), "play_history", ["track_id"])
    op.create_index(op.f("ix_play_history_recording_id"), "play_history", ["recording_id"])
    op.create_table(
        "play_stats",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("play_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("last_played_at", TIMESTAMP, nullable=True),
        _fk("user_id", "play_stats", "users", "CASCADE"),
        _fk("recording_id", "play_stats", "recordings", "CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "recording_id", name=op.f("pk_play_stats")),
    )
    with op.batch_alter_table("play_queues") as batch:
        batch.add_column(sa.Column("counted_entry_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("play_queues") as batch:
        batch.drop_column("counted_entry_id")
    for table in (
        "play_stats",
        "play_history",
        "favorites",
        "playlist_edits",
        "playlist_entries",
        "playlists",
        "playlist_folders",
    ):
        op.drop_table(table)
