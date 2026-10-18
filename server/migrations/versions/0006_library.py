"""Library: artists, release groups, releases, recordings, tracks, audio files and counters.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
NAME = sa.String(length=512)
# Normalized sort keys compare bytes on both engines (see anthology.db.types.sort_text).
SORT = sa.String(length=512).with_variant(sa.String(length=512, collation="C"), "postgresql")
RELEASE_GROUP_TYPES = ("album", "ep", "single", "compilation", "live", "soundtrack", "other")
FORMATS = ("flac", "wav", "aiff", "alac", "mp3", "aac", "opus", "vorbis")
QUALITY_TIERS = ("hires_lossless", "cd_lossless", "lossy_high", "lossy_low")
COUNTERS = ("artists", "releases", "tracks", "recordings")


def _check_in(table: str, column: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=op.f(f"ck_{table}_{column}"))


def upgrade() -> None:
    op.create_table(
        "artists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", NAME, nullable=False),
        sa.Column("sort_name", SORT, nullable=False),
        sa.Column("mb_artist_id", sa.Uuid(), nullable=True),
        sa.Column("release_count", sa.Integer(), nullable=False),
        sa.Column("track_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artists")),
        sa.UniqueConstraint("mb_artist_id", name=op.f("uq_artists_mb_artist_id")),
    )
    op.create_index("ix_artists_sort", "artists", ["sort_name", "id"])

    op.create_table(
        "release_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", NAME, nullable=False),
        sa.Column("type", ENUM, nullable=False),
        sa.Column("mb_release_group_id", sa.Uuid(), nullable=True),
        _check_in("release_groups", "type", RELEASE_GROUP_TYPES),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_groups")),
        sa.UniqueConstraint(
            "mb_release_group_id", name=op.f("uq_release_groups_mb_release_group_id")
        ),
    )

    op.create_table(
        "releases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("release_group_id", sa.Uuid(), nullable=False),
        sa.Column("title", NAME, nullable=False),
        sa.Column("album_artist_id", sa.Uuid(), nullable=False),
        sa.Column("album_artist_display", NAME, nullable=False),
        sa.Column("edition", sa.String(length=256), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("disc_count", sa.Integer(), nullable=False),
        sa.Column("track_count", sa.Integer(), nullable=False),
        sa.Column("sort_title", SORT, nullable=False),
        sa.Column("sort_album_artist", SORT, nullable=False),
        sa.Column("mb_release_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["album_artist_id"],
            ["artists.id"],
            name=op.f("fk_releases_album_artist_id_artists"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_group_id"],
            ["release_groups.id"],
            name=op.f("fk_releases_release_group_id_release_groups"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_releases")),
        sa.UniqueConstraint("mb_release_id", name=op.f("uq_releases_mb_release_id")),
    )
    op.create_index(
        "ix_releases_sort", "releases", ["sort_album_artist", "sort_title", "id"]
    )
    op.create_index(
        "ix_releases_album_artist_sort", "releases", ["album_artist_id", "sort_title", "id"]
    )
    op.create_index(op.f("ix_releases_release_group_id"), "releases", ["release_group_id"])

    op.create_table(
        "recordings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", NAME, nullable=False),
        sa.Column("artist_id", sa.Uuid(), nullable=False),
        sa.Column("artist_display", NAME, nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("isrc", sa.String(length=12), nullable=True),
        sa.Column("mb_recording_id", sa.Uuid(), nullable=True),
        sa.Column("acoust_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["artist_id"],
            ["artists.id"],
            name=op.f("fk_recordings_artist_id_artists"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recordings")),
        sa.UniqueConstraint("mb_recording_id", name=op.f("uq_recordings_mb_recording_id")),
    )
    op.create_index(op.f("ix_recordings_artist_id"), "recordings", ["artist_id"])
    op.create_index(op.f("ix_recordings_isrc"), "recordings", ["isrc"])
    op.create_index(op.f("ix_recordings_acoust_id"), "recordings", ["acoust_id"])

    op.create_table(
        "tracks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("disc_number", sa.Integer(), nullable=False),
        sa.Column("track_number", sa.Integer(), nullable=False),
        sa.Column("context_title", NAME, nullable=True),
        sa.Column("context_artist", NAME, nullable=True),
        sa.Column("sort_artist", SORT, nullable=False),
        sa.Column("sort_title", SORT, nullable=False),
        sa.Column("sort_album", SORT, nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            name=op.f("fk_tracks_recording_id_recordings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["releases.id"],
            name=op.f("fk_tracks_release_id_releases"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracks")),
    )
    op.create_index(
        "ix_tracks_sort", "tracks", ["sort_artist", "sort_title", "sort_album", "id"]
    )
    op.create_index(
        "ix_tracks_release_position",
        "tracks",
        ["release_id", "disc_number", "track_number", "id"],
    )
    op.create_index(op.f("ix_tracks_recording_id"), "tracks", ["recording_id"])

    op.create_table(
        "audio_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("format", ENUM, nullable=False),
        sa.Column("codec", sa.String(length=32), nullable=False),
        sa.Column("bitrate_kbps", sa.Integer(), nullable=True),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column("bit_depth", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("audio_hash", sa.String(length=128), nullable=False),
        sa.Column("declared_quality", ENUM, nullable=False),
        sa.Column("effective_quality", ENUM, nullable=True),
        sa.Column("home_track_id", sa.Uuid(), nullable=True),
        sa.Column("added_at", TIMESTAMP, nullable=False),
        _check_in("audio_files", "format", FORMATS),
        _check_in("audio_files", "declared_quality", QUALITY_TIERS),
        _check_in("audio_files", "effective_quality", QUALITY_TIERS),
        sa.ForeignKeyConstraint(
            ["home_track_id"],
            ["tracks.id"],
            name=op.f("fk_audio_files_home_track_id_tracks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            name=op.f("fk_audio_files_recording_id_recordings"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audio_files")),
        sa.UniqueConstraint("path", name=op.f("uq_audio_files_path")),
        sa.UniqueConstraint("recording_id", name=op.f("uq_audio_files_recording_id")),
    )
    op.create_index(op.f("ix_audio_files_audio_hash"), "audio_files", ["audio_hash"])
    op.create_index(op.f("ix_audio_files_home_track_id"), "audio_files", ["home_track_id"])

    counters = op.create_table(
        "library_counters",
        sa.Column("name", ENUM, nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        _check_in("library_counters", "name", COUNTERS),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_library_counters")),
    )
    op.bulk_insert(counters, [{"name": name, "value": 0} for name in COUNTERS])


def downgrade() -> None:
    op.drop_table("library_counters")
    op.drop_table("audio_files")
    op.drop_table("tracks")
    op.drop_table("recordings")
    op.drop_table("releases")
    op.drop_table("release_groups")
    op.drop_table("artists")
