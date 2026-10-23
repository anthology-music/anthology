"""Comparing the effective quality of two files (spec: library, Quality-based replacement;
library-import, Quality comparison of duplicate candidates)."""

import enum
from dataclasses import dataclass

from anthology.library.models import QualityStatus, QualityTier
from anthology.quality_analysis.models import Confidence, QualityAnalysis

RANK = {
    QualityTier.HIRES_LOSSLESS: 4,
    QualityTier.CD_LOSSLESS: 3,
    QualityTier.LOSSY_HIGH: 2,
    QualityTier.LOSSY_LOW: 1,
}


class Comparison(enum.StrEnum):
    BETTER = "better"
    NOT_BETTER = "not_better"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Quality:
    status: QualityStatus
    confidence: Confidence
    tier: QualityTier | None

    @staticmethod
    def of(analysis: QualityAnalysis) -> "Quality":
        if analysis.decided_status is not None:
            # A human decision from the review list counts as conclusive.
            return Quality(analysis.decided_status, Confidence.HIGH, analysis.decided_quality)
        return Quality(analysis.status, analysis.confidence, analysis.effective_quality)

    @property
    def conclusive(self) -> bool:
        return self.confidence == Confidence.HIGH and self.tier is not None


def effective_rank(tier: QualityTier) -> int:
    return RANK[tier]


def compare(new: Quality | None, existing: Quality | None) -> Comparison:
    """Whether ``new`` is better than ``existing``.

    Only two conclusive results decide; a missing or inconclusive result never replaces
    anything. Equal ranks are not better (WAV and FLAC of equal resolution are equal).
    """
    if new is None or existing is None or not new.conclusive or not existing.conclusive:
        return Comparison.INCONCLUSIVE
    if effective_rank(new.tier) > effective_rank(existing.tier):
        return Comparison.BETTER
    return Comparison.NOT_BETTER
