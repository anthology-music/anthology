"""Streams of personal data (spec: personal-data, Large playlists; sync-protocol):
``personal.playlists`` (own and shared), ``personal.playlist_folders`` (own),
``personal.playlist.entries`` (one playlist in order), ``personal.favorites`` and
``personal.history`` (newest first). Every list pages by its key."""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library import streams as library
from anthology.library.models import Artist, Recording, Release, Track
from anthology.library.schemas import LibraryTrackRow
from anthology.personal_data import playlists as service
from anthology.personal_data.models import (
    Favorite,
    FavoriteTarget,
    PlayHistory,
    Playlist,
    PlaylistEntry,
    PlaylistFolder,
    Visibility,
)
from anthology.personal_data.schemas import (
    FavoriteRow,
    PlaylistEntryRow,
    PlaylistFolderRow,
    PlaylistRow,
    PlayRow,
)
from anthology.personal_data.service import FAVORITE, PLAY, favorite_id
from anthology.playback.models import OutputZone
from anthology.sync.feed import ChangeEvent
from anthology.sync.streams import (
    KeyQuery,
    Meta,
    Row,
    RowChange,
    SortKey,
    StreamContext,
    StreamError,
)
from anthology.users.models import User
from anthology.users.service import SessionInfo


def _data(model) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude={"id", "key"})


def _row(model, key: SortKey) -> Row:
    return Row(id=model.id, key=key, data=_data(model))


def _upsert(row: Row) -> RowChange:
    return RowChange(op="upsert", id=row.id, key=row.key, row=row)


async def _page(db: AsyncSession, key_query: KeyQuery, after: SortKey | None, limit: int):
    query = key_query.query
    condition = key_query.after(after)
    if condition is not None:
        query = query.where(condition)
    return await db.execute(
        query.order_by(*key_query.ordering()).limit(limit).execution_options(populate_existing=True)
    )


async def _names(db: AsyncSession, ids) -> dict[uuid.UUID, str]:
    ids = {value for value in ids if value is not None}
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return dict(rows.all())


async def _tracks(db: AsyncSession, track_ids) -> dict[uuid.UUID, LibraryTrackRow]:
    ids = list(dict.fromkeys(track_ids))
    if not ids:
        return {}
    result = await db.execute(
        library.TRACK_ROW.where(Track.id.in_(ids)).execution_options(populate_existing=True)
    )
    return {
        row[0].id: LibraryTrackRow.model_validate(library.track_row(row, ()).payload())
        for row in result
    }


def _no_params(params: dict[str, Any]) -> dict[str, Any]:
    if params:
        raise StreamError("invalid_params", "this stream takes no parameters")
    return {}


# --- playlists --------------------------------------------------------------------------------


def _visible(user_id: uuid.UUID):
    return or_(Playlist.owner_id == user_id, Playlist.visibility == Visibility.SHARED)


class PlaylistsStream:
    name = "personal.playlists"
    entity_types = frozenset({service.PLAYLIST})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(Playlist).where(_visible(ctx.session.user_id)),
            columns=(Playlist.name, Playlist.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        mine = await db.scalar(
            select(func.count(Playlist.id)).where(Playlist.owner_id == ctx.session.user_id)
        )
        total = await db.scalar(
            select(func.count(Playlist.id)).where(_visible(ctx.session.user_id))
        )
        return Meta(total=total or 0, counters={"mine": mine or 0})

    async def _rows(self, db: AsyncSession, ctx: StreamContext, playlists) -> list[Row]:
        names = await _names(db, [playlist.owner_id for playlist in playlists])
        rows = []
        for playlist in playlists:
            mine = playlist.owner_id == ctx.session.user_id
            model = PlaylistRow(
                id=str(playlist.id),
                key=[playlist.name, str(playlist.id)],
                name=playlist.name,
                owner_id=str(playlist.owner_id),
                owner_name=names.get(playlist.owner_id, ""),
                visibility=playlist.visibility,
                folder_id=str(playlist.folder_id) if mine and playlist.folder_id else None,
                mine=mine,
                generation=str(playlist.generation),
                entry_count=playlist.entry_count,
                duration_ms=playlist.duration_ms,
                updated_at=playlist.updated_at,
            )
            rows.append(_row(model, (playlist.name, playlist.id)))
        return rows

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), _uuid_key(after), limit)
        return await self._rows(db, ctx, [playlist for (playlist,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        playlist = await db.get(Playlist, event.entity_id, populate_existing=True)
        if playlist is None or not service.visible(playlist, ctx.session.user_id):
            return [RowChange(op="remove", id=str(event.entity_id))]
        return [_upsert(row) for row in await self._rows(db, ctx, [playlist])]


def _uuid_key(after: SortKey | None) -> SortKey | None:
    """Keys travel as JSON: their last part (an ID) back to a UUID."""
    if after is None:
        return None
    *head, last = after
    return (*head, uuid.UUID(str(last)))


class FoldersStream:
    name = "personal.playlist_folders"
    entity_types = frozenset({service.FOLDER})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(PlaylistFolder).where(PlaylistFolder.user_id == ctx.session.user_id),
            columns=(PlaylistFolder.name, PlaylistFolder.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(
            select(func.count()).where(PlaylistFolder.user_id == ctx.session.user_id)
        )
        return Meta(total=total or 0)

    def _row(self, folder: PlaylistFolder) -> Row:
        model = PlaylistFolderRow(
            id=str(folder.id), key=[folder.name, str(folder.id)], name=folder.name
        )
        return _row(model, (folder.name, folder.id))

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), _uuid_key(after), limit)
        return [self._row(folder) for (folder,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        folder = await db.get(PlaylistFolder, event.entity_id, populate_existing=True)
        if folder is None or folder.user_id != ctx.session.user_id:
            return [RowChange(op="remove", id=str(event.entity_id))]
        return [_upsert(self._row(folder))]


# --- entries ----------------------------------------------------------------------------------


class EntriesStream:
    name = "personal.playlist.entries"
    entity_types = frozenset({service.ENTRY, service.PLAYLIST, "track"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if set(params) - {"playlist_id", "generation"} or "playlist_id" not in params:
            raise StreamError("invalid_params", "playlist_id (and generation) expected")
        try:
            playlist_id = str(uuid.UUID(str(params["playlist_id"])))
        except ValueError as error:
            raise StreamError("invalid_params", "playlist_id is not an ID") from error
        return {"playlist_id": playlist_id, "generation": str(params.get("generation", ""))}

    def _playlist_id(self, ctx: StreamContext) -> uuid.UUID:
        return uuid.UUID(ctx.params["playlist_id"])

    async def _visible(self, db: AsyncSession, ctx: StreamContext) -> Playlist | None:
        playlist = await db.get(Playlist, self._playlist_id(ctx), populate_existing=True)
        if playlist is None or not service.visible(playlist, ctx.session.user_id):
            return None
        return playlist

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        user_id = ctx.session.user_id
        visible = (
            select(Playlist.id)
            .where(Playlist.id == self._playlist_id(ctx), _visible(user_id))
            .scalar_subquery()
        )
        return KeyQuery(
            query=select(PlaylistEntry).where(PlaylistEntry.playlist_id == visible),
            columns=(PlaylistEntry.position_key, PlaylistEntry.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        playlist = await self._visible(db, ctx)
        if playlist is None:
            return Meta(total=0)
        return Meta(total=playlist.entry_count, counters={"duration_ms": playlist.duration_ms})

    async def _rows(self, db: AsyncSession, entries: list[PlaylistEntry]) -> list[Row]:
        tracks = await _tracks(db, [entry.track_id for entry in entries])
        names = await _names(db, [entry.added_by for entry in entries])
        rows = []
        for entry in entries:
            track = tracks.get(entry.track_id)
            if track is None:
                continue
            model = PlaylistEntryRow(
                id=str(entry.id),
                key=[entry.position_key, str(entry.id)],
                position_key=entry.position_key,
                track=track,
                added_by=str(entry.added_by) if entry.added_by else None,
                added_by_name=names.get(entry.added_by) if entry.added_by else None,
                added_at=entry.added_at,
            )
            rows.append(_row(model, (entry.position_key, entry.id)))
        return rows

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), _uuid_key(after), limit)
        return await self._rows(db, [entry for (entry,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        if event.entity_type == service.PLAYLIST:
            # Counts change with entries; access with the visibility.
            return []
        if await self._visible(db, ctx) is None:
            return (
                [RowChange(op="remove", id=str(event.entity_id))]
                if event.entity_type == service.ENTRY
                else []
            )
        base = select(PlaylistEntry).where(PlaylistEntry.playlist_id == self._playlist_id(ctx))
        if event.entity_type == "track":
            entries = list(
                await db.scalars(
                    base.where(PlaylistEntry.track_id == event.entity_id).execution_options(
                        populate_existing=True
                    )
                )
            )
            return [_upsert(row) for row in await self._rows(db, entries)]
        entry = await db.scalar(
            base.where(PlaylistEntry.id == event.entity_id).execution_options(
                populate_existing=True
            )
        )
        rows = await self._rows(db, [entry]) if entry is not None else []
        if not rows:
            return [RowChange(op="remove", id=str(event.entity_id))]
        return [_upsert(rows[0])]


# --- favorites and history --------------------------------------------------------------------

LABELS = {
    FavoriteTarget.RECORDING: (Recording, Recording.title),
    FavoriteTarget.RELEASE: (Release, Release.title),
    FavoriteTarget.ARTIST: (Artist, Artist.name),
}


class FavoritesStream:
    name = "personal.favorites"
    entity_types = frozenset({FAVORITE})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(Favorite).where(Favorite.user_id == ctx.session.user_id),
            columns=(Favorite.target_type, Favorite.target_id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        rows = await db.execute(
            select(Favorite.target_type, func.count())
            .where(Favorite.user_id == ctx.session.user_id)
            .group_by(Favorite.target_type)
        )
        counters = {target.value: count for target, count in rows}
        return Meta(total=sum(counters.values()), counters=counters)

    async def _rows(self, db: AsyncSession, favorites: list[Favorite]) -> list[Row]:
        labels: dict[uuid.UUID, str] = {}
        for target, (model, column) in LABELS.items():
            ids = [f.target_id for f in favorites if f.target_type == target]
            if ids:
                rows = await db.execute(select(model.id, column).where(model.id.in_(ids)))
                labels.update(dict(rows.all()))
        result = []
        for favorite in favorites:
            model = FavoriteRow(
                id=str(favorite_id(favorite.user_id, favorite.target_type, favorite.target_id)),
                key=[favorite.target_type.value, str(favorite.target_id)],
                target_type=favorite.target_type,
                target_id=str(favorite.target_id),
                label=labels.get(favorite.target_id, ""),
                created_at=favorite.created_at,
            )
            result.append(_row(model, (favorite.target_type.value, favorite.target_id)))
        return result

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), _uuid_key(after), limit)
        return await self._rows(db, [favorite for (favorite,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        # The change names the favorite by a derived ID: find it among the user's.
        for target in FavoriteTarget:
            favorites = list(
                await db.scalars(
                    select(Favorite).where(
                        Favorite.user_id == ctx.session.user_id, Favorite.target_type == target
                    )
                )
            )
            for favorite in favorites:
                if favorite_id(favorite.user_id, target, favorite.target_id) == event.entity_id:
                    return [_upsert(row) for row in await self._rows(db, [favorite])]
        return [RowChange(op="remove", id=str(event.entity_id))]


class HistoryStream:
    name = "personal.history"
    entity_types = frozenset({PLAY, "track"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(PlayHistory).where(
                PlayHistory.user_id == ctx.session.user_id, PlayHistory.track_id.is_not(None)
            ),
            columns=(PlayHistory.played_at, PlayHistory.id),
            descending=True,
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(
            select(func.count()).where(
                PlayHistory.user_id == ctx.session.user_id, PlayHistory.track_id.is_not(None)
            )
        )
        return Meta(total=total or 0)

    async def _rows(self, db: AsyncSession, plays: list[PlayHistory]) -> list[Row]:
        tracks = await _tracks(db, [play.track_id for play in plays])
        zone_ids = {play.output_zone_id for play in plays if play.output_zone_id}
        zones = {}
        if zone_ids:
            rows = await db.execute(
                select(OutputZone.id, OutputZone.name).where(OutputZone.id.in_(zone_ids))
            )
            zones = dict(rows.all())
        result = []
        for play in plays:
            track = tracks.get(play.track_id)
            if track is None:
                continue
            model = PlayRow(
                id=str(play.id),
                key=[play.played_at.isoformat(), play.id],
                played_at=play.played_at,
                track=track,
                zone=zones.get(play.output_zone_id) if play.output_zone_id else None,
            )
            result.append(_row(model, (play.played_at, play.id)))
        return result

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), after, limit)
        return await self._rows(db, [play for (play,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        base = select(PlayHistory).where(PlayHistory.user_id == ctx.session.user_id)
        if event.entity_type == "track":
            plays = list(await db.scalars(base.where(PlayHistory.track_id == event.entity_id)))
        else:
            plays = list(await db.scalars(base.where(PlayHistory.id == event.entity_id.int)))
        rows = await self._rows(db, plays)
        if not rows and event.entity_type == PLAY:
            return [RowChange(op="remove", id=str(event.entity_id.int))]
        return [_upsert(row) for row in rows]


STREAMS = (PlaylistsStream, FoldersStream, EntriesStream, FavoritesStream, HistoryStream)
