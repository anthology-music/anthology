"""Images, the release gallery and front covers of releases and recordings.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = ("front", "back", "booklet", "disc", "other")


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime", sa.String(32), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_images")),
        sa.UniqueConstraint("sha256", name=op.f("uq_images_sha256")),
    )
    op.create_table(
        "release_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=True),
        sa.Column("remote_url", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"kind IN ({', '.join(f"'{kind}'" for kind in KINDS)})",
            name=op.f("ck_release_images_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["releases.id"],
            name=op.f("fk_release_images_release_id_releases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["images.id"],
            name=op.f("fk_release_images_image_id_images"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_images")),
    )
    op.create_index(
        "ix_release_images_order", "release_images", ["release_id", "position", "id"]
    )
    op.create_index(op.f("ix_release_images_image_id"), "release_images", ["image_id"])
    for table in ("releases", "recordings"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("front_image_id", sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                op.f(f"fk_{table}_front_image_id_images"),
                "images",
                ["front_image_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_index(op.f(f"ix_{table}_front_image_id"), ["front_image_id"])


def downgrade() -> None:
    for table in ("recordings", "releases"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(op.f(f"ix_{table}_front_image_id"))
            batch.drop_constraint(op.f(f"fk_{table}_front_image_id_images"), type_="foreignkey")
            batch.drop_column("front_image_id")
    op.drop_table("release_images")
    op.drop_table("images")
