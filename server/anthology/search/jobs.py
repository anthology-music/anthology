"""The job ``search_reindex``: rebuilds the search documents (design: Search documents).

Started at server start when the stored index version differs from ``index.VERSION``. One
item per item type; each rewrites its documents in batches, one transaction per batch, while
the library stays writable (edits rewrite their documents themselves).
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.library.models import Artist
from anthology.search import index
from anthology.search.models import SearchTerm
from anthology.users.service import active_admin

JOB_TYPE = "search_reindex"
BATCH = 1_000


async def start(session: AsyncSession, *, created_by: uuid.UUID) -> uuid.UUID:
    # The vocabulary is rebuilt with the documents.
    await session.execute(delete(SearchTerm))
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title="Rebuild the search index",
        items=list(index.ITEM_TYPES),
        created_by=created_by,
    )
    await session.run_sync(index.set_version)
    return job.id


async def ensure_index(session: AsyncSession) -> uuid.UUID | None:
    """Start the rebuild if the index version is outdated; returns the job ID if started."""
    if await session.run_sync(index.current_version) == index.VERSION:
        return None
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        return None
    admin = await active_admin(session, None)
    if admin is None or await session.scalar(select(func.count()).select_from(Artist)) == 0:
        # Nothing to index yet: new documents are written with every library write.
        await session.run_sync(index.set_version)
        return None
    return await start(session, created_by=admin)


class SearchReindexHandler:
    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._sessionmaker: async_sessionmaker | None = None

    def bind(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        if self._sessionmaker is None:
            raise RuntimeError("search reindex handler is not bound")
        item_type = index.ITEM_TYPES[ctx.position]
        async with self._sessionmaker() as session:
            total = await session.run_sync(index.item_count, item_type)
        done, after = 0, None
        while True:
            if await ctx.cancelled():
                return ItemResult(result={"documents": done})
            async with self._sessionmaker() as session, session.begin():
                after = await session.run_sync(index.rebuild_batch, item_type, after, BATCH)
            if after is None:
                break
            done += BATCH
            await ctx.report(min(done / max(total, 1), 1.0))
        if ctx.position == len(index.ITEM_TYPES) - 1:
            async with self._sessionmaker() as session, session.begin():
                await session.run_sync(index.remove_stale)
        return ItemResult(result={"documents": min(done, total)})
