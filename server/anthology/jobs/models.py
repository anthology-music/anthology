"""Jobs, job items and maintained counters per status (spec: jobs)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


FINISHED = frozenset({JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED})


class PriorityClass(enum.StrEnum):
    INTERACTIVE = "interactive"
    BACKGROUND = "background"


class ItemOutcome(enum.StrEnum):
    NEW = "new"
    REPLACED = "replaced"
    ALREADY_PRESENT = "already_present"
    NOT_BETTER_THAN_EXISTING = "not_better_than_existing"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "priority_class", "status", "created_at"),
        Index("ix_jobs_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus, "status"))
    priority_class: Mapped[PriorityClass] = mapped_column(str_enum(PriorityClass, "priority_class"))
    parallel_items: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    done_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class JobItem(Base):
    __tablename__ = "job_items"
    __table_args__ = (UniqueConstraint("job_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(256))
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus, "status"))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    outcome: Mapped[ItemOutcome | None] = mapped_column(str_enum(ItemOutcome, "outcome"))
    message: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class JobCounter(Base):
    """Number of jobs per status, maintained with every status change."""

    __tablename__ = "job_counters"

    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus, "status"), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
