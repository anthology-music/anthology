"""REST routes of the metadata-lookup domain."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from anthology.api.deps import AdminSession
from anthology.core.services import ServiceState

router = APIRouter(tags=["metadata-lookup"])


class LookupStatusOut(BaseModel):
    """Queued MusicBrainz work and the mirror (spec: Mirror recommendation)."""

    mirror_configured: bool
    mirror_status: ServiceState | None
    queued_requests: int
    estimated_seconds: float
    mirror_recommended: bool


@router.get("/metadata-lookup/status")
async def lookup_status(request: Request, _admin: AdminSession) -> LookupStatusOut:
    status = await request.app.state.lookups.status()
    return LookupStatusOut(
        mirror_configured=status.mirror_configured,
        mirror_status=status.mirror_status,
        queued_requests=status.queued,
        estimated_seconds=status.estimated_seconds,
        mirror_recommended=status.mirror_recommended,
    )
