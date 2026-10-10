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
| `POST /v1/tags/copy` | write a copy of a file with complete context tags (and cover) into the cache; the source is opened read-only |
| `GET /v1/health` | health and version |

Status: placeholder – nothing built yet.
