# Configuration

The server is configured with environment variables starting with `ANTHOLOGY_`. In the Quadlet files they are `Environment=` lines of `anthology-server.container`; in Compose they are under `environment:` of `anthology-server`.

## Important settings

| Variable | Default | Meaning |
|---|---|---|
| `ANTHOLOGY_DATABASE_URL` | set by the pod | PostgreSQL connection; the password comes from `ANTHOLOGY_DATABASE_PASSWORD_FILE` |
| `ANTHOLOGY_TIME_ZONE` | `UTC` | time zone of schedules, e.g. `Europe/Zurich` |
| `ANTHOLOGY_IMPORT_ROOTS` | `/data/imports` | folders admins may import from, comma-separated |
| `ANTHOLOGY_MUSICBRAINZ_CONTACT` | – | your e-mail or URL, sent to MusicBrainz as the required contact |
| `ANTHOLOGY_ACOUSTID_API_KEY` | – | enables fingerprint lookups at AcoustID |
| `ANTHOLOGY_MUSICBRAINZ_URL` | – | a local MusicBrainz mirror (no rate limit) |
| `ANTHOLOGY_SOURCE_SERVICES` | – | URLs of source services, comma-separated |
| `ANTHOLOGY_RAUMFELD_HOSTS` | – | Raumfeld host addresses when discovery cannot find them |
| `ANTHOLOGY_OUTPUT_MEDIA_URL` | – | the server's address as the speakers see it |
| `ANTHOLOGY_TRANSCODE_CACHE_GB` | `20` | size of the transcode cache |
| `ANTHOLOGY_THUMBNAIL_CACHE_MB` | `512` | size of the cover thumbnails |
| `ANTHOLOGY_JOBS_THROTTLE` | `normal` | background jobs at once: `gentle`, `normal`, `fast` |

## Data volumes

| Volume | Mounted at | Content | Back up |
|---|---|---|---|
| `anthology-library` | `/data/library` | your music (originals) and the cover images | yes |
| `anthology-db` | PostgreSQL | the database | yes (`pg_dump`) |
| `anthology-keys` | `/data/keys` | signing keys; losing them signs out every device | yes |
| `anthology-imports` | `/data/imports` | incoming files | optional |
| `anthology-cache` | `/data/cache` | transcodes, tagged copies, thumbnails | no |

An existing collection can replace the library volume with a bind mount of a host folder (`Volume=/srv/music:/data/library:Z`); the server and the tagger need the same path.

## HTTPS and access from outside

The server speaks plain HTTP on port 8400. For access beyond your network, put a reverse proxy with TLS in front (for example Caddy, Traefik or nginx) and forward WebSocket upgrades for `/api/v1/ws`. The server trusts `X-Forwarded-*` headers from `127.0.0.1` only; set `FORWARDED_ALLOW_IPS` to the proxy's address if it runs elsewhere.
