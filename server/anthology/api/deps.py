"""Request dependencies: authenticated session, roles and signed media URLs."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from anthology.core.media_urls import InvalidMediaUrlError, MediaGrant
from anthology.core.security import InvalidTokenError, decode_access_token
from anthology.users.models import Role
from anthology.users.service import SessionInfo

_bearer = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="not_authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def current_session(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> SessionInfo:
    if credentials is None:
        raise UNAUTHORIZED
    try:
        claims = decode_access_token(request.app.state.token_key, credentials.credentials)
    except InvalidTokenError as error:
        raise UNAUTHORIZED from error
    info = await request.app.state.session_cache.get(claims.user_device_id)
    if info is None or info.user_id != claims.user_id:
        raise UNAUTHORIZED
    return info


CurrentSession = Annotated[SessionInfo, Depends(current_session)]


def require_role(*roles: Role) -> Callable[[SessionInfo], Awaitable[SessionInfo]]:
    async def check(session: CurrentSession) -> SessionInfo:
        if session.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return session

    return check


AdminSession = Annotated[SessionInfo, Depends(require_role(Role.ADMIN))]


async def media_grant(request: Request) -> MediaGrant:
    """Verify a signed media URL and check that user and target are still allowed."""
    try:
        grant = request.app.state.media_signer.verify(request.url.path, dict(request.query_params))
    except InvalidMediaUrlError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid_url") from error
    info = await request.app.state.session_cache.get(grant.target_id)
    if info is not None and info.user_id == grant.user_id:
        return grant
    # A URL handed to an output zone (spec: playback, Delivery to outputs).
    outputs = getattr(request.app.state, "outputs", None)
    if (
        info is None
        and outputs is not None
        and await outputs.allows(grant.user_id, grant.target_id)
    ):
        return grant
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="revoked")


MediaAccess = Annotated[MediaGrant, Depends(media_grant)]
