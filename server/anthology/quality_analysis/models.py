"""Results of the quality analysis, one per audio data (spec: quality-analysis)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow
from anthology.library.models import QualityStatus, QualityTier


class Confidence(enum.StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class QualityAnalysis(Base):
    """The analysis of one audio hash (equal audio data is analysed once)."""

    __tablename__ = "quality_analyses"

    audio_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[QualityStatus] = mapped_column(str_enum(QualityStatus, "status"))
    confidence: Mapped[Confidence] = mapped_column(str_enum(Confidence, "confidence"))
    # Finding code (e.g. "lossy_origin") and its measured values as JSON.
    finding: Mapped[str] = mapped_column(String(64))
    finding_values: Mapped[str] = mapped_column(Text, default="{}")
    # Unknown (None) unless the result has high confidence.
    effective_quality: Mapped[QualityTier | None] = mapped_column(
        str_enum(QualityTier, "effective_quality")
    )
    cutoff_hz: Mapped[int | None] = mapped_column(Integer)
    effective_sample_rate_hz: Mapped[int | None] = mapped_column(Integer)
    effective_bit_depth: Mapped[int | None] = mapped_column(Integer)
    estimated_bitrate_kbps: Mapped[int | None] = mapped_column(Integer)
    whole_file: Mapped[bool] = mapped_column(Boolean, default=False)
    method_version: Mapped[int] = mapped_column(Integer)
    analyzed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # A human decision from the review list; kept when the analysis runs again.
    decided_status: Mapped[QualityStatus | None] = mapped_column(
        str_enum(QualityStatus, "decided_status")
    )
    decided_quality: Mapped[QualityTier | None] = mapped_column(
        str_enum(QualityTier, "decided_quality")
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
