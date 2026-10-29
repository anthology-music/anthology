"""Fetching covers (spec: covers, Cover sources and priority, Covers for the existing library):
the job ``covers_fetch`` has one item per release. An item reads the images embedded in the
release's originals through the tagger and asks the Cover Art Archive; the covers go through
``covers.service.set_cover``, so ranks, protection and conflicts apply. Items are idempotent:
equal images are stored once and an equal cover changes nothing.
"""

import asyncio
import logging
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.blobs import FileBlobStore
from anthology.core.config import Settings
from anthology.covers import service
from anthology.covers.models import ImageKind, ReleaseImage
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.jobs.models import Job
from anthology.library.models import AudioFile, OriginalStatus, Release, Track
from anthology.library_import import service as imports
from anthology.library_import.models import ImportItem, ImportStatus
from anthology.metadata_lookup.service import LookupFailed, LookupService, Priority
from anthology.tagging.fields import Level
from anthology.tagging.models import FieldProvenance, ProvenanceSource
from anthology.tagging.tagger_client import TaggerClient, TaggerIncompatible, TaggerUnavailable
from anthology.users import service as users

logger = logging.getLogger(__name__)

JOB_TYPE = "covers_fetch"
# Releases per job item.
BATCH = 20
ARCHIVE_KINDS = {
    "Back": ImageKind.BACK,
    "Booklet": ImageKind.BOOKLET,
    "Medium": ImageKind.DISC,
    "Tray": ImageKind.OTHER,
    "Obi": ImageKind.OTHER,
    "Spine": ImageKind.OTHER,
    "Liner": ImageKind.BOOKLET,
    "Sticker": ImageKind.OTHER,
}


async def start(
    session: AsyncSession,
    release_ids: list[uuid.UUID],
    *,
    created_by: uuid.UUID | None,
    title: str = "Fetch covers",
) -> uuid.UUID | None:
    """A job fetching the covers of ``release_ids`` (in batches); None if there are none."""
    ids = [str(release_id) for release_id in dict.fromkeys(release_ids)]
    if not ids:
        return None
    if created_by is None:
        # Automatic jobs belong to the earliest active admin (like the review backfill).
        created_by = await users.active_admin(session, None)
        if created_by is None:
            return None
    batches = [ids[index : index + BATCH] for index in range(0, len(ids), BATCH)]
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title=title,
        items=[f"{index + 1}/{len(batches)}" for index in range(len(batches))],
        created_by=created_by,
        params={"batches": batches},
    )
    return job.id


async def ensure_backfill(session: AsyncSession) -> uuid.UUID | None:
    """Once per installation: a job over every release (spec: Covers for the existing
    library). A library without releases needs none."""
    if await session.scalar(select(Job.id).where(Job.type == JOB_TYPE).limit(1)) is not None:
        return None
    release_ids = list(await session.scalars(select(Release.id).order_by(Release.id)))
    if not release_ids:
        return None
    return await start(session, release_ids, created_by=None, title="Fetch covers of the library")


async def fetch_uncovered(sessionmaker: async_sessionmaker) -> uuid.UUID | None:
    """When the tagger is available again: fetch the releases that have no cover and no
    decision about one (embedded images matter only for them, as the lowest source)."""
    async with sessionmaker() as session, session.begin():
        if await jobs.has_unfinished_job(session, JOB_TYPE):
            return None
        decided = select(FieldProvenance.entity_id).where(
            FieldProvenance.entity_type == Level.RELEASE.value, FieldProvenance.field == "cover"
        )
        release_ids = list(
            await session.scalars(
                select(Release.id)
                .where(Release.front_image_id.is_(None), Release.id.not_in(decided))
                .order_by(Release.id)
            )
        )
        return await start(session, release_ids, created_by=None, title="Fetch missing covers")


class Fetcher:
    """Fetches the covers of one release; bound to the handler when the app starts."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        settings: Settings,
        blobs: FileBlobStore,
        tagger: TaggerClient,
        lookups: LookupService,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.settings = settings
        self.blobs = blobs
        self.tagger = tagger
        self.lookups = lookups
        self.staging = settings.cache_dir / "staging" / "images"

    async def fetch(self, release_id: uuid.UUID) -> dict[str, Any]:
        result: dict[str, Any] = {}
        async with self.sessionmaker() as session:
            release = await session.get(Release, release_id)
            if release is None:
                return {"release": "gone"}
            mbid = release.mb_release_id
            originals = list(
                await session.execute(
                    select(AudioFile.path, AudioFile.source_id)
                    .join(Track, Track.recording_id == AudioFile.recording_id)
                    .where(
                        Track.release_id == release_id,
                        AudioFile.original_status == OriginalStatus.ACTIVE,
                    )
                )
            )
        if originals:
            result["embedded"] = await self._embedded(release_id, originals)
        if mbid is not None:
            result["archive"] = await self._archive(release_id, str(mbid))
        return result

    # --- embedded images ------------------------------------------------------------------

    async def _embedded(self, release_id, originals) -> str:
        paths = sorted({path for path, _source in originals})
        from_source = sum(1 for _path, source in originals if source is not None)
        await asyncio.to_thread(self.staging.mkdir, parents=True, exist_ok=True)
        try:
            results = await self.tagger.read(paths, extract_images_to=str(self.staging))
        except (TaggerUnavailable, TaggerIncompatible):
            # Read later: when the tagger is back, releases still without a cover are fetched
            # again (``fetch_uncovered``). Waiting here would hold a job slot.
            return "tagger_unavailable"
        fronts = Counter(
            image.sha256
            for result in results
            if result.ok
            for image in result.images
            if image.type == "front" and image.path
        )
        if not fronts:
            return "none"
        sha256 = fronts.most_common(1)[0][0]
        image_path = next(
            Path(image.path)
            for result in results
            if result.ok
            for image in result.images
            if image.sha256 == sha256 and image.path
        )
        # Files a source service delivered rank above other imports (spec: priority).
        source = (
            ProvenanceSource.SOURCE if from_source * 2 > len(originals) else ProvenanceSource.IMPORT
        )
        return await self._set(release_id, image_path, source, move=False)

    async def _set(self, release_id, path: Path, source: ProvenanceSource, *, move: bool) -> str:
        async with self.sessionmaker() as session, session.begin():
            try:
                image = await service.store(session, self.blobs, path, move=move)
            except service.InvalidImage as error:
                return f"invalid: {error}"
            outcome = await service.set_cover(
                session, Level.RELEASE, release_id, image.id, source=source
            )
        if outcome.conflicts:
            return "conflict"
        return "set" if outcome.changed else "unchanged"

    # --- Cover Art Archive ----------------------------------------------------------------

    async def _archive(self, release_id: uuid.UUID, mbid: str) -> str:
        coverart = self.lookups.coverart
        try:
            answer = await coverart.release(mbid, priority=Priority.BACKGROUND)
        except LookupFailed as error:
            logger.info("Cover Art Archive for %s failed: %s", mbid, error)
            return "failed"
        if not answer.found:
            return "none"
        images = (answer.data or {}).get("images") or []
        outcome = "no_front"
        for entry in images:
            url = _url(entry)
            if not url:
                continue
            if entry.get("front"):
                outcome = await self._archive_front(release_id, url)
                continue
            types = entry.get("types") or []
            kinds = [ARCHIVE_KINDS[kind] for kind in types if kind in ARCHIVE_KINDS]
            async with self.sessionmaker() as session, session.begin():
                await service.add_gallery_image(
                    session, release_id, kinds[0] if kinds else ImageKind.OTHER, remote_url=url
                )
        return outcome

    async def _archive_front(self, release_id: uuid.UUID, url: str) -> str:
        try:
            data = await self.lookups.coverart.image(url, max_bytes=service.MAX_BYTES)
        except LookupFailed as error:
            logger.info("cover %s failed: %s", url, error)
            return "failed"
        if data is None:
            return "none"
        path = self.staging / f"archive-{uuid.uuid4().hex}"
        await asyncio.to_thread(self.staging.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        try:
            return await self._set(release_id, path, ProvenanceSource.MUSICBRAINZ, move=True)
        finally:
            await asyncio.to_thread(path.unlink, missing_ok=True)

    async def download(self, entry_id: uuid.UUID) -> bool:
        """Download a gallery image that is only a Cover Art Archive URL yet."""
        async with self.sessionmaker() as session:
            entry = await session.get(ReleaseImage, entry_id)
            if entry is None or entry.image_id is not None or not entry.remote_url:
                return entry is not None and entry.image_id is not None
            url = entry.remote_url
        try:
            data = await self.lookups.coverart.image(
                url, max_bytes=service.MAX_BYTES, priority=Priority.INTERACTIVE
            )
        except LookupFailed:
            return False
        if data is None:
            return False
        path = self.staging / f"gallery-{uuid.uuid4().hex}"
        await asyncio.to_thread(self.staging.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        try:
            async with self.sessionmaker() as session, session.begin():
                try:
                    image = await service.store(session, self.blobs, path, move=True)
                except service.InvalidImage:
                    return False
                entry = await session.get(ReleaseImage, entry_id, with_for_update=True)
                if entry is None:
                    return False
                entry.image_id = image.id
                await service.gallery_changed(session, entry.release_id)
        finally:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        return True


def _url(entry: dict[str, Any]) -> str | None:
    """A size that is enough for every use (1200 pixels), else the original image."""
    thumbnails = entry.get("thumbnails") or {}
    return thumbnails.get("1200") or thumbnails.get("large") or entry.get("image")


class CoversFetchHandler:
    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._fetcher: Fetcher | None = None

    def bind(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        if self._fetcher is None:
            raise RuntimeError("covers handler is not bound")
        batch = ctx.params["batches"][ctx.position]
        counts: dict[str, int] = {}
        for index, release_id in enumerate(batch):
            if await ctx.cancelled():
                break
            outcome = await self._fetcher.fetch(uuid.UUID(release_id))
            for part, value in outcome.items():
                name = f"{part}:{value}"
                counts[name] = counts.get(name, 0) + 1
            await ctx.report((index + 1) / len(batch))
        return ItemResult(result=counts)


async def import_ended(session: AsyncSession, library_import) -> None:
    """After an import: fetch the covers of its releases (in the import's transaction)."""
    if library_import.status != ImportStatus.DONE:
        return
    release_ids = list(
        await session.scalars(
            select(ImportItem.release_id)
            .where(ImportItem.import_id == library_import.id, ImportItem.release_id.is_not(None))
            .distinct()
        )
    )
    await start(
        session,
        release_ids,
        created_by=library_import.created_by,
        title="Fetch covers of an import",
    )


imports.on_finished(import_ended)
