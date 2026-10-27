"""Transcode cache and the audio formats devices report.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    with op.batch_alter_table("devices") as batch:
        batch.add_column(sa.Column("supported_formats", sa.JSON(), nullable=True))
    op.create_table(
        "transcode_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("variant_key", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("audio_file_id", sa.Uuid(), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("bitrate_kbps", sa.Integer(), nullable=True),
        sa.Column("context_track_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("last_accessed_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            _allowed("kind", ("transcode", "tagged_copy")), name=op.f("ck_transcode_cache_kind")
        ),
        sa.CheckConstraint(
            _allowed("status", ("running", "ready", "failed")),
            name=op.f("ck_transcode_cache_status"),
        ),
        sa.ForeignKeyConstraint(
            ["audio_file_id"],
            ["audio_files.id"],
            name=op.f("fk_transcode_cache_audio_file_id_audio_files"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcode_cache")),
        sa.UniqueConstraint("variant_key", name=op.f("uq_transcode_cache_variant_key")),
    )
    op.create_index(
        op.f("ix_transcode_cache_audio_file_id"), "transcode_cache", ["audio_file_id"]
    )
    op.create_index(
        op.f("ix_transcode_cache_context_track_id"), "transcode_cache", ["context_track_id"]
    )
    op.create_index(
        "ix_transcode_cache_status_last_accessed_at",
        "transcode_cache",
        ["status", "last_accessed_at"],
    )


def downgrade() -> None:
    op.drop_table("transcode_cache")
    with op.batch_alter_table("devices") as batch:
        batch.drop_column("supported_formats")
