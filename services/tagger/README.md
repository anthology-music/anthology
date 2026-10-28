# anthology-tagger

Tag reading and writing service for Anthology, based on [mutagen](https://github.com/quodlibet/mutagen).

- **License: GPL-2.0-or-later** (see `LICENSE`) – because it uses mutagen. The Anthology core (MIT) does not import this code; it calls the service through its interface.
- Runs as its own container (`anthology-tagger`, port 8410) in the Anthology pod, with the library, cache and imports volumes mounted at the same paths as in the server.
- Formats: FLAC, MP3, MP4/M4A (AAC, ALAC), Ogg Vorbis, Opus, WAV and AIFF (ID3 chunk).

## Interface v1

Full description: [`docs/architecture/tagger-api.md`](../../docs/architecture/tagger-api.md).

| Endpoint | Purpose |
|---|---|
| `POST /v1/tags/read` | read tags, embedded images and audio properties of one or more files; optionally extract images by content hash into a staging directory |
| `POST /v1/tags/write` | write tags (and images) into one or more files; `mode: atomic` (temp file + rename, for managed originals) or `mode: in_place` (keeps hardlinks, journaled backup, for referenced files with tag writing enabled) |
| `POST /v1/tags/copy` | write a copy of a file with complete context tags (and images) into the cache; the source is opened read-only |
| `GET /v1/health` | health, service version and interface version |

## Configuration

| Variable | Default |
|---|---|
| `ANTHOLOGY_TAGGER_ROOTS` | `/data/library,/data/cache,/data/imports` |
| `ANTHOLOGY_TAGGER_CACHE_ROOT` | `/data/cache` |
| `ANTHOLOGY_TAGGER_JOURNAL_DIR` | `/data/cache/tagger/journal` |
| `ANTHOLOGY_TAGGER_MAX_BATCH` | `200` |
| `ANTHOLOGY_TAGGER_PORT` | `8410` |

## Development

```
cd services/tagger
uv sync
uv run pytest            # needs ffmpeg (test media is generated)
uv run ruff check . && uv run ruff format --check .
uv run python -m tagger  # serves on port 8410
```

Container (from the repository root): `podman build -t anthology-tagger -f services/tagger/Containerfile .`
