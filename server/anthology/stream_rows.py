"""Registry of typed stream rows, published with the sync message schema.

Add the row schema of every stream that has one here; client types are generated from it.
"""

from pydantic import BaseModel

from anthology.library.schemas import LibraryArtistRow, LibraryReleaseRow, LibraryTrackRow

ROW_SCHEMAS: dict[str, type[BaseModel]] = {
    "library.artists": LibraryArtistRow,
    "library.releases": LibraryReleaseRow,
    "library.artist.releases": LibraryReleaseRow,
    "library.release.tracks": LibraryTrackRow,
    "library.tracks": LibraryTrackRow,
}
