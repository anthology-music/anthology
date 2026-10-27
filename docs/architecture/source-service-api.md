# Source service interface (v1)

Contract between the Anthology core and optional source services (ADR 0017). Source services run as separate containers in the Anthology pod, are developed outside the core repository and are reached over the pod network via HTTP/JSON. The core repository contains a reference implementation for tests, `tools/fake-source-service/`, which speaks every endpoint below.

Status: v1, implemented by the core (change `source-service-adapter`).

## Configuration

The core reads `ANTHOLOGY_SOURCE_SERVICES`, a comma-separated list of base URLs (e.g. `http://localhost:8420` in a Quadlet pod). At startup and then every 60 seconds (every 10 seconds while a service is unavailable) it calls `GET /v1/info` and `GET /v1/health` on each. Unreachable services, services with another interface version and services whose login failed are unavailable: they are left out of search and orders, and every user can see the reason in the source status view.

## Services and ports

Source services live in the GitHub organisation `anthology-sources` and are published as `ghcr.io/anthology-sources/<name>`. Ports 8420–8429 are reserved for them (8429: the fake service of the end-to-end tests); in a Quadlet pod they are reached via `localhost:<port>`, with Compose via `<name>:<port>`.

| Service | Port | Wraps |
|---|---|---|
| `anthology-source-streamrip` | 8420 | streamrip (Tidal first) |
| `anthology-source-ytdlp` | 8421 | yt-dlp (YouTube, YouTube Music; audio and video) |
| `anthology-source-spotdl` | 8422 | spotDL (Spotify metadata, audio via YouTube Music) |

## Common rules

- Requests and answers are JSON (`Content-Type: application/json`). Unknown fields are ignored on both sides, so a service may add fields; removing or changing a field needs `/v2`.
- Errors answer with an HTTP status ≥ 400 and `{"error": "<code>", "message": "<text>"}`. Codes: `not_found` (unknown ref or task), `unsupported_link`, `login_required`, `login_failed`, `rate_limited` (with `retry_after` in seconds), `invalid_request`, `upstream_failed`.
- Qualities are named `best`, `flac_hires`, `flac_cd`, `aac_320`, `mp3_320`, `aac_256`, `opus_160`, `aac_128`.
- An **offered quality** describes what a download would deliver: `format` (`flac`, `alac`, `aac`, `mp3`, `opus`, `vorbis`, `wav`), `lossless` (boolean), `bitrate_kbps` (lossy, else `null`), `sample_rate_hz`, `bit_depth` (lossless, else `null`).
- Times are ISO 8601 with time zone.

## Endpoints

### `GET /v1/info`

```json
{
  "id": "streamrip",
  "name": "Tidal",
  "interface": 1,
  "version": "1.4.2",
  "source": "tidal",
  "short": "TD",
  "capabilities": {
    "search": true,
    "video": false,
    "link_patterns": ["^https://(listen\\.)?tidal\\.com/(browse/)?(album|track|playlist)/"],
    "qualities": ["best", "flac_hires", "flac_cd", "aac_320"]
  },
  "login": {"fields": [{"name": "username", "label": "Benutzername", "secret": false},
                       {"name": "password", "label": "Passwort", "secret": true}]}
}
```

`id` identifies the service in the core (stable across versions). `source` is stored with every acquired file and shown to users with `short` (two letters for the source icon). `interface` is the interface version (1). `login` is `null` for services without login.

### `GET /v1/health`

```json
{"ok": true, "version": "1.4.2", "logged_in": true, "rate_limited_until": null, "message": null}
```

`logged_in` is `null` for services without login. While `logged_in` is `false`, the core sends the stored login fields again (`POST /v1/login`).

### `POST /v1/login`

Request `{"fields": {"username": "…", "password": "…"}}`; answer `{"logged_in": true, "message": null}`. The service keeps the session itself; it never returns the fields. A wrong login answers `401` with `login_failed`.

### `POST /v1/search`

Request `{"query": "Polarnacht", "kinds": ["album", "track", "playlist"], "page": 1, "page_size": 20}`; answer:

```json
{"results": [{"ref": "album:41", "kind": "album", "title": "Polarnacht", "artist": "Nordlicht",
              "album": null, "year": 2024, "track_count": 10,
              "offered": {"format": "flac", "lossless": true, "bitrate_kbps": null,
                          "sample_rate_hz": 44100, "bit_depth": 16},
              "url": "https://fake.example/album/41"}],
 "next_page": 2}
```

`ref` is opaque to the core and passed back unchanged. `next_page` is `null` on the last page.

### `POST /v1/resolve`

Request `{"url": "https://…"}` or `{"ref": "album:41"}`; answer `{"item": <a search result>, "tracks": [<track>]}` with tracks in their order:

```json
{"ref": "track:410", "title": "Eisfeld", "artist": "Nordlicht", "album": "Polarnacht",
 "album_artist": "Nordlicht", "disc_number": 1, "track_number": 1, "duration_ms": 214000,
 "isrc": "DEA012400001", "offered": {"format": "flac", "lossless": true, "bitrate_kbps": null,
                                     "sample_rate_hz": 44100, "bit_depth": 16}}
```

A link the service does not handle answers `422` with `unsupported_link`.

### `POST /v1/download`

Request `{"tracks": ["track:410", "track:411"], "quality": "best", "target": "/data/imports/anthology-downloads/<order>"}`; answer `{"task_id": "…"}` (`202`). The service writes one file per track below `target` (a folder in the shared imports volume, created by the service), with the track's tags, and never writes anywhere else.

### `GET /v1/tasks/{id}`

```json
{"state": "running", "waiting_until": null,
 "items": [{"ref": "track:410", "state": "done", "progress": 1.0,
            "file": "01 Eisfeld.flac", "message": null},
           {"ref": "track:411", "state": "running", "progress": 0.4, "file": null,
            "message": null}]}
```

Task `state`: `running`, `waiting` (rate-limited until `waiting_until`), `done`, `failed`. Item `state`: `queued`, `running`, `waiting`, `done`, `failed`; `file` is relative to `target` once the item is done. Services keep a task at least an hour after it ended.

## Rules

- Services write only into the `imports` volume, never into the library.
- Credentials are stored by the core (encrypted) and passed to the service with `login`; services never return them.
- The core runs the duplicate check on `resolve` results before calling `download`.
- Services respect the rate limits reported by their upstream: affected items and tasks wait (`waiting`) instead of failing.
