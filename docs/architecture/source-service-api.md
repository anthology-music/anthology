# Source service interface (v1)

Contract between the Anthology core and optional source services (ADR 0017). Source services run as separate containers in the Anthology pod, are developed outside the core repository and are reached over the pod network via HTTP/JSON.

Status: draft – nothing built yet.

## Configuration

The core reads `ANTHOLOGY_SOURCE_SERVICES`, a comma-separated list of base URLs (e.g. `http://localhost:8420` in a Quadlet pod). At startup and periodically it calls `GET /v1/info` and `GET /v1/health` on each; unreachable services or unsupported interface versions are hidden from users and reported to admins.

## Services and ports

Source services live in the GitHub organisation `anthology-sources` and are published as `ghcr.io/anthology-sources/<name>`. Ports 8420–8429 are reserved for them; in a Quadlet pod they are reached via `localhost:<port>`, with Compose via `<name>:<port>`.

| Service | Port | Wraps |
|---|---|---|
| `anthology-source-streamrip` | 8420 | streamrip (Tidal first) |
| `anthology-source-ytdlp` | 8421 | yt-dlp (YouTube, YouTube Music; audio and video) |
| `anthology-source-spotdl` | 8422 | spotDL (Spotify metadata, audio via YouTube Music) |

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /v1/info` | service id, display name, interface version, capabilities (video, max quality, link patterns, needs login) |
| `POST /v1/search` | search albums, tracks, playlists, videos; paged results |
| `POST /v1/resolve` | resolve a link into items with ISRC, duration and offered quality |
| `POST /v1/download` | download items into the shared `imports` volume; returns a task ID |
| `GET /v1/tasks/{id}` | progress and result per item (also as server-sent events) |
| `GET /v1/health` | health, version, login state |

## Rules

- Services write only into the `imports` volume, never into the library.
- Credentials are stored by the core (encrypted) and passed to the service; services never return them.
- The core runs the duplicate check on `resolve` results before calling `download`.
- Breaking changes require a new version prefix (`/v2`); the core may support several versions.
- Services respect the rate limits reported by their upstream and make affected items wait instead of failing.
