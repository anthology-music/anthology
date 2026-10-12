"""API schemas of the jobs domain."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from anthology.jobs.models import JobStatus, PriorityClass


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    status: JobStatus
    priority_class: PriorityClass
    created_by: uuid.UUID
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    total_items: int
    done_items: int
    failed_items: int
    progress: float
    error: str | None


class DemoJobRequest(BaseModel):
    items: int = Field(default=12, ge=1, le=1000)
    seconds_per_item: float = Field(default=1.0, ge=0.0, le=60.0)
    parallel_items: int = Field(default=1, ge=1, le=8)
