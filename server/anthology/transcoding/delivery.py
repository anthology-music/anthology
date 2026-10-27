"""The delivery decision (spec: transcoding, Never upscale, Format-aware delivery,
Compatibility transcodes, Quality before analysis; ADR 0013): what one target receives of one
original. A pure function, so that every combination can be tested."""

from dataclasses import dataclass

from anthology.library.models import AudioFormat, QualityTier
from anthology.users.models import BitrateSetting

# Bitrate steps of transcodes, lowest first.
STEPS = (128, 192, 256, 320)
LOSSLESS_TIERS = frozenset({QualityTier.HIRES_LOSSLESS, QualityTier.CD_LOSSLESS})
# Assumed when a target reported no formats (playable-delivery-format).
DEFAULT_FORMATS = frozenset({AudioFormat.AAC, AudioFormat.MP3})


@dataclass(frozen=True)
class Original:
    format: AudioFormat
    bitrate_kbps: int | None
    declared: QualityTier
    effective: QualityTier | None


@dataclass(frozen=True)
class Variant:
    """A transcode: AAC at ``bitrate_kbps``, or ALAC (no bitrate)."""

    format: AudioFormat
    bitrate_kbps: int | None = None

    @property
    def name(self) -> str:
        return "alac" if self.format == AudioFormat.ALAC else f"aac-{self.bitrate_kbps}"

    @classmethod
    def parse(cls, name: str) -> "Variant | None":
        if name == "alac":
            return cls(AudioFormat.ALAC)
        kind, _, bitrate = name.partition("-")
        if kind == "aac" and bitrate.isdigit() and int(bitrate) in STEPS:
            return cls(AudioFormat.AAC, int(bitrate))
        return None


def effective_bitrate(original: Original) -> int | None:
    """The bitrate the original is worth; None for lossless (above every step).

    Before the analysis the declared tier stands in. A lossy file that the analysis found
    below its declared bitrate (``lossy_low`` at 256 kbit/s or more) is worth the lowest step:
    its real bitrate is unknown, and anything higher could upscale it.
    """
    tier = original.effective or original.declared
    if tier in LOSSLESS_TIERS:
        return None
    bitrate = original.bitrate_kbps or STEPS[0]
    if tier == QualityTier.LOSSY_LOW and bitrate >= 256:
        return STEPS[0]
    return bitrate


def _setting(setting: BitrateSetting) -> int | None:
    return None if setting == BitrateSetting.ORIGINAL else int(setting.value)


def decide(
    original: Original, setting: BitrateSetting, formats: frozenset[AudioFormat] | None
) -> Variant | None:
    """None: deliver the original; otherwise the transcode to deliver."""
    playable = formats if formats else DEFAULT_FORMATS
    limit = _setting(setting)
    worth = effective_bitrate(original)
    if original.format in playable and (limit is None or (worth is not None and worth <= limit)):
        return None
    if limit is not None and (worth is None or worth > limit):
        return Variant(AudioFormat.AAC, limit)
    # The target cannot play the format: a compatibility transcode.
    if worth is None:
        if AudioFormat.ALAC in playable:
            return Variant(AudioFormat.ALAC)
        return Variant(AudioFormat.AAC, STEPS[-1])
    step = next((value for value in STEPS if value >= worth), STEPS[-1])
    return Variant(AudioFormat.AAC, min(step, limit) if limit is not None else step)
