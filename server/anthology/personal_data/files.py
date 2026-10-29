"""Playlist files (spec: personal-data, Playlist import and export): M3U8 export, and import of
M3U, M3U8, PLS and XSPF. Entries are matched by the original's path, else by artist and title
(folded like the search, within two seconds when the file gives a duration)."""

import re
import uuid
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library.models import AudioFile, OriginalStatus, Recording, Track
from anthology.personal_data.models import Playlist, PlaylistEntry
from anthology.search.normalize import fold

DURATION_SLACK_MS = 2_000
EXTINF = re.compile(r"^#EXTINF:(-?\d+)[^,]*,(.*)$")
PLS_ENTRY = re.compile(r"^(File|Title|Length)(\d+)=(.*)$", re.IGNORECASE)


class InvalidFile(ValueError):
    pass


@dataclass
class Item:
    path: str | None = None
    artist: str | None = None
    title: str | None = None
    duration_ms: int | None = None

    def label(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        return self.title or self.path or "?"


# --- export -----------------------------------------------------------------------------------


async def export_m3u8(session: AsyncSession, playlist: Playlist) -> str:
    """The playlist as M3U8: duration, artist and title of the context, the original's path."""
    rows = await session.execute(
        select(
            Track.context_title,
            Track.context_artist,
            Recording.title,
            Recording.artist_display,
            Recording.duration_ms,
            AudioFile.path,
        )
        .select_from(PlaylistEntry)
        .join(Track, Track.id == PlaylistEntry.track_id)
        .join(Recording, Recording.id == Track.recording_id)
        .outerjoin(
            AudioFile,
            (AudioFile.recording_id == Recording.id)
            & (AudioFile.original_status == OriginalStatus.ACTIVE),
        )
        .where(PlaylistEntry.playlist_id == playlist.id)
        .order_by(PlaylistEntry.position_key, PlaylistEntry.id)
    )
    lines = ["#EXTM3U", f"#PLAYLIST:{playlist.name}"]
    for context_title, context_artist, title, artist, duration_ms, path in rows:
        name = f"{context_artist or artist} - {context_title or title}"
        lines.append(f"#EXTINF:{round((duration_ms or 0) / 1000)},{name}")
        lines.append(path or "")
    return "\n".join(lines) + "\n"


# --- import -----------------------------------------------------------------------------------


def parse(data: bytes) -> list[Item]:
    """The entries of a playlist file; the format is recognised by its content."""
    text = data.decode("utf-8-sig", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("<"):
        return _xspf(stripped)
    if stripped[:10].lower() == "[playlist]":
        return _pls(stripped)
    return _m3u(stripped)


def _split(name: str) -> tuple[str | None, str]:
    artist, separator, title = name.partition(" - ")
    return (artist.strip(), title.strip()) if separator else (None, name.strip())


def _m3u(text: str) -> list[Item]:
    items = []
    pending: Item | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = EXTINF.match(line)
        if match:
            artist, title = _split(match.group(2))
            seconds = int(match.group(1))
            pending = Item(
                artist=artist, title=title, duration_ms=seconds * 1000 if seconds > 0 else None
            )
            continue
        if line.startswith("#"):
            continue
        item = pending or Item()
        item.path = _path(line)
        items.append(item)
        pending = None
    return items


def _pls(text: str) -> list[Item]:
    entries: dict[int, Item] = {}
    for raw in text.splitlines():
        match = PLS_ENTRY.match(raw.strip())
        if not match:
            continue
        field, number, value = match.group(1).lower(), int(match.group(2)), match.group(3).strip()
        item = entries.setdefault(number, Item())
        if field == "file":
            item.path = _path(value)
        elif field == "title":
            item.artist, item.title = _split(value)
        elif value.lstrip("-").isdigit() and int(value) > 0:
            item.duration_ms = int(value) * 1000
    return [entries[number] for number in sorted(entries)]


def _xspf(text: str) -> list[Item]:
    try:
        # A file the user uploads: expat resolves no external entities and limits expansion.
        root = ElementTree.fromstring(text)  # noqa: S314
    except ElementTree.ParseError as error:
        raise InvalidFile(f"not a playlist: {error}") from error
    items = []
    for track in root.iter():
        if not track.tag.endswith("}track") and track.tag != "track":
            continue
        values = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in track}
        duration = values.get("duration", "")
        items.append(
            Item(
                path=_path(values["location"]) if values.get("location") else None,
                artist=values.get("creator") or None,
                title=values.get("title") or None,
                duration_ms=int(duration) if duration.isdigit() else None,
            )
        )
    return items


def _path(value: str) -> str:
    """A file path from a path or a ``file://`` URL."""
    if value.lower().startswith("file://"):
        return unquote(urlsplit(value).path)
    return value


async def match(session: AsyncSession, items: list[Item]) -> tuple[list[uuid.UUID], list[str]]:
    """Track IDs of the matched entries in order, and the labels of the unmatched ones."""
    tracks: list[uuid.UUID] = []
    unmatched: list[str] = []
    for item in items:
        track_id = await _by_path(session, item.path) if item.path else None
        if track_id is None and item.title:
            track_id = await _by_name(session, item)
        if track_id is None:
            unmatched.append(item.label())
        else:
            tracks.append(track_id)
    return tracks, unmatched


async def _by_path(session: AsyncSession, path: str) -> uuid.UUID | None:
    row = (
        await session.execute(
            select(AudioFile.home_track_id, AudioFile.recording_id).where(
                AudioFile.path == path, AudioFile.original_status == OriginalStatus.ACTIVE
            )
        )
    ).first()
    if row is None:
        return None
    if row.home_track_id is not None:
        return row.home_track_id
    return await session.scalar(
        select(Track.id).where(Track.recording_id == row.recording_id).order_by(Track.id).limit(1)
    )


async def _by_name(session: AsyncSession, item: Item) -> uuid.UUID | None:
    title = fold(item.title or "")
    artist = fold(item.artist or "")
    candidates = await session.execute(
        select(Track.id, Recording.title, Recording.artist_display, Recording.duration_ms)
        .join(Recording, Recording.id == Track.recording_id)
        .where(func.lower(Recording.title) == (item.title or "").lower())
        .order_by(Track.id)
        .limit(50)
    )
    for track_id, candidate_title, candidate_artist, duration_ms in candidates:
        if fold(candidate_title) != title:
            continue
        if artist and fold(candidate_artist) != artist:
            continue
        if item.duration_ms and abs(duration_ms - item.duration_ms) > DURATION_SLACK_MS:
            continue
        return track_id
    return None
