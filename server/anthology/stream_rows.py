"""Registry of typed stream rows, published with the sync message schema.

Add the row schema of every stream that has one here; client types are generated from it.
"""

from pydantic import BaseModel

from anthology.library.schemas import (
    LibraryArtistRow,
    LibraryIdentificationRow,
    LibraryReleaseRow,
    LibraryStorageRow,
    LibrarySupersededRow,
    LibraryTrackRow,
)
from anthology.library_import.schemas import LibraryImportRow
from anthology.quality_analysis.schemas import QualitySummaryRow

ROW_SCHEMAS: dict[str, type[BaseModel]] = {
    "library.artists": LibraryArtistRow,
    "library.artist": LibraryArtistRow,
    "library.releases": LibraryReleaseRow,
    "library.release": LibraryReleaseRow,
    "library.artist.releases": LibraryReleaseRow,
    "library.release.tracks": LibraryTrackRow,
    "library.tracks": LibraryTrackRow,
    "library.superseded": LibrarySupersededRow,
    "library.identification": LibraryIdentificationRow,
    "library.storage": LibraryStorageRow,
    "library_import.imports": LibraryImportRow,
    "quality_analysis.summary": QualitySummaryRow,
}
