"""Generated reference audio for the quality analysis (never copyrighted material).

Signals are noise at -20 dBFS with optional band limits, written as WAV and re-encoded with
FFmpeg where a test needs FLAC or a lossy round trip.
"""

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

from tests.media_helpers import encode


def noise(
    seconds: float = 50.0,
    rate: int = 44_100,
    *,
    lowpass_hz: float | None = None,
    highpass_hz: float | None = None,
    rolloff_hz: float | None = None,
    seed: int = 7,
) -> np.ndarray:
    """Stereo noise in [-1, 1]: brick-wall lowpass, or a gradual roll-off (6 dB per kHz above
    ``rolloff_hz``) like the treble of real music."""
    generator = np.random.default_rng(seed)
    samples = generator.normal(0, 0.1, size=(int(seconds * rate), 2))
    if lowpass_hz or highpass_hz or rolloff_hz:
        spectrum = np.fft.rfft(samples, axis=0)
        freqs = np.fft.rfftfreq(len(samples), 1 / rate)
        if lowpass_hz:
            spectrum[freqs > lowpass_hz] = 0
        if highpass_hz:
            spectrum[freqs < highpass_hz] = 0
        if rolloff_hz:
            attenuation_db = np.clip((freqs - rolloff_hz) / 1000 * 6, 0, None)
            spectrum *= (10 ** (-attenuation_db / 20))[:, None]
        samples = np.fft.irfft(spectrum, n=len(samples), axis=0)
    return np.clip(samples, -1, 1)


def write_wav(path: Path, samples: np.ndarray, rate: int = 44_100, *, bits: int = 16,
              padded_from: int | None = None) -> Path:  # fmt: skip
    """PCM WAV; ``padded_from=16`` stores 16-bit samples in a 24-bit file (lowest 8 bits 0)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source_bits = padded_from or bits
    scaled = np.round(samples * (2 ** (source_bits - 1) - 1)).astype(np.int64)
    scaled <<= bits - source_bits
    width = bits // 8
    as_int32 = scaled.reshape(-1).astype("<i4")
    if width == 3:  # the lowest three bytes of each little-endian int32
        raw = as_int32.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    else:
        raw = as_int32.astype(f"<i{width}").tobytes()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(samples.shape[1])
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(raw)
    return path


def flac(path: Path, samples: np.ndarray, rate: int = 44_100, **options) -> Path:
    source = write_wav(path.with_suffix(".source.wav"), samples, rate, **options)
    return encode(source, path)


def lossy_round_trip(path: Path, samples: np.ndarray, bitrate: str = "96k") -> Path:
    """The noise encoded with FFmpeg's native AAC encoder, decoded back into a FLAC file."""
    source = write_wav(path.with_suffix(".source.wav"), samples)
    lossy = path.with_suffix(".m4a")
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    subprocess.run([*args, "-c:a", "aac", "-b:a", bitrate, str(lossy)], check=True)  # noqa: S603
    return encode(lossy, path)
