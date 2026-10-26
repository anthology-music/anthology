"""The central review list (spec: review).

Producers create entries with ``propose``; the domain that owns an entry type registers a
``ReviewHandler`` that re-validates and applies decisions. The review module owns the entries,
their counters, suppression and decisions.
"""

import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import ColumnElement, and_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.changes import (
    ChangeOperation,
    ChangeScope,
    record_audit,
    record_change,
    record_changes,
)
from anthology.db.types import utcnow
from anthology.quality_analysis.models import Confidence
from anthology.review.models import (
    CONFIDENCE_RANK,
    SUPPRESSING_SQL,
    ReviewCounter,
    ReviewItem,
    ReviewOrigin,
    ReviewStatus,
    ReviewType,
)

# Change entries of the review list (stream review.items).
ITEM = "review_item"
INSERT_BATCH = 1_000


class Decision:
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"
    REOPEN = "reopen"

    ALL = (ACCEPT, REJECT, DEFER, REOPEN)


# The statuses a decision starts from.
DECIDABLE = {
    Decision.ACCEPT: (ReviewStatus.OPEN, ReviewStatus.DEFERRED),
    Decision.REJECT: (ReviewStatus.OPEN, ReviewStatus.DEFERRED),
    Decision.DEFER: (ReviewStatus.OPEN,),
    Decision.REOPEN: (ReviewStatus.DEFERRED,),
}


class ReviewError(Exception):
    code = "error"


class ItemNotFound(ReviewError):
    code = "not_found"


class NotDecidable(ReviewError):
    code = "not_decidable"


class HandlerMissing(ReviewError):
    code = "not_applicable_now"


class InvalidChoice(ReviewError):
    code = "invalid_choice"


class Obsolete(Exception):
    """Raised by a handler when the proposal no longer applies."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- producers --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Proposal:
    """One entry a producer wants to create."""

    type: ReviewType
    subject_type: str
    subject_id: str
    origin: ReviewOrigin
    confidence: Confidence
    proposal: dict[str, Any]
    summary: dict[str, Any]
    evidence: dict[str, Any] = field(default_factory=dict)
    # What makes two suggestions equal (default: subject and proposal).
    suppression: str | None = None
    # Group columns (``field``, ``release_id``, ``artist_id``, ``source``) of a tag conflict.
    groups: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        value = self.suppression or (
            f"{self.subject_type}:{self.subject_id}|{json.dumps(self.proposal, sort_keys=True)}"
        )
        return hashlib.sha256(f"{self.type.value}|{value}".encode()).hexdigest()


def _insert(session: AsyncSession):
    return pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert


async def propose(session: AsyncSession, proposals: Iterable[Proposal]) -> list[uuid.UUID]:
    """Create entries in one statement; entries whose suggestion is already open, deferred or
    rejected are skipped (spec: Rejected suggestions stay rejected). Returns the new IDs."""
    now = utcnow()
    rows = [
        {
            "id": uuid.uuid4(),
            "type": proposal.type,
            "subject_type": proposal.subject_type,
            "subject_id": proposal.subject_id,
            "origin": proposal.origin,
            "confidence": proposal.confidence,
            "confidence_rank": CONFIDENCE_RANK[proposal.confidence],
            "evidence_json": json.dumps(proposal.evidence, sort_keys=True),
            "proposal_json": json.dumps(proposal.proposal, sort_keys=True),
            "summary_json": json.dumps(proposal.summary, sort_keys=True),
            "suppression_key": proposal.key(),
            "status": ReviewStatus.OPEN,
            "created_at": now,
            "group_field": proposal.groups.get("field"),
            "group_release_id": proposal.groups.get("release_id"),
            "group_artist_id": proposal.groups.get("artist_id"),
            "group_source": proposal.groups.get("source"),
        }
        for proposal in proposals
    ]
    if not rows:
        return []
    # One entry per key within the batch as well.
    rows = list({row["suppression_key"]: row for row in rows}.values())
    insert = _insert(session)
    created = []
    # Statements stay below the parameter limit of PostgreSQL (32,767).
    for start in range(0, len(rows), INSERT_BATCH):
        statement = (
            insert(ReviewItem)
            .values(rows[start : start + INSERT_BATCH])
            .on_conflict_do_nothing(
                # The predicate of the partial unique index, literally (PostgreSQL matches it).
                index_elements=["suppression_key"],
                index_where=text(SUPPRESSING_SQL),
            )
            .returning(ReviewItem.id, ReviewItem.type, ReviewItem.origin, ReviewItem.confidence)
        )
        created.extend(await session.execute(statement))
    counts: dict[tuple, int] = {}
    for _id, type_, origin, confidence in created:
        key = (ReviewType(type_), ReviewOrigin(origin), Confidence(confidence), ReviewStatus.OPEN)
        counts[key] = counts.get(key, 0) + 1
    for key, count in counts.items():
        await _count(session, *key, count)
    ids = [row[0] for row in created]
    await record_changes(
        session,
        entity_type=ITEM,
        entity_ids=ids,
        operation=ChangeOperation.INSERT,
        scope=ChangeScope.SHARED,
    )
    return ids


async def _count(
    session: AsyncSession,
    type_: ReviewType,
    origin: ReviewOrigin,
    confidence: Confidence,
    status: ReviewStatus,
    delta: int,
) -> None:
    insert = _insert(session)
    await session.execute(
        insert(ReviewCounter)
        .values(type=type_, origin=origin, confidence=confidence, status=status, value=delta)
        .on_conflict_do_update(
            index_elements=["type", "origin", "confidence", "status"],
            set_={"value": ReviewCounter.value + delta},
        )
    )


async def counts(session: AsyncSession) -> list[ReviewCounter]:
    """All counter rows (at most one row per type, origin, confidence and status)."""
    return list(await session.scalars(select(ReviewCounter).where(ReviewCounter.value != 0)))


# --- handlers ---------------------------------------------------------------------------------


class ReviewHandler(Protocol):
    """Applies decisions of one review type; registered by the domain that owns the type."""

    type: ReviewType
    # Answers of an acceptance (e.g. "genuine", "upscaled"); empty: plain accept.
    choices: frozenset[str]

    def needs_job(self, decision: str) -> bool:
        """True if the decision touches files (then it runs as a job item)."""
        ...

    async def still_applies(self, session: AsyncSession, item: ReviewItem) -> str | None:
        """None, or the reason why the proposal no longer applies."""
        ...

    async def prepare(self, item: ReviewItem, decision: str, choice: str | None) -> Any:
        """File work outside the transaction (may raise ``Obsolete``); the result is passed
        to ``apply``."""
        ...

    async def apply(
        self,
        session: AsyncSession,
        item: ReviewItem,
        decision: str,
        choice: str | None,
        prepared: Any,
        user_id: uuid.UUID | None,
    ) -> None:
        """Apply an accept or reject in the decision's transaction, after ``still_applies``
        passed again; an exception rolls the whole decision back."""
        ...

    async def finished(self, item: ReviewItem, decision: str, prepared: Any) -> None:
        """Work after the commit (e.g. removing a moved source once the library refers to the
        new file)."""
        ...

    async def backfill(self, sessionmaker: async_sessionmaker, ctx: Any) -> int:
        """Create the entries of results stored before the review list existed; returns the
        number created. Runs once per installation (job ``review_backfill``)."""
        ...


class BaseHandler:
    """Defaults: no choices, no file work, rejecting changes nothing."""

    type: ReviewType
    choices: frozenset[str] = frozenset()

    def needs_job(self, decision: str) -> bool:
        return False

    async def still_applies(self, session: AsyncSession, item: ReviewItem) -> str | None:
        return None

    async def prepare(self, item: ReviewItem, decision: str, choice: str | None) -> Any:
        return None

    async def apply(self, session, item, decision, choice, prepared, user_id) -> None:
        return None

    async def finished(self, item: ReviewItem, decision: str, prepared: Any) -> None:
        return None

    async def backfill(self, sessionmaker: async_sessionmaker, ctx: Any) -> int:
        return 0


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[ReviewType, ReviewHandler] = {}

    def register(self, handler: ReviewHandler, *, replace: bool = False) -> None:
        if handler.type in self._handlers and not replace:
            raise ValueError(f"review type {handler.type!r} already registered")
        self._handlers[handler.type] = handler

    def get(self, type_: ReviewType) -> ReviewHandler | None:
        return self._handlers.get(type_)

    def remove(self, type_: ReviewType) -> None:
        self._handlers.pop(type_, None)

    def types(self) -> frozenset[ReviewType]:
        return frozenset(self._handlers)


# --- decisions --------------------------------------------------------------------------------


def evidence(item: ReviewItem) -> dict[str, Any]:
    return json.loads(item.evidence_json)


def proposal(item: ReviewItem) -> dict[str, Any]:
    return json.loads(item.proposal_json)


def summary(item: ReviewItem) -> dict[str, Any]:
    return json.loads(item.summary_json)


async def set_status(
    session: AsyncSession,
    item: ReviewItem,
    status: ReviewStatus,
    *,
    user_id: uuid.UUID | None,
    note: str | None = None,
) -> None:
    """Record a decision (or an obsolete entry) with user and time, counters and change."""
    previous = item.status
    item.status = status
    item.note = note
    if status == ReviewStatus.OPEN:
        item.decided_by = item.decided_at = None
    else:
        item.decided_by = user_id
        item.decided_at = utcnow()
    await session.flush()
    await _count(session, item.type, item.origin, item.confidence, previous, -1)
    await _count(session, item.type, item.origin, item.confidence, status, +1)
    await record_change(
        session,
        entity_type=ITEM,
        entity_id=item.id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )
    await record_audit(
        session,
        entity_type=ITEM,
        entity_id=item.id,
        action=f"review_{status.value}",
        user_id=user_id,
        diff={"status": [previous.value, status.value], "note": note},
    )


def _check(item: ReviewItem | None, decision: str) -> ReviewItem:
    if item is None:
        raise ItemNotFound()
    if item.status not in DECIDABLE[decision]:
        raise NotDecidable()
    return item


@dataclass
class Reviewer:
    """Decides entries; bound to the app's handler registry."""

    sessionmaker: async_sessionmaker
    handlers: HandlerRegistry

    def handler(self, item: ReviewItem) -> ReviewHandler | None:
        return self.handlers.get(item.type)

    def check(self, item: ReviewItem, decision: str, choice: str | None) -> None:
        """Refuse a decision that cannot be made (before a job is created for it)."""
        if decision != Decision.ACCEPT:
            return
        handler = self.handler(item)
        if handler is None:
            raise HandlerMissing()
        if handler.choices and choice not in handler.choices:
            raise InvalidChoice()
        if not handler.choices and choice is not None:
            raise InvalidChoice()

    def needs_job(self, item: ReviewItem, decision: str) -> bool:
        handler = self.handler(item)
        return handler is not None and handler.needs_job(decision)

    async def decide(
        self,
        item_id: uuid.UUID,
        decision: str,
        *,
        choice: str | None = None,
        user_id: uuid.UUID | None,
    ) -> ReviewStatus:
        """Decide one entry; returns its new status. Accepting re-validates the proposal first
        and closes the entry as obsolete when it no longer applies (spec: Stale entries)."""
        async with self.sessionmaker() as session, session.begin():
            item = _check(await session.get(ReviewItem, item_id, with_for_update=True), decision)
            self.check(item, decision, choice)
            if decision == Decision.DEFER:
                await set_status(session, item, ReviewStatus.DEFERRED, user_id=user_id)
                return item.status
            if decision == Decision.REOPEN:
                await set_status(session, item, ReviewStatus.OPEN, user_id=user_id)
                return item.status
            handler = self.handler(item)
            if handler is None:
                # Rejecting needs no handler: nothing is applied.
                await set_status(session, item, ReviewStatus.REJECTED, user_id=user_id)
                return item.status
            reason = await handler.still_applies(session, item)
            if reason is not None:
                await set_status(session, item, ReviewStatus.OBSOLETE, user_id=user_id, note=reason)
                return item.status
            session.expunge(item)

        try:
            prepared = await handler.prepare(item, decision, choice)
        except Obsolete as error:
            return await self._obsolete(item_id, error.reason, user_id)

        async with self.sessionmaker() as session, session.begin():
            item = _check(await session.get(ReviewItem, item_id, with_for_update=True), decision)
            # Checked again: the subject may have changed during the file work.
            reason = await handler.still_applies(session, item)
            if reason is not None:
                await set_status(session, item, ReviewStatus.OBSOLETE, user_id=user_id, note=reason)
                return item.status
            await handler.apply(session, item, decision, choice, prepared, user_id)
            status = ReviewStatus.ACCEPTED if decision == Decision.ACCEPT else ReviewStatus.REJECTED
            await set_status(session, item, status, user_id=user_id, note=choice)
        await handler.finished(item, decision, prepared)
        return status

    async def _obsolete(
        self, item_id: uuid.UUID, reason: str, user_id: uuid.UUID | None
    ) -> ReviewStatus:
        async with self.sessionmaker() as session, session.begin():
            item = await session.get_one(ReviewItem, item_id, with_for_update=True)
            if item.status in (ReviewStatus.OPEN, ReviewStatus.DEFERRED):
                await set_status(session, item, ReviewStatus.OBSOLETE, user_id=user_id, note=reason)
            return item.status


async def close_subject(
    session: AsyncSession,
    subject_type: str,
    subject_ids: Iterable[str],
    reason: str,
    *,
    except_id: uuid.UUID | None = None,
) -> int:
    """Close the open and deferred entries of removed subjects as obsolete (spec: Stale
    entries); ``except_id`` is the entry whose decision removed the subject."""
    ids = [str(subject_id) for subject_id in subject_ids]
    if not ids:
        return 0
    query = select(ReviewItem).where(
        ReviewItem.subject_type == subject_type,
        ReviewItem.subject_id.in_(ids),
        ReviewItem.status.in_((ReviewStatus.OPEN, ReviewStatus.DEFERRED)),
    )
    if except_id is not None:
        query = query.where(ReviewItem.id != except_id)
    items = list(await session.scalars(query.with_for_update()))
    for item in items:
        await set_status(session, item, ReviewStatus.OBSOLETE, user_id=None, note=reason)
    return len(items)


# --- filters ----------------------------------------------------------------------------------


# Types listed elsewhere: tag conflicts have their own list (spec: review, Central review list).
SEPARATE_TYPES = frozenset({ReviewType.TAG_CONFLICT})
GROUPS = ("field", "release_id", "artist_id", "source")


@dataclass(frozen=True)
class Filter:
    """A selection of the list: the subscription parameters and the rule of bulk decisions.
    Without a type, types with their own list are left out; the group filters apply to tag
    conflicts."""

    status: ReviewStatus = ReviewStatus.OPEN
    type: ReviewType | None = None
    origin: ReviewOrigin | None = None
    confidence: Confidence | None = None
    field: str | None = None
    release_id: uuid.UUID | None = None
    artist_id: uuid.UUID | None = None
    source: str | None = None

    def where(self) -> ColumnElement[bool]:
        conditions = [ReviewItem.status == self.status]
        if self.type is not None:
            conditions.append(ReviewItem.type == self.type)
        else:
            conditions.append(ReviewItem.type.not_in(SEPARATE_TYPES))
        if self.origin is not None:
            conditions.append(ReviewItem.origin == self.origin)
        if self.confidence is not None:
            conditions.append(ReviewItem.confidence == self.confidence)
        for name, column in self._groups():
            value = getattr(self, name)
            if value is not None:
                conditions.append(column == value)
        return and_(*conditions)

    @staticmethod
    def _groups():
        return (
            ("field", ReviewItem.group_field),
            ("release_id", ReviewItem.group_release_id),
            ("artist_id", ReviewItem.group_artist_id),
            ("source", ReviewItem.group_source),
        )

    def matches(self, item: ReviewItem) -> bool:
        type_matches = (
            item.type == self.type if self.type is not None else item.type not in SEPARATE_TYPES
        )
        return (
            item.status == self.status
            and type_matches
            and self.origin in (None, item.origin)
            and self.confidence in (None, item.confidence)
            and all(
                getattr(self, name) in (None, getattr(item, column.key))
                for name, column in self._groups()
            )
        )

    def params(self) -> dict[str, str | None]:
        return {
            "status": self.status.value,
            "type": self.type.value if self.type else None,
            "origin": self.origin.value if self.origin else None,
            "confidence": self.confidence.value if self.confidence else None,
            **{
                name: str(getattr(self, name)) if getattr(self, name) is not None else None
                for name in GROUPS
            },
        }

    @classmethod
    def of(cls, params: dict[str, Any]) -> "Filter":
        """Parse parameters; raises ValueError for unknown values."""
        unknown = set(params) - {"status", "type", "origin", "confidence", *GROUPS}
        if unknown:
            raise ValueError(f"unknown parameters: {sorted(unknown)}")

        def value(name: str, kind):
            raw = params.get(name)
            return kind(raw) if raw is not None else None

        return cls(
            status=value("status", ReviewStatus) or ReviewStatus.OPEN,
            type=value("type", ReviewType),
            origin=value("origin", ReviewOrigin),
            confidence=value("confidence", Confidence),
            field=value("field", str),
            release_id=value("release_id", lambda raw: uuid.UUID(str(raw))),
            artist_id=value("artist_id", lambda raw: uuid.UUID(str(raw))),
            source=value("source", str),
        )


def filter_counts(rows: Iterable[ReviewCounter], selection: Filter) -> tuple[int, dict[str, int]]:
    """Total of the selection, and counts per status (other filters applied) and per type
    (other filters applied) for the filter bar; types with their own list are left out."""
    total = 0
    by: dict[str, int] = {}
    for row in rows:
        if row.type in SEPARATE_TYPES and selection.type != row.type:
            continue
        same_type = selection.type in (None, row.type)
        same_origin = selection.origin in (None, row.origin)
        same_confidence = selection.confidence in (None, row.confidence)
        if same_type and same_origin and same_confidence:
            name = f"status.{row.status.value}"
            by[name] = by.get(name, 0) + row.value
            if row.status == selection.status:
                total += row.value
        if row.status == selection.status and same_origin and same_confidence:
            name = f"type.{row.type.value}"
            by[name] = by.get(name, 0) + row.value
    return total, by


async def keyset_batches(
    sessionmaker: async_sessionmaker, column, conditions: list, size: int = 500
) -> AsyncIterator[list[Any]]:
    """Values of ``column`` matching ``conditions`` in batches, in ascending order (keyset);
    each batch is read in its own session."""
    after = None
    while True:
        query = select(column).where(*conditions).order_by(column).limit(size)
        if after is not None:
            query = query.where(column > after)
        async with sessionmaker() as session:
            values = list(await session.scalars(query))
        if not values:
            return
        yield values
        after = values[-1]
