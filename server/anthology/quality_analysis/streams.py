"""Stream of the quality analysis: one summary row with the files per status."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library import service as library
from anthology.library.models import QUALITY_COUNTERS
from anthology.quality_analysis.models import QualityAnalysis
from anthology.quality_analysis.schemas import QualitySummaryRow
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
from anthology.users.models import Role
from anthology.users.service import SessionInfo


async def _counts(db: AsyncSession) -> dict[str, int]:
    counts = await library.counters(db, tuple(QUALITY_COUNTERS.values()))
    return {
        (status.value if status is not None else "unanalysed"): counts[counter.value]
        for status, counter in QUALITY_COUNTERS.items()
    }


async def _row(db: AsyncSession) -> Row:
    summary_id = library.QUALITY_SUMMARY_ID
    model = QualitySummaryRow(id=str(summary_id), key=[str(summary_id)], **await _counts(db))
    return Row(
        id=model.id,
        key=(summary_id,),
        data=model.model_dump(mode="json", exclude={"id", "key"}),
    )


class QualitySummaryStream:
    """Live counts per quality status for editors and admins."""

    name = "quality_analysis.summary"
    entity_types = frozenset({library.QUALITY})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role in (Role.ADMIN, Role.EDITOR)

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        return Meta(total=1, counters=await _counts(db))

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        # A single row without a table of its own, like the identification summary.
        return KeyQuery(
            query=select(QualityAnalysis).where(
                QualityAnalysis.audio_hash == str(library.QUALITY_SUMMARY_ID)
            ),
            columns=(QualityAnalysis.audio_hash,),
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        if after is not None or limit < 1:
            return []
        return [await _row(db)]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        row = await _row(db)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


STREAMS = (QualitySummaryStream,)
