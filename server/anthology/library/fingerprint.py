"""Acoustic fingerprints with FFmpeg's Chromaprint muxer (spec: library, Stored fingerprints).

FFmpeg runs as a separate process with an argument list (ADR 0004, ADR 0020). A fingerprint
covers the first 120 seconds, like ``fpcalc``; the duration is the whole file's.
"""

import asyncio
import base64
import os
from dataclasses import dataclass

FINGERPRINT_SECONDS = 120


class FingerprintError(Exception):
    """The fingerprint could not be computed; ``reason`` is stored as identification note."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class Fingerprint:
    fingerprint: str  # compressed and base64-encoded, as AcoustID expects
    duration_s: int


async def _run(*args: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise FingerprintError("fingerprint_failed", stderr.decode(errors="replace").strip()[-300:])
    return stdout


async def compute(path: str, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> Fingerprint:
    if not await asyncio.to_thread(os.path.isfile, path):
        raise FingerprintError("file_missing", path)
    try:
        duration = await _run(
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        )
        fingerprint = await _run(
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            path,
            "-t",
            str(FINGERPRINT_SECONDS),
            "-f",
            "chromaprint",
            "-fp_format",
            "base64",
            "-",
        )
    except FileNotFoundError as error:  # FFmpeg itself is missing
        raise FingerprintError("ffmpeg_missing", str(error)) from error
    try:
        seconds = round(float(duration.decode().strip()))
    except ValueError as error:
        raise FingerprintError("fingerprint_failed", "unknown duration") from error
    value = fingerprint.decode().strip()
    if not value:
        raise FingerprintError("fingerprint_failed", "empty fingerprint")
    return Fingerprint(fingerprint=value, duration_s=seconds)


# --- local comparison (library import: fingerprint candidates) --------------------------------

# Offsets (in fingerprint items of ~0.12 s) tried when aligning two fingerprints.
MAX_OFFSET = 16
MIN_OVERLAP = 40


def decode(fingerprint: str) -> list[int]:
    """The raw 32-bit items of a compressed, base64-encoded Chromaprint fingerprint.

    Format of Chromaprint's ``FingerprintCompressor``: one byte algorithm, three bytes item
    count, then the bit positions of each item XOR its predecessor as 3-bit values (0 ends an
    item, 7 continues in a 5-bit exception value after the 3-bit stream).
    """
    data = base64.urlsafe_b64decode(fingerprint + "=" * (-len(fingerprint) % 4))
    if len(data) < 4:
        raise ValueError("fingerprint too short")
    count = int.from_bytes(data[1:4], "big")
    bits = int.from_bytes(data[4:], "little")
    available = (len(data) - 4) * 8
    normal: list[int] = []
    offset = ends = 0
    while ends < count and offset + 3 <= available:
        value = (bits >> offset) & 7
        offset += 3
        normal.append(value)
        if value == 0:
            ends += 1
    offset = (offset + 7) // 8 * 8  # exceptions start at the next byte
    items: list[int] = []
    item = position = previous = 0
    for value in normal:
        if value == 7:
            value += (bits >> offset) & 31
            offset += 5
        if value == 0:
            previous ^= item
            items.append(previous)
            item = position = 0
        else:
            position += value
            item |= 1 << (position - 1)
    return items


def similarity(first: list[int], second: list[int]) -> float:
    """Share of equal bits (0..1) at the best alignment within ±MAX_OFFSET items.

    Fingerprints of the same audio score close to 1, unrelated audio around 0.5.
    """
    best = 0.0
    for offset in range(-MAX_OFFSET, MAX_OFFSET + 1):
        pairs = list(zip(first[max(0, offset) :], second[max(0, -offset) :], strict=False))
        if len(pairs) < MIN_OVERLAP:
            continue
        errors = sum((a ^ b).bit_count() for a, b in pairs)
        best = max(best, 1 - errors / (32 * len(pairs)))
    return best
