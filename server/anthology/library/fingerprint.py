"""Acoustic fingerprints with FFmpeg's Chromaprint muxer (spec: library, Stored fingerprints).

FFmpeg runs as a separate process with an argument list (ADR 0004, ADR 0020). A fingerprint
covers the first 120 seconds, like ``fpcalc``; the duration is the whole file's.
"""

import asyncio
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
