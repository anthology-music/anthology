# anthology-tagger

Tag reading and writing service for Anthology, based on [mutagen](https://github.com/quodlibet/mutagen).

- **License: GPL-2.0-or-later** (see `LICENSE`) – because it uses mutagen. The Anthology core (MIT) does not import this code; it calls the service through its interface.
- Runs as its own container (`anthology-tagger`) in the Anthology pod.
- Several long-lived workers; requests are batched for large libraries.

## Interface (draft, versioned)

| Endpoint | Purpose |
|---|---|
| `POST /v1/tags/read` | read full tags, cover and audio properties of one or more files |
| `POST /v1/tags/write` | write tags (and cover) into one or more files |
| `POST /v1/header/build` | build a tag header with context tags for streaming an original (FLAC metadata blocks, ID3v2) and return audio-data offsets |
| `GET /v1/health` | health and version |

Status: placeholder – nothing built yet.
