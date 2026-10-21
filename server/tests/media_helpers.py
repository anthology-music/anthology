"""Generated test media (never copyrighted material) and the FFmpeg the tests need."""

import math
import os
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

RATE = 44_100


def tone_wav(path: Path, frequencies: list[float], seconds: float = 20.0) -> Path:
    """A stereo 16-bit WAV that steps through ``frequencies`` (one step per second)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for index in range(int(RATE * seconds)):
        frequency = frequencies[(index // RATE) % len(frequencies)]
        sample = int(8_000 * math.sin(2 * math.pi * frequency * index / RATE))
        frames += struct.pack("<hh", sample, sample)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(bytes(frames))
    return path


def require_ffmpeg() -> None:
    """Skip without FFmpeg (with the Chromaprint muxer); fail instead in CI.

    CI sets ANTHOLOGY_TEST_REQUIRE_FFMPEG=1 so that these tests never pass by being skipped.
    """
    ffmpeg = shutil.which("ffmpeg")
    usable = ffmpeg is not None and shutil.which("ffprobe") is not None
    if usable:
        muxers = subprocess.run(  # noqa: S603  (the FFmpeg found on the PATH)
            [ffmpeg, "-hide_banner", "-muxers"], capture_output=True, text=True, check=False
        ).stdout
        usable = " chromaprint " in muxers
    if usable:
        return
    message = "FFmpeg with the Chromaprint muxer is not installed"
    if os.environ.get("ANTHOLOGY_TEST_REQUIRE_FFMPEG"):
        pytest.fail(message)
    pytest.skip(message)
