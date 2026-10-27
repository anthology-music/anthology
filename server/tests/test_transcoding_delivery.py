"""The delivery decision (spec: transcoding; ADR 0013)."""

import pytest

from anthology.library.models import AudioFormat as F
from anthology.library.models import QualityTier as Q
from anthology.transcoding.delivery import Original, Variant, decide, effective_bitrate
from anthology.users.models import BitrateSetting as B

FLAC = Original(F.FLAC, 900, Q.CD_LOSSLESS, Q.CD_LOSSLESS)
HIRES = Original(F.FLAC, 2_800, Q.HIRES_LOSSLESS, Q.HIRES_LOSSLESS)
AIFF = Original(F.AIFF, 1_411, Q.CD_LOSSLESS, Q.CD_LOSSLESS)
OPUS_160 = Original(F.OPUS, 160, Q.LOSSY_LOW, Q.LOSSY_LOW)
MP3_320 = Original(F.MP3, 320, Q.LOSSY_HIGH, None)  # not analysed yet
MP3_192 = Original(F.MP3, 192, Q.LOSSY_LOW, Q.LOSSY_LOW)
FAKE_FLAC = Original(F.FLAC, 900, Q.CD_LOSSLESS, Q.LOSSY_LOW)  # upscaled from lossy
FAKE_MP3 = Original(F.MP3, 320, Q.LOSSY_HIGH, Q.LOSSY_LOW)

BROWSER = frozenset({F.FLAC, F.MP3, F.AAC, F.OPUS, F.VORBIS, F.WAV})
APPLE = frozenset({F.AAC, F.ALAC, F.MP3, F.WAV, F.AIFF})
MINIMAL = frozenset({F.AAC, F.MP3})


def aac(bitrate: int) -> Variant:
    return Variant(F.AAC, bitrate)


@pytest.mark.parametrize(
    ("original", "setting", "formats", "expected"),
    [
        # Bitrate per user and device: the phone at 128 kbit/s gets AAC 128.
        (FLAC, B.KBPS_128, BROWSER, aac(128)),
        (HIRES, B.KBPS_320, BROWSER, aac(320)),
        (FLAC, B.ORIGINAL, BROWSER, None),
        # Never upscale: Opus 160 on a device playing Opus at 320 stays the original.
        (OPUS_160, B.KBPS_320, BROWSER, None),
        (MP3_192, B.KBPS_256, BROWSER, None),
        (MP3_192, B.KBPS_192, BROWSER, None),
        (MP3_192, B.KBPS_128, BROWSER, aac(128)),
        # Format-aware delivery: FLAC on a device without FLAC.
        (FLAC, B.ORIGINAL, MINIMAL, aac(320)),
        # Compatibility transcodes.
        (OPUS_160, B.KBPS_320, APPLE, aac(192)),
        (OPUS_160, B.KBPS_128, APPLE, aac(128)),
        (OPUS_160, B.ORIGINAL, APPLE, aac(192)),
        (AIFF, B.ORIGINAL, frozenset({F.ALAC, F.AAC}), Variant(F.ALAC)),
        (AIFF, B.ORIGINAL, BROWSER, aac(320)),
        (AIFF, B.KBPS_256, APPLE, aac(256)),
        (FLAC, B.ORIGINAL, APPLE, Variant(F.ALAC)),
        # Quality before analysis: the declared MP3 320 stands in.
        (MP3_320, B.KBPS_192, BROWSER, aac(192)),
        (MP3_320, B.KBPS_320, BROWSER, None),
        # Upscaled files are worth the lowest step.
        (FAKE_FLAC, B.KBPS_320, BROWSER, None),
        (FAKE_FLAC, B.ORIGINAL, MINIMAL, aac(128)),
        (FAKE_MP3, B.KBPS_256, BROWSER, None),
        # No reported formats: AAC and MP3 assumed.
        (FLAC, B.ORIGINAL, None, aac(320)),
        (MP3_192, B.ORIGINAL, frozenset(), None),
    ],
)
def test_delivery_decision(original, setting, formats, expected) -> None:
    assert decide(original, setting, formats) == expected


@pytest.mark.parametrize("original", [FLAC, HIRES, AIFF, OPUS_160, MP3_320, MP3_192, FAKE_FLAC])
@pytest.mark.parametrize("setting", list(B))
@pytest.mark.parametrize("formats", [BROWSER, APPLE, MINIMAL, None])
def test_never_above_the_setting_or_the_original(original, setting, formats) -> None:
    variant = decide(original, setting, formats)
    if variant is None:
        assert original.format in (formats or MINIMAL)
        return
    assert variant.format in (F.AAC, F.ALAC)
    if variant.format == F.ALAC:
        assert setting == B.ORIGINAL and effective_bitrate(original) is None
        return
    if setting != B.ORIGINAL:
        assert variant.bitrate_kbps <= int(setting.value)
    worth = effective_bitrate(original)
    if worth is not None and setting != B.ORIGINAL and worth <= int(setting.value):
        # A compatibility transcode: the lowest step at or above the original.
        assert variant.bitrate_kbps == min(s for s in (128, 192, 256, 320) if s >= worth)


def test_variant_names() -> None:
    assert Variant.parse("aac-256") == aac(256)
    assert Variant.parse("alac") == Variant(F.ALAC)
    assert Variant.parse("aac-999") is None and Variant.parse("mp3-128") is None
    assert aac(128).name == "aac-128" and Variant(F.ALAC).name == "alac"
