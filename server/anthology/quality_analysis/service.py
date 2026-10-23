"""The quality analysis job and its results (spec: quality-analysis, Analysis job; Stored
result; Efficient execution).

The job ``analyze_quality`` works through the audio hashes of active originals without a
result in batches of 100 (one job item each). Each hash is analysed once with one of its
files; the result is stored per hash and applied to every file with that audio through the
library service.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.library import service as library
from anthology.quality_analysis.analysis import (
    METHOD_VERSION,
    DecodeError,
    FileFacts,
    Result,
    analyze,
)
from anthology.quality_analysis.models import Confidence, QualityAnalysis

logger = logging.getLogger(__name__)

JOB_TYPE = "analyze_quality"
BATCH = 100


class AnalysisRunning(Exception):
    """A quality analysis job is already queued or running."""


def _analysed(full: bool):
    """Hashes that are done: any result, or (full re-run) a result of the current method."""
    query = select(QualityAnalysis.audio_hash)
    if full:
        query = query.where(QualityAnalysis.method_version >= METHOD_VERSION)
    return query


async def _batches(session: AsyncSession, full: bool) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    after: str | None = None
    while True:
        hashes = await library.audio_hashes(
            session, without=_analysed(full), after=after, limit=10_000
        )
        if not hashes:
            break
        for audio_hash in hashes:
            current.append(audio_hash)
            if len(current) == BATCH:
                batches.append([current[0], current[-1]])
                current = []
        after = hashes[-1]
    if current:
        batches.append([current[0], current[-1]])
    return batches


async def start(
    session: AsyncSession, *, created_by: uuid.UUID, full: bool = False
) -> uuid.UUID | None:
    """Create the analysis job (None if nothing is due)."""
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        raise AnalysisRunning()
    batches = await _batches(session, full)
    if not batches:
        return None
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title="Analyse quality",
        items=[
            f"Audio {index * BATCH + 1}-{index * BATCH + BATCH}" for index in range(len(batches))
        ],
        created_by=created_by,
        params={"full": full, "batches": batches},
        parallel_items=2,
    )
    return job.id


async def store(session: AsyncSession, audio_hash: str, result: Result) -> None:
    """Store the result for the hash and apply it to its files (spec: Stored result)."""
    analysis = await session.get(QualityAnalysis, audio_hash, with_for_update=True)
    if analysis is None:
        analysis = QualityAnalysis(audio_hash=audio_hash)
        session.add(analysis)
    analysis.status = result.status
    analysis.confidence = result.confidence
    analysis.finding = result.finding
    analysis.finding_values = json.dumps(result.values, sort_keys=True)
    analysis.effective_quality = result.effective_quality
    analysis.cutoff_hz = result.cutoff_hz
    analysis.effective_sample_rate_hz = result.effective_sample_rate_hz
    analysis.effective_bit_depth = result.effective_bit_depth
    analysis.estimated_bitrate_kbps = result.estimated_bitrate_kbps
    analysis.whole_file = result.whole_file
    analysis.method_version = METHOD_VERSION
    analysis.analyzed_at = utcnow()
    await session.flush()
    # Only a high-confidence result sets the effective quality.
    effective = result.effective_quality if result.confidence == Confidence.HIGH else None
    await library.apply_quality(session, audio_hash, result.status, effective)


@dataclass
class Analyzer:
    """Analyses one audio hash; bound to the handler when the app starts."""

    sessionmaker: async_sessionmaker
    settings: Settings

    async def analyse(self, audio_hash: str) -> str:
        """Analyse and store; returns the status, or why the hash could not be analysed."""
        async with self.sessionmaker() as session:
            original = await library.original_by_audio_hash(session, audio_hash)
            if original is None:
                return "no_original"
            recording = await library.get_recording(session, original.recording_id)
            facts = FileFacts(
                format=original.format,
                sample_rate_hz=original.sample_rate_hz,
                bit_depth=original.bit_depth,
                bitrate_kbps=original.bitrate_kbps,
                declared_quality=original.declared_quality,
                release_year=await library.release_year(session, original),
            )
            path, duration_s = original.path, recording.duration_ms / 1000
        if not await asyncio.to_thread(Path(path).is_file):
            return "file_missing"
        try:
            result = await analyze(path, facts, duration_s, ffmpeg=self.settings.ffmpeg_path)
        except DecodeError as error:
            logger.info("quality analysis of %s failed: %s", path, error)
            return error.reason
        async with self.sessionmaker() as session, session.begin():
            await store(session, audio_hash, result)
        return result.status.value


class AnalyzeQualityHandler:
    type = JOB_TYPE
    parallel_items = 2

    def __init__(self) -> None:
        self._analyzer: Analyzer | None = None

    def bind(self, analyzer: Analyzer) -> None:
        self._analyzer = analyzer

    @property
    def analyzer(self) -> Analyzer:
        if self._analyzer is None:
            raise RuntimeError("quality analysis handler is not bound")
        return self._analyzer

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        first, last = ctx.params["batches"][ctx.position]
        full = bool(ctx.params.get("full"))
        async with self.analyzer.sessionmaker() as session:
            hashes = await library.audio_hashes(
                session, without=_analysed(full), first=first, last=last, limit=BATCH * 2
            )
        counts: dict[str, int] = {}
        for index, audio_hash in enumerate(hashes):
            if await ctx.cancelled():
                return ItemResult(message="stopped", result=counts)
            # Analysed hashes are no longer due, so a repeated item skips them.
            outcome = await self.analyzer.analyse(audio_hash)
            counts[outcome] = counts.get(outcome, 0) + 1
            await ctx.report((index + 1) / len(hashes), f"{index + 1}/{len(hashes)}")
        return ItemResult(message=json.dumps(counts, sort_keys=True), result=counts)


# --- single files on acquisition (ADR 0022) -------------------------------------------------------


async def stored(session: AsyncSession, audio_hash: str) -> QualityAnalysis | None:
    return await session.get(QualityAnalysis, audio_hash)


async def analyse_file(
    path: str, facts: FileFacts, duration_s: float, *, ffmpeg: str
) -> Result | None:
    """Analyse a file that is not (yet) in the library; None if it cannot be decoded."""
    if not await asyncio.to_thread(Path(path).is_file):
        return None
    try:
        return await analyze(path, facts, duration_s, ffmpeg=ffmpeg)
    except DecodeError as error:
        logger.info("quality analysis of %s failed: %s", path, error)
        return None


async def apply_stored(session: AsyncSession, audio_hash: str) -> None:
    """Apply a result stored before the file entered the library (a duplicate candidate)."""
    analysis = await stored(session, audio_hash)
    if analysis is None:
        return
    effective = analysis.effective_quality if analysis.confidence == Confidence.HIGH else None
    await library.apply_quality(session, audio_hash, analysis.status, effective)
