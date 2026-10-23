"""Quality ranking for replacements (spec: library-import, Quality comparison of duplicate
candidates)."""

import pytest

from anthology.library.models import QualityStatus, QualityTier
from anthology.quality_analysis.models import Confidence
from anthology.quality_analysis.ranking import Comparison, Quality, compare, effective_rank

GENUINE = QualityStatus.GENUINE
UPSCALED = QualityStatus.UPSCALED
HIGH, MEDIUM, LOW = Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW


def quality(tier, status=GENUINE, confidence=HIGH) -> Quality:
    return Quality(status, confidence, tier)


def test_ranks_order_the_tiers() -> None:
    tiers = [
        QualityTier.LOSSY_LOW,
        QualityTier.LOSSY_HIGH,
        QualityTier.CD_LOSSLESS,
        QualityTier.HIRES_LOSSLESS,
    ]
    assert [effective_rank(tier) for tier in tiers] == sorted(effective_rank(t) for t in tiers)


@pytest.mark.parametrize(
    ("new", "existing", "expected"),
    [
        # A genuine FLAC replaces an MP3.
        (quality(QualityTier.CD_LOSSLESS), quality(QualityTier.LOSSY_LOW), Comparison.BETTER),
        # Hi-res replaces CD quality.
        (quality(QualityTier.HIRES_LOSSLESS), quality(QualityTier.CD_LOSSLESS), Comparison.BETTER),
        # Equal ranks never replace (WAV and FLAC of equal resolution).
        (quality(QualityTier.CD_LOSSLESS), quality(QualityTier.CD_LOSSLESS), Comparison.NOT_BETTER),
        # Worse never replaces.
        (quality(QualityTier.LOSSY_HIGH), quality(QualityTier.CD_LOSSLESS), Comparison.NOT_BETTER),
        # An upscaled FLAC (lossy origin) is not better than a genuine AAC 256.
        (
            quality(QualityTier.LOSSY_LOW, UPSCALED),
            quality(QualityTier.LOSSY_HIGH),
            Comparison.NOT_BETTER,
        ),
        # A genuine CD rip replaces an existing upscaled "FLAC" of lossy origin.
        (
            quality(QualityTier.CD_LOSSLESS),
            quality(QualityTier.LOSSY_LOW, UPSCALED),
            Comparison.BETTER,
        ),
        # Anything not conclusive decides nothing.
        (
            quality(QualityTier.CD_LOSSLESS),
            quality(None, QualityStatus.SUSPICIOUS, MEDIUM),
            Comparison.INCONCLUSIVE,
        ),
        (
            quality(None, QualityStatus.SUSPICIOUS, LOW),
            quality(QualityTier.LOSSY_LOW),
            Comparison.INCONCLUSIVE,
        ),
        (quality(QualityTier.CD_LOSSLESS), None, Comparison.INCONCLUSIVE),
        (None, quality(QualityTier.LOSSY_LOW), Comparison.INCONCLUSIVE),
    ],
)
def test_compare(new, existing, expected) -> None:
    assert compare(new, existing) == expected
