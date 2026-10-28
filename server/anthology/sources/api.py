"""REST routes of sources (spec: sources): search, links with duplicate status, logins."""

import asyncio
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import require_role
from anthology.db import get_session
from anthology.sources import duplicates, orders
from anthology.sources.client import SourceServiceError
from anthology.sources.models import DownloadOrderItem, OrderItemState, SourceService
from anthology.sources.schemas import (
    LoginField,
    LoginIn,
    LoginOut,
    OrderIn,
    OrderOut,
    ResolvedTrack,
    ResolveIn,
    ResolveOut,
    SearchIn,
    SearchResult,
    ServiceResults,
    clean,
)
from anthology.sources.service import SourceServices
from anthology.users.models import Role
from anthology.users.service import SessionInfo

router = APIRouter(tags=["sources"])

Session = Annotated[AsyncSession, Depends(get_session)]
Editor = Annotated[SessionInfo, Depends(require_role(Role.ADMIN, Role.EDITOR))]
Admin = Annotated[SessionInfo, Depends(require_role(Role.ADMIN))]

# A slow service must not hold up the others (spec: Search and links).
SEARCH_TIMEOUT = 10.0


def _services(request: Request) -> SourceServices:
    return request.app.state.sources


async def _service(session: AsyncSession, service_id: str) -> SourceService:
    try:
        row = await session.get(SourceService, uuid.UUID(service_id))
    except ValueError:
        row = None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_service")
    return row


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail="service_unavailable")


def _failed(error: SourceServiceError) -> HTTPException:
    if error.code == "unsupported_link":
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="no_source_for_link")
    if error.code == "not_found":
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=error.code)


# --- search and links -----------------------------------------------------------------------


@router.post("/sources/search")
async def search(
    request: Request, session: Session, _current: Editor, body: SearchIn
) -> list[ServiceResults]:
    """Search the available services (all or one), each with its own results and error."""
    query = select(SourceService).where(SourceService.available.is_(True))
    if body.service is not None:
        query = query.where(SourceService.id == (await _service(session, body.service)).id)
    rows = [row for row in await session.scalars(query.order_by(SourceService.position))]
    rows = [row for row in rows if (row.capabilities or {}).get("search", True)]
    services = _services(request)

    async def ask(row: SourceService) -> ServiceResults:
        try:
            answer = await asyncio.wait_for(
                services.client(row.url).search(
                    body.query, list(body.kinds), body.page, body.page_size
                ),
                SEARCH_TIMEOUT,
            )
        except TimeoutError:
            return ServiceResults(service=str(row.id), results=[], next_page=None, error="timeout")
        except SourceServiceError as error:
            return ServiceResults(service=str(row.id), results=[], next_page=None, error=error.code)
        results = [
            SearchResult.model_validate(clean(SearchResult, item))
            for item in answer.get("results") or []
            if isinstance(item, dict) and item.get("ref") and item.get("title")
        ]
        page = answer.get("next_page")
        return ServiceResults(
            service=str(row.id), results=results, next_page=page if isinstance(page, int) else None
        )

    return list(await asyncio.gather(*(ask(row) for row in rows)))


def _matches(row: SourceService, url: str) -> bool:
    for pattern in (row.capabilities or {}).get("link_patterns") or []:
        try:
            if re.search(str(pattern), url):
                return True
        except re.error:
            continue
    return False


@router.post("/sources/resolve")
async def resolve(
    request: Request, session: Session, _current: Editor, body: ResolveIn
) -> ResolveOut:
    """The tracks of a link or search result with their duplicate status."""
    if body.url is not None:
        rows = await session.scalars(
            select(SourceService)
            .where(SourceService.available.is_(True))
            .order_by(SourceService.position)
        )
        row = next((row for row in rows if _matches(row, body.url.strip())), None)
        if row is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="no_source_for_link")
    else:
        row = await _service(session, body.service or "")
        if not row.available:
            raise _unavailable()
    try:
        answer = (
            await _services(request)
            .client(row.url)
            .resolve(url=body.url.strip() if body.url else None, ref=body.ref)
        )
    except SourceServiceError as error:
        raise _failed(error) from error
    tracks = []
    for raw in answer.get("tracks") or []:
        fields = clean(ResolvedTrack, raw)
        if not fields.get("ref") or not fields.get("title"):
            continue
        existing = await duplicates.check(session, raw)
        tracks.append(
            ResolvedTrack.model_validate(
                {
                    **fields,
                    "status": existing.status,
                    "recording_id": str(existing.recording_id) if existing.recording_id else None,
                    "existing_quality": existing.quality,
                }
            )
        )
    item = answer.get("item") or {}
    return ResolveOut(
        service=str(row.id),
        item=SearchResult.model_validate(clean(SearchResult, item))
        if item.get("ref") and item.get("title")
        else SearchResult(ref=body.ref or body.url or "", kind="album", title=""),
        tracks=tracks,
    )


# --- orders ---------------------------------------------------------------------------------


@router.post("/sources/orders", status_code=status.HTTP_202_ACCEPTED)
async def order(request: Request, session: Session, current: Editor, body: OrderIn) -> OrderOut:
    """Order tracks of a resolved item (spec: Download orders); present tracks are not
    downloaded."""
    row = await _service(session, body.service)
    try:
        created = await orders.create(
            session,
            _services(request),
            request.app.state.settings,
            service=row,
            ref=body.ref,
            tracks=body.tracks,
            quality=body.quality,
            created_by=current.user_id,
        )
    except orders.OrderError as error:
        if error.code == "service_unavailable":
            raise _unavailable() from error
        if error.code in ("no_tracks", "not_found"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="no_tracks"
            ) from error
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=error.code) from error
    present = await session.scalar(
        select(func.count()).where(
            DownloadOrderItem.order_id == created.id,
            DownloadOrderItem.state == OrderItemState.SKIPPED,
        )
    )
    total = await session.scalar(
        select(func.count()).where(DownloadOrderItem.order_id == created.id)
    )
    await session.commit()
    return OrderOut(
        order_id=str(created.id),
        job_id=str(created.job_id),
        items=total or 0,
        already_present=present or 0,
    )


# --- logins ---------------------------------------------------------------------------------


async def _login_out(services: SourceServices, row: SourceService) -> LoginOut:
    stored = await services.stored_names(row.service_id)
    return LoginOut(
        fields=[LoginField.model_validate(clean(LoginField, f)) for f in row.login_fields or []],
        stored=bool(stored),
        stored_fields=stored,
        logged_in=row.logged_in,
        problem=row.problem,
    )


@router.get("/sources/services/{service_id}/login")
async def get_login(
    request: Request, session: Session, _current: Admin, service_id: str
) -> LoginOut:
    """The login fields a service asks for and whether values are stored; never the values."""
    return await _login_out(_services(request), await _service(session, service_id))


@router.put("/sources/services/{service_id}/login")
async def put_login(
    request: Request, session: Session, _current: Admin, service_id: str, body: LoginIn
) -> LoginOut:
    """Store the login fields encrypted and log the service in (spec: Source service login);
    empty fields keep their stored values."""
    row = await _service(session, service_id)
    names = {str(field.get("name")) for field in row.login_fields or []}
    if not names or set(body.fields) - names:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="unknown_fields")
    services = _services(request)
    try:
        updated = await services.save_login(row.id, body.fields)
    except SourceServiceError as error:
        raise _failed(error) from error
    return await _login_out(services, updated)


@router.delete("/sources/services/{service_id}/login", status_code=status.HTTP_204_NO_CONTENT)
async def delete_login(
    request: Request, session: Session, _current: Admin, service_id: str
) -> None:
    await _services(request).forget_login((await _service(session, service_id)).id)
