"""REST routes of outputs (spec: playback, Output picker, Output discovery and addresses, Zone
management): choosing the output of a device, system addresses (admins), volumes and grouping
(every signed-in user). What the systems, zones and rooms look like comes from the stream
``playback.outputs``."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import AdminSession, CurrentSession
from anthology.db import get_session
from anthology.playback import service
from anthology.playback.models import SystemOrigin
from anthology.playback.outputs.base import OutputError
from anthology.playback.outputs.registry import Outputs, UnknownOutput

router = APIRouter(tags=["playback"])

Session = Annotated[AsyncSession, Depends(get_session)]


class OutputIn(BaseModel):
    """The zone this device controls from now on; None: the device plays itself."""

    zone_id: str | None


class SystemIn(BaseModel):
    adapter: str = "raumfeld"
    # Host or host:port of the system.
    address: str = Field(min_length=1, max_length=255)


class SystemOut(BaseModel):
    id: str


class VolumeIn(BaseModel):
    volume: int | None = Field(default=None, ge=0, le=100)
    muted: bool | None = None


class RoomZoneIn(BaseModel):
    """The zone the room joins; None: a new zone of the room alone."""

    zone_id: str | None


def _outputs(request: Request) -> Outputs:
    return request.app.state.outputs


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_id") from error


async def _command(action) -> None:
    try:
        await action
    except UnknownOutput as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_output") from error
    except OutputError as error:
        detail = "output_offline" if str(error) == "offline" else "output_failed"
        code = (
            status.HTTP_409_CONFLICT if detail == "output_offline" else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, detail=detail) from error


@router.put("/playback/output", status_code=status.HTTP_204_NO_CONTENT)
async def select_output(
    request: Request, session: Session, current: CurrentSession, body: OutputIn
) -> None:
    """Hand this device's queue to a zone, or take it back (spec: Output picker)."""
    zone_id = _uuid(body.zone_id) if body.zone_id is not None else None
    try:
        stopped = await service.select_output(
            session, current.user_id, current.user_device_id, current.device_id, zone_id
        )
    except service.OutputUnavailable as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="output_offline") from error
    await session.commit()
    if stopped is not None:
        await _outputs(request).stop_zone(stopped)


@router.post("/playback/systems", status_code=status.HTTP_201_CREATED)
async def add_system(request: Request, _admin: AdminSession, body: SystemIn) -> SystemOut:
    """An output system the server cannot discover (no multicast, spec: Output discovery and
    addresses)."""
    outputs = _outputs(request)
    try:
        system = await outputs.add_system(body.adapter, body.address, SystemOrigin.MANUAL)
    except ValueError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_address"
        ) from error
    except UnknownOutput as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="unknown_adapter"
        ) from error
    return SystemOut(id=str(system.id))


@router.delete("/playback/systems/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_system(request: Request, _admin: AdminSession, system_id: str) -> None:
    await _command(_outputs(request).remove_system(_uuid(system_id)))


@router.put("/playback/zones/{zone_id}/volume", status_code=status.HTTP_204_NO_CONTENT)
async def zone_volume(
    request: Request, _current: CurrentSession, zone_id: str, body: VolumeIn
) -> None:
    await _command(_outputs(request).set_zone_volume(_uuid(zone_id), body.volume, body.muted))


@router.put("/playback/rooms/{room_id}/volume", status_code=status.HTTP_204_NO_CONTENT)
async def room_volume(
    request: Request, _current: CurrentSession, room_id: str, body: VolumeIn
) -> None:
    await _command(_outputs(request).set_room_volume(_uuid(room_id), body.volume, body.muted))


@router.put("/playback/rooms/{room_id}/zone", status_code=status.HTTP_204_NO_CONTENT)
async def join_zone(
    request: Request, _current: CurrentSession, room_id: str, body: RoomZoneIn
) -> None:
    """Add the room to a zone, or form a new zone of it alone (spec: Zone management)."""
    zone_id = _uuid(body.zone_id) if body.zone_id is not None else None
    await _command(_outputs(request).group(_uuid(room_id), zone_id))


@router.delete("/playback/rooms/{room_id}/zone", status_code=status.HTTP_204_NO_CONTENT)
async def leave_zone(request: Request, _current: CurrentSession, room_id: str) -> None:
    await _command(_outputs(request).ungroup(_uuid(room_id)))
