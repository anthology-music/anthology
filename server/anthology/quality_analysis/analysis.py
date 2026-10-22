"""Measuring and classifying the effective quality of audio data (spec: quality-analysis,
Detection methods; Confidence instead of verdict).

FFmpeg decodes excerpts (or the whole file) to raw PCM in a separate process (ADR 0020); the
measurements run on the stream in blocks, so long files need little memory. Thresholds are
constants of this module; changing them means raising METHOD_VERSION, so that a re-run
analyses older results again.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from anthology.library.models import AudioFormat, QualityStatus, QualityTier
from anthology.quality_analysis.models import Confidence

METHOD_VERSION = 1

EXCERPT_SECONDS = 10.0
EXCERPT_POSITIONS = (0.2, 0.5, 0.8)
WHOLE_FILE_BELOW_SECONDS = 40.0
WINDOW = 8192
SILENT_DBFS = -60.0
MIN_LOUD_WINDOWS = 8
SMOOTHING_HZ = 100.0
CONTENT_BELOW_REFERENCE_DB = 70.0
CONTENT_ABOVE_FLOOR_DB = 10.0
FLOOR_BELOW_REFERENCE_DB = 20.0
FULL_BAND_MARGIN_HZ = 500.0
STEEP_DROP_DB = 30.0
CD_BANDWIDTH_HZ = 24_000.0
LOSSY_CUTOFF_BELOW_HZ = 20_500.0
# Steep edges from here up also occur on genuine CD masters: never a high-confidence verdict.
MASTERING_LOWPASS_FROM_HZ = 19_300.0
NATURAL_CUTOFF_HZ = 16_000.0
OLD_RECORDING_BEFORE = 1980
PADDED_SHARE = 0.999
CHUNK_BYTES = 1 << 20

LOSSLESS = frozenset({AudioFormat.FLAC, AudioFormat.WAV, AudioFormat.AIFF, AudioFormat.ALAC})
# Typical lowpass frequencies of lossy encoders and the bitrate they indicate.
ENCODER_LOWPASS = ((11_000, 64), (15_000, 96), (16_000, 128), (17_000, 160), (19_000, 192),
                   (19_500, 256), (20_000, 256), (20_500, 320))  # fmt: skip
LOWPASS_TOLERANCE_HZ = 500.0
# Lowpass a lossy file of a bitrate at least reaches (a far lower cutoff: lossy re-encode).
BITRATE_LOWPASS = ((320, 19_500), (256, 19_000), (192, 17_500), (160, 16_500), (128, 15_500))
BELOW_BITRATE_HZ = 3_000.0


class DecodeError(Exception):
    """FFmpeg could not decode the file; ``reason`` is stored as the finding."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


# --- measurements on samples ------------------------------------------------------------------


class SpectrumAccumulator:
    """Average power spectrum of the loud windows (Welch's method, Hann, 50 % overlap)."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._window = np.hanning(WINDOW).astype(np.float64)
        self._scale = float(np.sum(self._window**2))
        self._power = np.zeros(WINDOW // 2 + 1)
        self._rest = np.zeros(0, dtype=np.float32)
        self.loud_windows = 0
        self._silent = 10 ** (SILENT_DBFS / 20)

    def add(self, samples: np.ndarray) -> None:
        data = np.concatenate([self._rest, samples.astype(np.float32, copy=False)])
        hop = WINDOW // 2
        count = (len(data) - WINDOW) // hop + 1 if len(data) >= WINDOW else 0
        for index in range(count):
            frame = data[index * hop : index * hop + WINDOW].astype(np.float64)
            if np.sqrt(np.mean(frame**2)) < self._silent:
                continue
            self._power += np.abs(np.fft.rfft(frame * self._window)) ** 2 / self._scale
            self.loud_windows += 1
        self._rest = data[count * hop :] if count else data

    def end_segment(self) -> None:
        """Excerpts are not contiguous: never let a window span two of them."""
        self._rest = np.zeros(0, dtype=np.float32)

    def levels(self) -> tuple[np.ndarray, np.ndarray]:
        """(frequencies in Hz, level in dB) of the averaged, smoothed spectrum."""
        freqs = np.fft.rfftfreq(WINDOW, 1 / self.sample_rate)
        power = self._power / max(self.loud_windows, 1)
        width = max(1, round(SMOOTHING_HZ / (self.sample_rate / WINDOW)))
        smoothed = np.convolve(power, np.ones(width) / width, mode="same")
        return freqs, 10 * np.log10(smoothed + 1e-30)


@dataclass(frozen=True)
class Cutoff:
    hz: float
    steep: bool
    full_band: bool


def find_cutoff(freqs: np.ndarray, levels: np.ndarray, sample_rate: int) -> Cutoff:
    """Highest frequency with real content and whether the spectrum ends in a brick wall.

    Content is anything within 70 dB of the music's level (median of 1-4 kHz) and clearly
    above the noise floor. A brick wall drops at least 30 dB from 700 Hz below the cutoff to
    500 Hz above it; music rolls off gradually.
    """
    nyquist = sample_rate / 2
    usable = freqs < nyquist - SMOOTHING_HZ
    reference = float(np.median(levels[(freqs >= 1_000) & (freqs <= 4_000)]))
    floor = float(np.percentile(levels[usable], 1))
    # Without a floor clearly below the music (full-band content), the floor rule is void.
    threshold = max(
        reference - CONTENT_BELOW_REFERENCE_DB,
        min(floor + CONTENT_ABOVE_FLOOR_DB, reference - FLOOR_BELOW_REFERENCE_DB),
    )
    content = np.nonzero(usable & (levels >= threshold))[0]
    hz = float(freqs[content[-1]]) if len(content) else 0.0

    def level_at(frequency: float) -> float:
        index = int(np.clip(np.searchsorted(freqs, frequency), 0, len(freqs) - 1))
        return float(levels[index])

    full_band = hz >= nyquist - FULL_BAND_MARGIN_HZ - SMOOTHING_HZ
    above = min(hz + 500, nyquist - SMOOTHING_HZ)
    steep = not full_band and level_at(hz - 700) - level_at(above) >= STEEP_DROP_DB
    return Cutoff(hz=hz, steep=steep, full_band=full_band)


class BitDepthAccumulator:
    """Share of non-silent samples whose 8 lowest of 24 bits are zero (padded 16 bit)."""

    def __init__(self) -> None:
        self.samples = 0
        self.padded = 0

    def add(self, samples: np.ndarray) -> None:
        # s32le from FFmpeg: 24-bit audio occupies the upper 24 bits.
        loud = samples[np.abs(samples) >= (1 << 16)]
        self.samples += len(loud)
        self.padded += int(np.count_nonzero((loud >> 8) & 0xFF == 0))

    @property
    def effective_bits(self) -> int | None:
        if self.samples < 10_000:
            return None
        return 16 if self.padded / self.samples > PADDED_SHARE else 24


def encoder_bitrate(cutoff_hz: float) -> int | None:
    """Bitrate of the lossy encoder whose typical lowpass matches the cutoff."""
    for lowpass, bitrate in ENCODER_LOWPASS:
        if abs(cutoff_hz - lowpass) <= LOWPASS_TOLERANCE_HZ:
            return bitrate
    return None


def nearest_bitrate(cutoff_hz: float) -> int:
    return min(ENCODER_LOWPASS, key=lambda entry: abs(entry[0] - cutoff_hz))[1]


# --- classification ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileFacts:
    format: AudioFormat
    sample_rate_hz: int
    bit_depth: int | None
    bitrate_kbps: int | None
    declared_quality: QualityTier
    release_year: int | None = None


@dataclass(frozen=True)
class Measurements:
    loud_windows: int
    cutoff: Cutoff
    effective_bits: int | None = None


@dataclass
class Result:
    status: QualityStatus
    confidence: Confidence
    finding: str
    values: dict[str, Any] = field(default_factory=dict)
    effective_quality: QualityTier | None = None
    cutoff_hz: int | None = None
    effective_sample_rate_hz: int | None = None
    effective_bit_depth: int | None = None
    estimated_bitrate_kbps: int | None = None
    whole_file: bool = False

    @property
    def conclusive(self) -> bool:
        return self.confidence == Confidence.HIGH


def _lossy_tier(bitrate_kbps: int) -> QualityTier:
    return QualityTier.LOSSY_HIGH if bitrate_kbps >= 256 else QualityTier.LOSSY_LOW


def _cd_rate(sample_rate: int) -> int:
    return 44_100 if sample_rate % 44_100 == 0 else 48_000


def classify(facts: FileFacts, measured: Measurements) -> Result:
    """Status, confidence, finding and effective quality; the first matching rule decides."""
    cutoff = measured.cutoff
    cutoff_hz = round(cutoff.hz)
    old = facts.release_year is not None and facts.release_year < OLD_RECORDING_BEFORE
    if measured.loud_windows < MIN_LOUD_WINDOWS:
        return Result(QualityStatus.GENUINE, Confidence.LOW, "too_quiet")

    if facts.format in LOSSLESS:
        encoder = encoder_bitrate(cutoff.hz)
        upsampled_cd = facts.sample_rate_hz > 48_000 and cutoff.hz >= MASTERING_LOWPASS_FROM_HZ
        if cutoff.steep and not upsampled_cd and cutoff.hz < MASTERING_LOWPASS_FROM_HZ:
            if old:
                return _old(cutoff_hz, facts.release_year)
            if encoder is not None:
                return Result(
                    QualityStatus.UPSCALED,
                    Confidence.HIGH,
                    "lossy_origin",
                    {"cutoff_hz": cutoff_hz, "bitrate_kbps": encoder},
                    effective_quality=_lossy_tier(encoder),
                    cutoff_hz=cutoff_hz,
                    estimated_bitrate_kbps=encoder,
                )
            return Result(
                QualityStatus.SUSPICIOUS,
                Confidence.MEDIUM,
                "cutoff_without_encoder_match",
                {"cutoff_hz": cutoff_hz},
                cutoff_hz=cutoff_hz,
            )
        if cutoff.steep and not upsampled_cd and cutoff.hz <= LOSSY_CUTOFF_BELOW_HZ:
            # A mastering lowpass or a high-bitrate lossy origin: not decidable here.
            return Result(
                QualityStatus.GENUINE,
                Confidence.MEDIUM,
                "possible_lossy_origin",
                {"cutoff_hz": cutoff_hz, "bitrate_kbps": nearest_bitrate(cutoff.hz)},
                cutoff_hz=cutoff_hz,
            )
        if cutoff.hz < NATURAL_CUTOFF_HZ:
            if old:
                return _old(cutoff_hz, facts.release_year)
            return Result(
                QualityStatus.SUSPICIOUS,
                Confidence.MEDIUM,
                "cutoff_without_encoder_match",
                {"cutoff_hz": cutoff_hz},
                cutoff_hz=cutoff_hz,
            )
        hires_content = facts.sample_rate_hz > 48_000 and cutoff.hz > CD_BANDWIDTH_HZ
        if (facts.bit_depth or 16) > 16 and measured.effective_bits == 16:
            return Result(
                QualityStatus.UPSCALED,
                Confidence.HIGH,
                "padded_bit_depth",
                {"bits": facts.bit_depth},
                effective_quality=(
                    QualityTier.HIRES_LOSSLESS if hires_content else QualityTier.CD_LOSSLESS
                ),
                cutoff_hz=cutoff_hz,
                effective_bit_depth=16,
                effective_sample_rate_hz=(
                    facts.sample_rate_hz if hires_content else _cd_rate(facts.sample_rate_hz)
                ),
            )
        if facts.sample_rate_hz > 48_000 and not hires_content:
            return Result(
                QualityStatus.UPSCALED,
                Confidence.HIGH,
                "no_hires_content",
                {"sample_rate_hz": facts.sample_rate_hz},
                effective_quality=QualityTier.CD_LOSSLESS,
                cutoff_hz=cutoff_hz,
                effective_sample_rate_hz=_cd_rate(facts.sample_rate_hz),
                effective_bit_depth=measured.effective_bits,
            )
    elif facts.bitrate_kbps and cutoff.steep:
        expected = next(
            (lowpass for bitrate, lowpass in BITRATE_LOWPASS if facts.bitrate_kbps >= bitrate),
            None,
        )
        if expected is not None and cutoff.hz < expected - BELOW_BITRATE_HZ:
            estimated = nearest_bitrate(cutoff.hz)
            return Result(
                QualityStatus.UPSCALED,
                Confidence.HIGH,
                "lossy_below_bitrate",
                {"cutoff_hz": cutoff_hz, "bitrate_kbps": estimated},
                effective_quality=_lossy_tier(estimated),
                cutoff_hz=cutoff_hz,
                estimated_bitrate_kbps=estimated,
            )

    return Result(
        QualityStatus.GENUINE,
        Confidence.HIGH,
        "genuine",
        effective_quality=facts.declared_quality,
        cutoff_hz=cutoff_hz,
        effective_sample_rate_hz=facts.sample_rate_hz,
        effective_bit_depth=measured.effective_bits or facts.bit_depth,
    )


def _old(cutoff_hz: int, year: int | None) -> Result:
    """Old recordings: a low cutoff is only suspicious (spec: Old recording with little treble)."""
    return Result(
        QualityStatus.SUSPICIOUS,
        Confidence.LOW,
        "low_cutoff_old_recording",
        {"cutoff_hz": cutoff_hz, "year": year},
        cutoff_hz=cutoff_hz,
    )


# --- decoding ---------------------------------------------------------------------------------


async def _pcm(
    path: str, ffmpeg: str, *, start: float | None, seconds: float | None, raw: str
) -> AsyncIterator[np.ndarray]:
    """Raw PCM of the first audio stream in blocks: mono float or all channels as int32."""
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    if seconds is not None:
        args += ["-t", f"{seconds:.3f}"]
    args += ["-i", path, "-map", "0:a:0"]
    if raw == "f32le":
        args += ["-ac", "1", "-c:a", "pcm_f32le", "-f", "f32le", "-"]
        dtype = np.dtype("<f4")
    else:
        args += ["-c:a", "pcm_s32le", "-f", "s32le", "-"]
        dtype = np.dtype("<i4")
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"{ffmpeg} is not installed") from error
    if process.stdout is None or process.stderr is None:  # pragma: no cover  (PIPE requested)
        raise RuntimeError("no pipes")
    stderr = asyncio.create_task(process.stderr.read())
    rest = b""
    try:
        while chunk := await process.stdout.read(CHUNK_BYTES):
            data = rest + chunk
            usable = len(data) - len(data) % dtype.itemsize
            rest = data[usable:]
            if usable:
                yield np.frombuffer(data[:usable], dtype=dtype)
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()
        message = (await stderr).decode(errors="replace").strip()
    if process.returncode not in (0, -9) and message:
        raise DecodeError("unreadable_audio", message[-300:])


def _sections(duration_s: float, whole: bool) -> list[tuple[float | None, float | None]]:
    if whole or duration_s < WHOLE_FILE_BELOW_SECONDS:
        return [(None, None)]
    return [
        (max(0.0, duration_s * position - EXCERPT_SECONDS / 2), EXCERPT_SECONDS)
        for position in EXCERPT_POSITIONS
    ]


async def measure(
    path: str, facts: FileFacts, duration_s: float, *, ffmpeg: str, whole: bool = False
) -> Measurements:
    """Spectrum (and, for files declaring more than 16 bit, bit depth) of excerpts or the
    whole file."""
    spectrum = SpectrumAccumulator(facts.sample_rate_hz)
    bits = BitDepthAccumulator() if (facts.bit_depth or 16) > 16 else None
    for start, seconds in _sections(duration_s, whole):
        async for block in _pcm(path, ffmpeg, start=start, seconds=seconds, raw="f32le"):
            spectrum.add(block)
        spectrum.end_segment()
        if bits is not None:
            async for block in _pcm(path, ffmpeg, start=start, seconds=seconds, raw="s32le"):
                bits.add(block)
    if spectrum.loud_windows == 0:
        return Measurements(loud_windows=0, cutoff=Cutoff(0.0, False, False))
    freqs, levels = spectrum.levels()
    return Measurements(
        loud_windows=spectrum.loud_windows,
        cutoff=find_cutoff(freqs, levels, facts.sample_rate_hz),
        effective_bits=bits.effective_bits if bits is not None else None,
    )


async def analyze(path: str, facts: FileFacts, duration_s: float, *, ffmpeg: str) -> Result:
    """Excerpts first; an inconclusive result is repeated on the whole file once (spec:
    Efficient execution)."""
    result = classify(facts, await measure(path, facts, duration_s, ffmpeg=ffmpeg))
    if result.conclusive or duration_s < WHOLE_FILE_BELOW_SECONDS:
        return result
    result = classify(facts, await measure(path, facts, duration_s, ffmpeg=ffmpeg, whole=True))
    result.whole_file = True
    return result
