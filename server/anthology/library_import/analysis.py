"""Reading an import file: tags (tinytag), technical data (ffprobe) and the audio hash
(FFmpeg's hash muxer over the audio packets, tags excluded).

FFmpeg runs as a separate process with argument lists (ADR 0004, ADR 0020).
"""

import asyncio
import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tinytag import TinyTag, TinyTagException

from anthology.library.models import AudioFormat, QualityTier

LOSSLESS = frozenset({AudioFormat.FLAC, AudioFormat.WAV, AudioFormat.AIFF, AudioFormat.ALAC})
ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")


class Broken(Exception):
    """The file cannot be read as audio; ``reason`` becomes the item's note."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass
class Tags:
    title: str | None = None
    artist: str | None = None
    album_artist: str | None = None
    album: str | None = None
    track: int | None = None
    track_total: int | None = None
    disc: int | None = None
    disc_total: int | None = None
    year: int | None = None
    isrc: str | None = None
    mb_recording_id: str | None = None


@dataclass
class Technical:
    format: AudioFormat
    codec: str
    sample_rate_hz: int
    channels: int
    duration_ms: int
    bit_depth: int | None = None
    bitrate_kbps: int | None = None

    @property
    def declared_quality(self) -> QualityTier:
        if self.format in LOSSLESS:
            hires = self.sample_rate_hz > 48_000 or (self.bit_depth or 16) > 16
            return QualityTier.HIRES_LOSSLESS if hires else QualityTier.CD_LOSSLESS
        return QualityTier.LOSSY_HIGH if (self.bitrate_kbps or 0) >= 256 else QualityTier.LOSSY_LOW


@dataclass
class FileInfo:
    tags: Tags
    technical: Technical
    audio_hash: str

    def to_json(self) -> str:
        return json.dumps(
            {"tags": asdict(self.tags), "technical": asdict(self.technical)}, sort_keys=True
        )

    @staticmethod
    def from_json(value: str, audio_hash: str) -> "FileInfo":
        data = json.loads(value)
        technical = data["technical"]
        technical["format"] = AudioFormat(technical["format"])
        return FileInfo(Tags(**data["tags"]), Technical(**technical), audio_hash)


# --- tags ---------------------------------------------------------------------------------------


def _first(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> int | None:
    text = _first(value)
    if text is None:
        return None
    match = re.match(r"\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _isrc(value: Any) -> str | None:
    text = _first(value)
    if text is None:
        return None
    text = text.replace("-", "").upper()
    return text if ISRC.match(text) else None


def _mbid(value: Any) -> str | None:
    text = _first(value)
    try:
        return str(uuid.UUID(text)) if text else None
    except ValueError:
        return None


def read_tags(path: str) -> Tags:
    """Tags of a file (blocking). Raises Broken if the file cannot be parsed."""
    try:
        tag = TinyTag.get(path, image=False)
    except (TinyTagException, OSError, ValueError, KeyError, IndexError) as error:
        raise Broken("unreadable_tags", str(error)) from error
    other = tag.other or {}
    return Tags(
        title=_first(tag.title),
        artist=_first(tag.artist),
        album_artist=_first(tag.albumartist),
        album=_first(tag.album),
        track=_number(tag.track),
        track_total=_number(tag.track_total),
        disc=_number(tag.disc),
        disc_total=_number(tag.disc_total),
        year=_number(tag.year),
        isrc=_isrc(other.get("isrc")),
        mb_recording_id=_mbid(other.get("musicbrainz_trackid")),
    )


# --- technical data and audio hash ----------------------------------------------------------------


async def _run(*args: str) -> bytes:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as error:  # FFmpeg itself is missing: not the file's fault
        raise RuntimeError(f"{args[0]} is not installed") from error
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise Broken("unreadable_audio", stderr.decode(errors="replace").strip()[-300:])
    return stdout


def _format(codec: str, container: str) -> AudioFormat | None:
    if codec.startswith("pcm_"):
        if "aiff" in container:
            return AudioFormat.AIFF
        if "wav" in container:
            return AudioFormat.WAV
        return None
    return {
        "flac": AudioFormat.FLAC,
        "alac": AudioFormat.ALAC,
        "mp3": AudioFormat.MP3,
        "aac": AudioFormat.AAC,
        "opus": AudioFormat.OPUS,
        "vorbis": AudioFormat.VORBIS,
    }.get(codec)


def _int(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number or None


async def read_technical(path: str, ffprobe: str) -> Technical:
    output = await _run(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,bits_per_raw_sample,bits_per_sample,bit_rate"
        ":format=duration,bit_rate,format_name",
        "-of",
        "json",
        path,
    )
    data = json.loads(output or b"{}")
    streams = data.get("streams") or []
    if not streams:
        raise Broken("no_audio")
    stream, container = streams[0], data.get("format") or {}
    codec = stream.get("codec_name") or ""
    audio_format = _format(codec, container.get("format_name") or "")
    if audio_format is None:
        raise Broken("unsupported_format", codec)
    duration = float(container.get("duration") or 0)
    sample_rate = _int(stream.get("sample_rate"))
    if duration <= 0 or not sample_rate:
        raise Broken("unreadable_audio", "no duration")
    bit_rate = _int(stream.get("bit_rate")) or _int(container.get("bit_rate"))
    bit_depth = _int(stream.get("bits_per_raw_sample")) or _int(stream.get("bits_per_sample"))
    return Technical(
        format=audio_format,
        codec=codec,
        sample_rate_hz=sample_rate,
        channels=_int(stream.get("channels")) or 2,
        duration_ms=round(duration * 1000),
        bit_depth=bit_depth if audio_format in LOSSLESS else None,
        bitrate_kbps=round(bit_rate / 1000) if bit_rate else None,
    )


async def audio_hash(path: str, ffmpeg: str) -> str:
    """SHA-256 of the first audio stream's packets: equal for files differing only in tags."""
    output = await _run(
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        path,
        "-map",
        "0:a:0",
        "-c:a",
        "copy",
        "-f",
        "hash",
        "-hash",
        "sha256",
        "-",
    )
    text = output.decode().strip()
    if not text.startswith("SHA256="):
        raise Broken("unreadable_audio", "no audio hash")
    return text.removeprefix("SHA256=").lower()


async def read_file(path: str, *, ffmpeg: str, ffprobe: str) -> FileInfo:
    """Everything the import needs of one file. Raises Broken for files that are not audio."""
    if not await asyncio.to_thread(Path(path).is_file):
        raise Broken("missing")
    tags = await asyncio.to_thread(read_tags, path)
    technical = await read_technical(path, ffprobe)
    return FileInfo(tags=tags, technical=technical, audio_hash=await audio_hash(path, ffmpeg))
