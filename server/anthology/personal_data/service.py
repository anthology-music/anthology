"""Favorites and play history (spec: personal-data, Favorites, Play history, Imported play
counts).

Favorites are personal (scope ``user``). Plays are counted by the server from the positions
its play queues receive (devices every few seconds, zone players while they play): once the
current entry reaches half its track or four minutes, the play is recorded once for that entry,
with ``PlayStats`` maintained in the same transaction.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.db.types import utcnow
from anthology.library.models import Artist, Recording, Release, Track
from anthology.personal_data.models import Favorite, FavoriteTarget, PlayHistory, PlayStats
from anthology.playback import service as playback
from anthology.playback.models import PlayQueue, PlayQueueEntry

FAVORITE = "favorite"
PLAY = "play"
# A play counts after half the track or four minutes, whichever comes first.
THRESHOLD_MS = 4 * 60 * 1000
TARGETS = {
    FavoriteTarget.RECORDING: Recording,
    FavoriteTarget.RELEASE: Release,
    FavoriteTarget.ARTIST: Artist,
}


class UnknownTarget(LookupError):
    pass


def favorite_id(user_id: uuid.UUID, target_type: FavoriteTarget, target_id: uuid.UUID):
    """Change entries name a favorite by one UUID."""
    return uuid.uuid5(target_id, f"{user_id}:{target_type.value}")


async def set_favorite(
    session: AsyncSession,
    user_id: uuid.UUID,
    target_type: FavoriteTarget,
    target_id: uuid.UUID,
    favorite: bool,
) -> bool:
    """Mark or unmark; returns whether anything changed."""
    if await session.get(TARGETS[target_type], target_id) is None:
        raise UnknownTarget(target_id)
    row = await session.get(Favorite, (user_id, target_type, target_id))
    if favorite == (row is not None):
        return False
    if favorite:
        session.add(Favorite(user_id=user_id, target_type=target_type, target_id=target_id))
        operation = ChangeOperation.INSERT
    else:
        await session.delete(row)
        operation = ChangeOperation.DELETE
    await session.flush()
    await record_change(
        session,
        entity_type=FAVORITE,
        entity_id=favorite_id(user_id, target_type, target_id),
        operation=operation,
        scope=ChangeScope.USER,
        owner_user_id=user_id,
    )
    return True


# --- plays ------------------------------------------------------------------------------------


def threshold(duration_ms: int) -> int:
    return min(duration_ms // 2, THRESHOLD_MS) if duration_ms > 0 else THRESHOLD_MS


async def record_play(
    session: AsyncSession,
    user_id: uuid.UUID,
    track_id: uuid.UUID,
    *,
    device_id: uuid.UUID | None = None,
    output_zone_id: uuid.UUID | None = None,
) -> PlayHistory | None:
    track = await session.get(Track, track_id)
    if track is None:
        return None
    now = utcnow()
    play = PlayHistory(
        user_id=user_id,
        device_id=device_id,
        output_zone_id=output_zone_id,
        track_id=track.id,
        recording_id=track.recording_id,
        played_at=now,
    )
    session.add(play)
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    await session.execute(
        insert(PlayStats)
        .values(
            user_id=user_id,
            recording_id=track.recording_id,
            play_count=1,
            imported_count=0,
            last_played_at=now,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "recording_id"],
            set_={"play_count": PlayStats.play_count + 1, "last_played_at": now},
        )
    )
    await session.flush()
    await record_change(
        session,
        entity_type=PLAY,
        entity_id=uuid.UUID(int=play.id),
        operation=ChangeOperation.INSERT,
        scope=ChangeScope.USER,
        owner_user_id=user_id,
    )
    return play


async def add_imported_count(
    session: AsyncSession, user_id: uuid.UUID, recording_id: uuid.UUID, count: int
) -> None:
    """Plays counted by another application: added to the count, no history (spec: Imported
    play counts)."""
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    await session.execute(
        insert(PlayStats)
        .values(user_id=user_id, recording_id=recording_id, play_count=0, imported_count=count)
        .on_conflict_do_update(
            index_elements=["user_id", "recording_id"],
            set_={"imported_count": PlayStats.imported_count + count},
        )
    )


async def play_count(session: AsyncSession, user_id: uuid.UUID, recording_id: uuid.UUID) -> int:
    stats = await session.get(PlayStats, (user_id, recording_id))
    return stats.play_count + stats.imported_count if stats else 0


async def _position(session: AsyncSession, queue: PlayQueue) -> None:
    """Count the current entry's play once it passed the threshold (a queue listener)."""
    entry_id = queue.current_entry_id
    if entry_id is None or queue.counted_entry_id == entry_id:
        return
    user_id = queue.user_id or queue.controlled_by
    if user_id is None:
        return
    row = (
        await session.execute(
            select(PlayQueueEntry.track_id, Recording.duration_ms)
            .join(Track, Track.id == PlayQueueEntry.track_id)
            .join(Recording, Recording.id == Track.recording_id)
            .where(PlayQueueEntry.id == entry_id)
        )
    ).first()
    if row is None or queue.position_ms < threshold(row.duration_ms):
        return
    queue.counted_entry_id = entry_id
    await record_play(
        session,
        user_id,
        row.track_id,
        device_id=queue.device_id,
        output_zone_id=queue.output_zone_id,
    )


playback.on_position(_position)
