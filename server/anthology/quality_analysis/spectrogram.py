"""Spectrogram images as evidence in the review list (spec: review, Quality findings).

FFmpeg decodes 30 seconds from the middle of the file to PCM (as for the analysis); numpy
computes the spectrogram and the PNG is written with zlib, so the FFmpeg build needs no image
encoder or video filter (ADR 0020).
"""

import struct
import zlib

import numpy as np

from anthology.quality_analysis.analysis import _pcm

WIDTH = 1024
HEIGHT = 512
FFT_SIZE = 2 * HEIGHT
SECONDS = 30.0
RANGE_DB = 100.0
# Colour stops from silence to full level: black, blue, red, yellow, white.
STOPS = np.array(
    [[0, 0, 0], [32, 32, 160], [200, 32, 64], [250, 200, 40], [255, 255, 255]], dtype=float
)


async def render(path: str, duration_s: float, *, ffmpeg: str) -> bytes:
    """A PNG spectrogram of 30 seconds from the middle of the file: time to the right,
    frequency upwards up to half the sample rate."""
    start = max(0.0, duration_s / 2 - SECONDS / 2)
    blocks = [
        block async for block in _pcm(path, ffmpeg, start=start, seconds=SECONDS, raw="f32le")
    ]
    samples = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)
    return png(colours(levels(samples)))


def levels(samples: np.ndarray) -> np.ndarray:
    """Levels 0..1 (``RANGE_DB`` below the loudest bin to the loudest), HEIGHT by WIDTH with the
    highest frequency in the first row."""
    if len(samples) < FFT_SIZE:
        samples = np.pad(samples, (0, FFT_SIZE - len(samples)))
    hop = (len(samples) - FFT_SIZE) / max(1, WIDTH - 1)
    starts = (np.arange(WIDTH) * hop).astype(int)
    frames = np.stack([samples[start : start + FFT_SIZE] for start in starts])
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(FFT_SIZE), axis=1))[:, :HEIGHT]
    decibels = 20 * np.log10(spectrum + 1e-10)
    top = decibels.max()
    scaled = np.clip((decibels - (top - RANGE_DB)) / RANGE_DB, 0.0, 1.0)
    return scaled.T[::-1]


def colours(values: np.ndarray) -> np.ndarray:
    positions = values * (len(STOPS) - 1)
    lower = np.minimum(positions.astype(int), len(STOPS) - 2)
    fraction = (positions - lower)[..., None]
    rgb = STOPS[lower] * (1 - fraction) + STOPS[lower + 1] * fraction
    return rgb.astype(np.uint8)


def png(rgb: np.ndarray) -> bytes:
    """An 8-bit RGB PNG (no filter) of an array of shape (height, width, 3)."""
    height, width, _ = rgb.shape
    rows = b"".join(b"\0" + rgb[row].tobytes() for row in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )
