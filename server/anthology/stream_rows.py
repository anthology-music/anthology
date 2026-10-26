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
    MaintenanceFindingRow,
    MaintenanceRunRow,
)
from anthology.library_import.schemas import LibraryImportRow
from anthology.quality_analysis.schemas import QualitySummaryRow
from anthology.review import schemas as review
from anthology.review.schemas import ReviewItemRow
from anthology.tagging.edits import ChangeSetRow

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
    "library.maintenance": MaintenanceRunRow,
    "library.maintenance.findings": MaintenanceFindingRow,
    "library_import.imports": LibraryImportRow,
    "quality_analysis.summary": QualitySummaryRow,
    "review.items": ReviewItemRow,
    "tagging.changes": ChangeSetRow,
    "tagging.conflicts": ReviewItemRow,
}

# Typed content of row fields that differ per row kind (the evidence and proposal of each
# review entry type); clients read them by the row's type.
PART_SCHEMAS: dict[str, type[BaseModel]] = {
    "review.recording_match.evidence": review.RecordingMatchEvidence,
    "review.recording_match.proposal": review.RecordingMatchProposal,
    "review.musicbrainz_suggestion.evidence": review.MusicBrainzSuggestionEvidence,
    "review.musicbrainz_suggestion.proposal": review.MusicBrainzSuggestionProposal,
    "review.import_title.evidence": review.ImportTitleEvidence,
    "review.import_replacement.evidence": review.ImportReplacementEvidence,
    "review.import.proposal": review.ImportProposal,
    "review.quality_finding.evidence": review.QualityFindingEvidence,
    "review.quality_finding.proposal": review.QualityFindingProposal,
    "review.tag_conflict.evidence": review.TagConflictEvidence,
    "review.tag_conflict.proposal": review.TagConflictProposal,
}
