"""Generated tag conflicts for developer installations and end-to-end tests (there the server
never reaches MusicBrainz): MusicBrainz-sourced titles for the recordings of the first albums."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.db import create_sessionmaker
from anthology.library.models import Release, Track
from anthology.tagging import service
from anthology.tagging.fields import Level
from anthology.tagging.models import ProvenanceSource


async def seed_conflicts(engine: AsyncEngine, releases: int = 3) -> int:
    """Propose " (Remaster)" titles from the source MusicBrainz for every recording of the
    first ``releases`` albums in list order; returns the number of conflicts."""
    sessionmaker = create_sessionmaker(engine)
    created = 0
    async with sessionmaker() as session, session.begin():
        release_ids = list(
            await session.scalars(
                select(Release.id)
                .order_by(Release.sort_album_artist, Release.sort_title, Release.id)
                .limit(releases)
            )
        )
        for release_id in release_ids:
            for track in await session.scalars(
                select(Track).where(Track.release_id == release_id).order_by(Track.track_number)
            ):
                recording = await session.get_one(
                    service.MODELS[Level.RECORDING], track.recording_id
                )
                outcome = await service.apply(
                    session,
                    [
                        service.Edit(
                            Level.RECORDING,
                            recording.id,
                            {"title": f"{recording.title} (Remaster)"},
                        )
                    ],
                    user_id=None,
                    source=ProvenanceSource.MUSICBRAINZ,
                )
                created += outcome.conflicts
    return created
