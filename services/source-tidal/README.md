# anthology-source-tidal

Optional Tidal source for Anthology, based on [streamrip](https://github.com/nathom/streamrip).

- **License: GPL-3.0-only** (see `LICENSE`) – because it uses streamrip. The Anthology core (MIT) does not import this code; it calls the service through its interface and reads finished files from a shared volume.
- Runs as its own, **optional** container (`anthology-source-tidal`). Without it, Anthology works normally and the Tidal source is hidden.
- Users are responsible for using it in line with Tidal's terms of service.

## Interface (draft, versioned)

| Endpoint | Purpose |
|---|---|
| `POST /v1/search` | search albums, tracks, playlists |
| `POST /v1/resolve` | resolve a Tidal link into tracks with ISRC and available quality |
| `POST /v1/download` | download tracks into the shared `imports` volume; returns a task ID |
| `GET /v1/tasks/{id}` | progress and result (also as server-sent events) |
| `GET /v1/health` | health, version, login state |

Status: placeholder – nothing built yet.
