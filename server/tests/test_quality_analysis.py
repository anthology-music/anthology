"""Measurements and classification of the quality analysis (spec: quality-analysis) on a
generated reference set: noise with band limits, lossy round trips, fake hi-res and padded
bit depth. No copyrighted audio."""

from pathlib import Path

import numpy as np
import pytest

from anthology.library.models import AudioFormat, QualityStatus, QualityTier
from anthology.quality_analysis.analysis import (
    WINDOW,
    BitDepthAccumulator,
    Cutoff,
    FileFacts,
    Measurements,
    SpectrumAccumulator,
    analyze,
    classify,
    find_cutoff,
    measure,
)
from anthology.quality_analysis.models import Confidence
from tests.media_helpers import require_ffmpeg
from tests.quality_helpers import flac, lossy_round_trip, noise

CD = FileFacts(AudioFormat.FLAC, 44_100, 16, None, QualityTier.CD_LOSSLESS)
HIRES = FileFacts(AudioFormat.FLAC, 96_000, 24, None, QualityTier.HIRES_LOSSLESS)
CD24 = FileFacts(AudioFormat.FLAC, 44_100, 24, None, QualityTier.HIRES_LOSSLESS)


def cutoff_of(samples: np.ndarray, rate: int = 44_100) -> Cutoff:
    spectrum = SpectrumAccumulator(rate)
    spectrum.add(samples.mean(axis=1))
    return find_cutoff(*spectrum.levels(), rate)


# --- measurements on samples ----------------------------------------------------------------------


def test_full_band_noise_has_no_cutoff() -> None:
    cutoff = cutoff_of(noise(seconds=5))
    assert cutoff.full_band and not cutoff.steep


def test_brick_wall_is_found_and_steep() -> None:
    cutoff = cutoff_of(noise(seconds=5, lowpass_hz=16_000))
    assert 15_800 <= cutoff.hz <= 16_200
    assert cutoff.steep


def test_gradual_roll_off_is_not_steep() -> None:
    cutoff = cutoff_of(noise(seconds=5, rolloff_hz=12_000))
    assert not cutoff.steep and not cutoff.full_band


def test_content_above_cd_bandwidth_of_hires() -> None:
    genuine = cutoff_of(noise(seconds=5, rate=96_000, lowpass_hz=40_000), 96_000)
    upsampled = cutoff_of(noise(seconds=5, rate=96_000, lowpass_hz=20_000), 96_000)
    assert genuine.hz > 39_000
    assert 19_800 <= upsampled.hz <= 20_400


def test_silent_windows_are_skipped() -> None:
    spectrum = SpectrumAccumulator(44_100)
    spectrum.add(np.zeros(WINDOW * 20, dtype=np.float32))
    assert spectrum.loud_windows == 0


def test_padded_bit_depth() -> None:
    samples = np.round(noise(seconds=2).reshape(-1) * 32767).astype(np.int64)
    padded, genuine = BitDepthAccumulator(), BitDepthAccumulator()
    padded.add((samples << 16).astype(np.int32))  # 16 bit in the upper bits of s32le
    genuine.add((np.round(noise(seconds=2, seed=3).reshape(-1) * 8_388_607).astype(np.int64)
                 << 8).astype(np.int32))  # fmt: skip
    assert (padded.effective_bits, genuine.effective_bits) == (16, 24)


# --- classification rules -------------------------------------------------------------------------


def measured(hz: float, *, steep: bool, full_band: bool = False, bits: int | None = None):
    return Measurements(loud_windows=100, cutoff=Cutoff(hz, steep, full_band), effective_bits=bits)


def test_lossy_origin_at_an_encoder_lowpass() -> None:
    result = classify(
        FileFacts(AudioFormat.FLAC, 44_100, 16, None, QualityTier.CD_LOSSLESS, 1998),
        measured(16_050, steep=True),
    )
    assert (result.status, result.confidence, result.finding) == (
        QualityStatus.UPSCALED,
        Confidence.HIGH,
        "lossy_origin",
    )
    assert result.values == {"cutoff_hz": 16_050, "bitrate_kbps": 128}
    assert result.effective_quality == QualityTier.LOSSY_LOW


def test_old_recording_with_little_treble_is_only_suspicious() -> None:
    old = FileFacts(AudioFormat.FLAC, 44_100, 16, None, QualityTier.CD_LOSSLESS, 1965)
    for steep in (True, False):
        result = classify(old, measured(15_000, steep=steep))
        assert (result.status, result.confidence, result.finding) == (
            QualityStatus.SUSPICIOUS,
            Confidence.LOW,
            "low_cutoff_old_recording",
        )
        assert result.effective_quality is None


def test_unknown_brick_wall_is_suspicious() -> None:
    result = classify(CD, measured(18_000, steep=True))
    assert (result.status, result.confidence) == (QualityStatus.SUSPICIOUS, Confidence.MEDIUM)
    assert result.effective_quality is None


def test_mastering_lowpass_is_never_upscaled() -> None:
    result = classify(CD, measured(20_000, steep=True))
    assert (result.status, result.confidence, result.finding) == (
        QualityStatus.GENUINE,
        Confidence.MEDIUM,
        "possible_lossy_origin",
    )


def test_lossy_file_far_below_its_bitrate() -> None:
    mp3 = FileFacts(AudioFormat.MP3, 44_100, None, 320, QualityTier.LOSSY_HIGH)
    reencoded = classify(mp3, measured(16_000, steep=True))
    genuine = classify(mp3, measured(20_000, steep=True))
    assert (reencoded.status, reencoded.effective_quality) == (
        QualityStatus.UPSCALED,
        QualityTier.LOSSY_LOW,
    )
    assert (genuine.status, genuine.effective_quality) == (
        QualityStatus.GENUINE,
        QualityTier.LOSSY_HIGH,
    )


def test_too_quiet_is_not_judged() -> None:
    result = classify(CD, Measurements(loud_windows=2, cutoff=Cutoff(0, False, False)))
    assert (result.confidence, result.effective_quality) == (Confidence.LOW, None)


# --- reference set through FFmpeg -----------------------------------------------------------------


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    require_ffmpeg()
    folder = tmp_path_factory.mktemp("reference")
    return {
        "genuine_cd": flac(folder / "genuine_cd.flac", noise(rolloff_hz=15_000)),
        "mp3_as_flac": flac(folder / "mp3_as_flac.flac", noise(lowpass_hz=16_000)),
        "aac_96": lossy_round_trip(folder / "aac_96.flac", noise()),
        "genuine_hires": flac(
            folder / "genuine_hires.flac", noise(rate=96_000, lowpass_hz=40_000), 96_000, bits=24
        ),
        "fake_hires": flac(
            folder / "fake_hires.flac", noise(rate=96_000, lowpass_hz=20_000), 96_000, bits=24
        ),
        "padded_24": flac(folder / "padded_24.flac", noise(), bits=24, padded_from=16),
        "genuine_24": flac(folder / "genuine_24.flac", noise(), bits=24),
        "old_15k": flac(folder / "old_15k.flac", noise(lowpass_hz=15_000)),
        "silence": flac(folder / "silence.flac", noise(seconds=20) * 0),
    }


CASES = [
    ("genuine_cd", CD, QualityStatus.GENUINE, Confidence.HIGH, QualityTier.CD_LOSSLESS),
    ("mp3_as_flac", CD, QualityStatus.UPSCALED, Confidence.HIGH, QualityTier.LOSSY_LOW),
    ("aac_96", CD, QualityStatus.UPSCALED, Confidence.HIGH, QualityTier.LOSSY_LOW),
    ("genuine_hires", HIRES, QualityStatus.GENUINE, Confidence.HIGH, QualityTier.HIRES_LOSSLESS),
    ("fake_hires", HIRES, QualityStatus.UPSCALED, Confidence.HIGH, QualityTier.CD_LOSSLESS),
    ("padded_24", CD24, QualityStatus.UPSCALED, Confidence.HIGH, QualityTier.CD_LOSSLESS),
    ("genuine_24", CD24, QualityStatus.GENUINE, Confidence.HIGH, QualityTier.HIRES_LOSSLESS),
    (
        "old_15k",
        FileFacts(AudioFormat.FLAC, 44_100, 16, None, QualityTier.CD_LOSSLESS, 1965),
        QualityStatus.SUSPICIOUS,
        Confidence.LOW,
        None,
    ),
    ("silence", CD, QualityStatus.GENUINE, Confidence.LOW, None),
]


@pytest.mark.parametrize(("name", "facts", "status", "confidence", "tier"), CASES)
async def test_reference_set(reference, name, facts, status, confidence, tier) -> None:
    duration = 20.0 if name == "silence" else 50.0
    result = await analyze(str(reference[name]), facts, duration, ffmpeg="ffmpeg")

    assert (result.status, result.confidence, result.effective_quality) == (
        status,
        confidence,
        tier,
    ), result


async def test_excerpts_first_and_whole_file_when_inconclusive(reference) -> None:
    excerpts = await measure(str(reference["genuine_cd"]), CD, 50.0, ffmpeg="ffmpeg")
    whole = await measure(str(reference["genuine_cd"]), CD, 50.0, ffmpeg="ffmpeg", whole=True)
    old = FileFacts(AudioFormat.FLAC, 44_100, 16, None, QualityTier.CD_LOSSLESS, 1965)
    repeated = await analyze(str(reference["old_15k"]), old, 50.0, ffmpeg="ffmpeg")
    conclusive = await analyze(str(reference["genuine_cd"]), CD, 50.0, ffmpeg="ffmpeg")

    # Three 10-second excerpts read far fewer windows than the whole 50 seconds.
    assert excerpts.loud_windows < whole.loud_windows * 0.75
    assert repeated.whole_file
    assert not conclusive.whole_file
