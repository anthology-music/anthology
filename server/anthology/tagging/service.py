"""Editing metadata (spec: tagging): one edit path for single and bulk edits.

An edit names a level, an entity and fields. The service writes the values through the library
service (which keeps sort keys, counters and change entries), records the provenance of every
changed field and one audit row with old and new values per entity (grouped by the current
change set, so that the edit can be undone) and queues the files whose tags change.
"""

import json
import uuid
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.changes import current_change_set, record_audit
from anthology.covers.models import Image
from anthology.db.types import utcnow
from anthology.library import service as library
from anthology.library.models import (
    AudioFile,
    IdentificationStatus,
    OriginalStatus,
    Recording,
    Release,
    StorageMode,
    Track,
)
from anthology.tagging import conflicts, writes
from anthology.tagging.fields import BASE_FIELDS, InvalidFields, Level, plain, validate
from anthology.tagging.models import (
    PROTECTED,
    RANKED,
    RANKED_PROTECTED,
    ChangeSet,
    ChangeSetKind,
    FieldProvenance,
    ProvenanceSource,
)

EDIT = "tag_edit"


class EditError(Exception):
    code = "invalid"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)
        self.message = message or self.code


class NotFound(EditError):
    code = "not_found"


class DuplicateId(EditError):
    code = "duplicate_id"


@dataclass
class Edit:
    level: Level
    entity_id: uuid.UUID
    fields: dict[str, Any]


@dataclass
class Outcome:
    changed: int = 0
    files: set[uuid.UUID] = field(default_factory=set)
    # Tag conflicts created for protected fields (automatic sources).
    conflicts: int = 0


# Fields that no file carries.
FILELESS = frozenset({"cover"})
# Edits by people: never conflicts (an accepted conflict counts as set by the accepting user).
MANUAL_SOURCES = frozenset({ProvenanceSource.MANUAL, ProvenanceSource.REVIEW})


def _empty(value: Any) -> bool:
    return value is None or value == [] or value == ""


async def _protected(
    session: AsyncSession, level: Level, entity_id: uuid.UUID, changes: dict[str, list[Any]]
) -> list[str]:
    """Fields an automatic source must not overwrite: set manually, imported or by a
    decision; a value without a provenance record was imported (spec: Field provenance)."""
    rows = await provenance(session, level, entity_id)
    protected = []
    for name, (old, _new) in changes.items():
        row = rows.get(name)
        if name in RANKED:
            if row is not None and row.source in RANKED_PROTECTED:
                protected.append(name)
        elif (row.source in PROTECTED) if row is not None else not _empty(old):
            protected.append(name)
    return protected


async def _outranked(
    session: AsyncSession,
    level: Level,
    entity_id: uuid.UUID,
    changes: dict[str, list[Any]],
    source: ProvenanceSource,
) -> list[str]:
    """Ranked fields whose current value comes from an automatic source of equal or higher
    rank than ``source``: the new value is ignored."""
    rows = await provenance(session, level, entity_id)
    ignored = []
    for name in changes.keys() & RANKED.keys():
        ranks = RANKED[name]
        row = rows.get(name)
        if row is not None and row.source in ranks and ranks[row.source] >= ranks.get(source, 0):
            ignored.append(name)
    return ignored


# --- change sets ------------------------------------------------------------------------------


async def create_change_set(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    summary: dict[str, Any],
    items: int,
    kind: ChangeSetKind = ChangeSetKind.EDIT,
    rule: dict[str, Any] | None = None,
    undo_of: uuid.UUID | None = None,
) -> ChangeSet:
    change_set = ChangeSet(
        id=uuid.uuid4(),
        kind=kind,
        user_id=user_id,
        summary_json=json.dumps(summary, sort_keys=True),
        rule_json=json.dumps(rule, sort_keys=True) if rule is not None else None,
        items=items,
        changed=0,
        created_at=utcnow(),
        undo_of=undo_of,
    )
    session.add(change_set)
    await session.flush()
    await writes.changed_set(session, change_set.id)
    return change_set


@asynccontextmanager
async def in_change_set(change_set_id: uuid.UUID) -> AsyncIterator[None]:
    """Audit rows written inside belong to the change set."""
    token = current_change_set.set(change_set_id)
    try:
        yield
    finally:
        current_change_set.reset(token)


async def count_changed(session: AsyncSession, change_set_id: uuid.UUID, changed: int) -> None:
    if not changed:
        return
    change_set = await session.get_one(ChangeSet, change_set_id, with_for_update=True)
    change_set.changed += changed
    await session.flush()
    await writes.changed_set(session, change_set_id)


# --- current values ---------------------------------------------------------------------------


async def current(session: AsyncSession, level: Level, entity: Any) -> dict[str, Any]:
    """The editable values of an entity, as the audit log stores them."""
    if level == Level.RECORDING:
        return {
            "title": entity.title,
            "artist": entity.artist_display,
            "isrc": entity.isrc,
            "mb_recording_id": plain(entity.mb_recording_id),
            "composers": list(entity.composers or []),
            "genres": list(entity.genres or []),
            "cover": plain(entity.front_image_id),
        }
    if level == Level.RELEASE:
        return {
            "title": entity.title,
            "album_artist": entity.album_artist_display,
            "year": entity.release_date.year if entity.release_date else None,
            "label": entity.label,
            "cover": plain(entity.front_image_id),
        }
    release = await session.get_one(Release, entity.release_id)
    return {
        "track_number": entity.track_number,
        "disc_number": entity.disc_number,
        "context_title": entity.context_title,
        "context_artist": entity.context_artist,
        "album": release.title,
        "album_artist": release.album_artist_display,
    }


MODELS = {Level.RECORDING: Recording, Level.RELEASE: Release, Level.TRACK: Track}


# --- applying edits ---------------------------------------------------------------------------


async def apply(
    session: AsyncSession,
    edits: Iterable[Edit],
    *,
    user_id: uuid.UUID | None,
    source: ProvenanceSource = ProvenanceSource.MANUAL,
) -> Outcome:
    """Apply validated edits in the caller's transaction; returns what changed. Files whose
    tags change are queued (written after the commit by the tag writer)."""
    outcome = Outcome()
    for edit in edits:
        values = validate(edit.level, edit.fields)
        entity = await session.get(MODELS[edit.level], edit.entity_id, with_for_update=True)
        if entity is None:
            raise NotFound(f"{edit.level} {edit.entity_id}")
        before = await current(session, edit.level, entity)
        changes = {
            name: [before[name], plain(value)]
            for name, value in values.items()
            if before[name] != plain(value)
        }
        if not changes:
            continue
        if source not in MANUAL_SOURCES:
            for name in await _outranked(session, edit.level, entity.id, changes, source):
                del changes[name]
            values = {name: value for name, value in values.items() if name in changes}
            if not changes:
                continue
            conflicting = await _protected(session, edit.level, entity.id, changes)
            if conflicting:
                outcome.conflicts += len(
                    await conflicts.propose(
                        session,
                        edit.level,
                        entity,
                        {name: changes.pop(name) for name in conflicting},
                        source,
                    )
                )
                values = {name: value for name, value in values.items() if name in changes}
            if not changes:
                continue
        await _write(session, edit.level, entity, values, changes, user_id=user_id)
        await _provenance(session, edit.level, entity.id, changes, source, user_id)
        await record_audit(
            session,
            entity_type=edit.level.value,
            entity_id=entity.id,
            action=EDIT,
            user_id=user_id,
            diff=changes,
        )
        outcome.changed += 1
        outcome.files |= await _files(session, edit.level, entity, changes)
    await writes.enqueue(session, outcome.files)
    return outcome


async def apply_to_tracks(
    session: AsyncSession,
    track_ids: list[uuid.UUID],
    fields: dict[Level, dict[str, Any]],
    *,
    user_id: uuid.UUID | None,
    source: ProvenanceSource = ProvenanceSource.MANUAL,
) -> Outcome:
    """Apply fields per level to tracks: the track fields first (moves included), then the
    recordings and the releases the tracks belong to afterwards."""
    total = Outcome()

    def add(outcome: Outcome) -> None:
        total.changed += outcome.changed
        total.files |= outcome.files
        total.conflicts += outcome.conflicts

    if fields.get(Level.TRACK):
        add(
            await apply(
                session,
                [Edit(Level.TRACK, track_id, fields[Level.TRACK]) for track_id in track_ids],
                user_id=user_id,
                source=source,
            )
        )
    for level, column in ((Level.RECORDING, Track.recording_id), (Level.RELEASE, Track.release_id)):
        if not fields.get(level):
            continue
        entity_ids = list(
            await session.scalars(
                select(column).where(Track.id.in_(track_ids)).distinct().order_by(column)
            )
        )
        add(
            await apply(
                session,
                [Edit(level, entity_id, fields[level]) for entity_id in entity_ids],
                user_id=user_id,
                source=source,
            )
        )
    return total


async def _write(
    session: AsyncSession,
    level: Level,
    entity: Any,
    values: dict[str, Any],
    changes: dict[str, list[Any]],
    *,
    user_id: uuid.UUID | None,
) -> None:
    if level == Level.RECORDING:
        await _write_recording(session, entity, values, changes, user_id)
    elif level == Level.RELEASE:
        await _write_release(session, entity, values, changes, user_id)
    else:
        await _write_track(session, entity, values, changes, user_id)


async def _write_recording(session, recording: Recording, values, changes, user_id) -> None:
    fields: dict[str, Any] = {
        name: values[name] for name in ("title", "isrc", "composers", "genres") if name in changes
    }
    if "cover" in changes:
        fields["front_image_id"] = await _image(session, values["cover"])
    if "artist" in changes:
        fields["artist"] = await library.get_or_create_artist(
            session, values["artist"], user_id=user_id
        )
        fields["artist_display"] = values["artist"]
    if fields:
        await library.update_recording(session, recording, user_id=user_id, **fields)
    if "mb_recording_id" in changes:
        mbid = values["mb_recording_id"]
        if mbid is not None:
            owner = await session.scalar(
                select(Recording.id).where(
                    Recording.mb_recording_id == mbid, Recording.id != recording.id
                )
            )
            if owner is not None:
                raise DuplicateId(str(mbid))
            await library.record_identification(
                session,
                recording,
                IdentificationStatus.CONFIRMED,
                checked_at=utcnow(),
                mb_recording_id=mbid,
                note="manual",
                user_id=user_id,
            )
        else:
            await library.clear_identification(session, recording, user_id=user_id)


async def _write_release(session, release: Release, values, changes, user_id) -> None:
    fields: dict[str, Any] = {}
    if "title" in changes:
        fields["title"] = values["title"]
    if "label" in changes:
        fields["label"] = values["label"]
    if "cover" in changes:
        fields["front_image_id"] = await _image(session, values["cover"])
    if "year" in changes:
        fields["release_date"] = _with_year(release.release_date, values["year"])
    if "album_artist" in changes:
        fields["album_artist"] = await library.get_or_create_artist(
            session, values["album_artist"], user_id=user_id
        )
        fields["album_artist_display"] = values["album_artist"]
    await library.update_release(session, release, user_id=user_id, **fields)


async def _image(session: AsyncSession, image_id: uuid.UUID | None) -> uuid.UUID | None:
    """A cover must be a stored image (spec: covers)."""
    if image_id is not None and await session.get(Image, image_id) is None:
        raise InvalidFields(f"unknown image {image_id}")
    return image_id


def _with_year(value: date | None, year: int | None) -> date | None:
    if year is None:
        return None
    if value is None:
        return date(year, 1, 1)
    # 29 February in a year without it becomes 28 February.
    day = min(value.day, 28) if value.month == 2 else value.day
    return value.replace(year=year, day=day)


async def _write_track(session, track: Track, values, changes, user_id) -> None:
    fields = {
        name: values[name]
        for name in ("track_number", "disc_number", "context_title", "context_artist")
        if name in changes
    }
    if fields:
        await library.update_track(session, track, user_id=user_id, **fields)
    if changes.keys() & {"album", "album_artist"}:
        old = await session.get_one(Release, track.release_id)
        title = values.get("album", old.title)
        artist_name = values.get("album_artist", old.album_artist_display)
        artist = await library.get_or_create_artist(session, artist_name, user_id=user_id)
        target = await library.find_or_create_release(
            session, title, artist, like=old, user_id=user_id
        )
        await library.move_track(session, track, target, user_id=user_id)


async def record_choice(
    session: AsyncSession,
    level: Level,
    entity_id: uuid.UUID,
    field: str,
    source: ProvenanceSource,
    user_id: uuid.UUID | None,
) -> None:
    """Record who decided a field without changing its value (e.g. "no cover" chosen for a
    release that has none, so that automatic sources leave it empty)."""
    await _provenance(session, level, entity_id, {field: [None, None]}, source, user_id)


async def _provenance(
    session: AsyncSession,
    level: Level,
    entity_id: uuid.UUID,
    changes: dict[str, list[Any]],
    source: ProvenanceSource,
    user_id: uuid.UUID | None,
) -> None:
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    now = utcnow()
    for name in changes:
        statement = insert(FieldProvenance).values(
            entity_type=level.value,
            entity_id=entity_id,
            field=name,
            source=source,
            set_by=user_id,
            set_at=now,
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["entity_type", "entity_id", "field"],
                set_={"source": source, "set_by": user_id, "set_at": now},
            )
        )


async def provenance(
    session: AsyncSession, level: Level, entity_id: uuid.UUID
) -> dict[str, FieldProvenance]:
    rows = await session.scalars(
        select(FieldProvenance).where(
            FieldProvenance.entity_type == level.value, FieldProvenance.entity_id == entity_id
        )
    )
    return {row.field: row for row in rows}


# --- files ------------------------------------------------------------------------------------


def _writable(audio_file: AudioFile) -> bool:
    return audio_file.original_status == OriginalStatus.ACTIVE and (
        audio_file.storage_mode == StorageMode.MANAGED or audio_file.tag_writes_allowed
    )


async def _files(
    session: AsyncSession, level: Level, entity: Any, changes: dict[str, list[Any]]
) -> set[uuid.UUID]:
    """Active originals whose tags change: managed ones for base fields of their recording,
    referenced ones with tag writing enabled for every field of their home context. Covers
    are never written into originals (spec: covers, Covers in files)."""
    if not changes.keys() - FILELESS:
        return set()
    if level == Level.RECORDING:
        original = await library.active_original(session, entity.id)
        if original is None or not _writable(original):
            return set()
        if original.storage_mode == StorageMode.MANAGED and not changes.keys() & BASE_FIELDS:
            return set()
        return {original.id}
    if level == Level.RELEASE:
        home = select(Track.id).where(Track.release_id == entity.id)
    else:
        home = select(Track.id).where(Track.id == entity.id)
    files = await session.scalars(
        select(AudioFile).where(
            AudioFile.home_track_id.in_(home),
            AudioFile.original_status == OriginalStatus.ACTIVE,
            AudioFile.storage_mode == StorageMode.REFERENCED,
            AudioFile.tag_writes_allowed.is_(True),
        )
    )
    return {audio_file.id for audio_file in files}
