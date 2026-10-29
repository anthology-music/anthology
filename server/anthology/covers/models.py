"""Images and the gallery (spec: covers, Images stored once, Image gallery). The front covers
are ``front_image_id`` of releases and recordings (library)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow


class ImageKind(enum.StrEnum):
    FRONT = "front"
    BACK = "back"
    BOOKLET = "booklet"
    DISC = "disc"
    OTHER = "other"


class Image(Base):
    """One image, stored once by its content (``<library>/_images/<xx>/<sha256>``)."""

    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    mime: Mapped[str] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ReleaseImage(Base):
    """A gallery image of a release; Cover Art Archive images keep their URL until the gallery
    is first opened."""

    __tablename__ = "release_images"
    __table_args__ = (Index("ix_release_images_order", "release_id", "position", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"))
    kind: Mapped[ImageKind] = mapped_column(str_enum(ImageKind, "kind"))
    position: Mapped[int] = mapped_column(Integer)
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("images.id", ondelete="RESTRICT"), index=True
    )
    remote_url: Mapped[str | None] = mapped_column(Text)
