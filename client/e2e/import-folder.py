"""Generates the folder the end-to-end test imports: two tagged FLAC files of sine tones.

Usage: python import-folder.py <import root>   (needs FFmpeg on the PATH)
"""

import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 44_100
SONGS = [("01 Frühling.flac", "Frühling", [440, 660, 550]), ("02 Sommer.flac", "Sommer", [330, 392])]


def tone(path: Path, frequencies: list[int], seconds: int = 8) -> None:
    frames = bytearray()
    for index in range(RATE * seconds):
        frequency = frequencies[(index // RATE) % len(frequencies)]
        sample = int(8_000 * math.sin(2 * math.pi * frequency * index / RATE))
        frames += struct.pack("<hh", sample, sample)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(bytes(frames))


def main(root: Path) -> None:
    album = root / "Kassette 1985"
    album.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    with tempfile.TemporaryDirectory() as scratch:
        for number, (name, title, frequencies) in enumerate(SONGS, start=1):
            source = Path(scratch) / f"{number}.wav"
            tone(source, frequencies)
            tags = {"title": title, "artist": "4 Jahreszeiten", "album": "Kassette 1985"}
            args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
            for key, value in {**tags, "track": str(number)}.items():
                args += ["-metadata", f"{key}={value}"]
            subprocess.run([*args, str(album / name)], check=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
