# Installation

Anthology runs as one pod: `anthology-server` (MIT, API and web client, the only published port), `anthology-tagger` (GPL-2.0-or-later) and PostgreSQL; optional services are added as further containers (ADR 0005). Images are published for `linux/amd64` and `linux/arm64`:

| Image | Tags |
|---|---|
| `ghcr.io/anthology-music/anthology-server` | `latest` and `X.Y.Z` / `X.Y` for releases, `edge` and `sha-<commit>` for the current `main` |
| `ghcr.io/anthology-music/anthology-tagger` | same |

After the start, open `http://<host>:8400` and create the first account – it becomes the administrator.

## Podman with Quadlet (recommended)

Requires **Podman 5.0 or later** (`.pod` units) and a systemd user session. Rootless:

```
mkdir -p ~/.config/containers/systemd
cp deploy/quadlet/* ~/.config/containers/systemd/
openssl rand -base64 32 | podman secret create anthology-db-password -
systemctl --user daemon-reload
systemctl --user start anthology-pod
```

To keep it running without an open login session: `loginctl enable-linger $USER`. Optional services live in `deploy/quadlet-optional/`; copy a unit from there only when you want it (sheet-music recognition, `anthology-audiveris.container`, needs an image that follows in a later milestone).

Check the installation (also used by CI): `deploy/smoke-test.sh http://localhost:8400`.

## Docker (or Podman) with Compose

```
cd deploy
mkdir -p secrets && openssl rand -base64 32 > secrets/db_password
docker compose up -d
```

`deploy/secrets/` is git-ignored; keep the file private (`chmod 600`). With Podman: `podman compose up -d`.

## Data

| Volume | Mounted at | Content | Backup |
|---|---|---|---|
| `anthology-library` | `/data/library` | originals (music library) | yes |
| `anthology-db` | PostgreSQL | database | yes (`pg_dump`) |
| `anthology-keys` | `/data/keys` (server) | signing keys of sign-ins and media URLs; losing them signs out all devices | yes |
| `anthology-imports` | `/data/imports` | incoming files (sources, CD, uploads) | optional |
| `anthology-video` | `/data/video` | videos | yes |
| `anthology-cache` | `/data/cache` | transcodes, tagged copies, thumbnails – can be deleted | no |

An existing collection on the host can be used instead of the library volume: replace `anthology-library.volume:/data/library:U` by a bind mount (`Volume=/srv/music:/data/library:Z` with SELinux) in the server and tagger units – both need the same path.

## Database password

The password is a secret, never part of a unit file or environment variable: PostgreSQL reads it from `POSTGRES_PASSWORD_FILE`, the server from `ANTHOLOGY_DATABASE_PASSWORD_FILE` (it replaces the password in `ANTHOLOGY_DATABASE_URL`). PostgreSQL uses the secret only when it creates the database; to change it later, change it in PostgreSQL (`ALTER USER anthology PASSWORD …`) and in the secret.

## Metadata lookups

Anthology identifies music with MusicBrainz (at most one request per second, cached). Set `ANTHOLOGY_MUSICBRAINZ_CONTACT` to your e-mail address or a URL; MusicBrainz asks every application to name a contact in its User-Agent. For fingerprint lookups, register an application at [AcoustID](https://acoustid.org/new-application) and set `ANTHOLOGY_ACOUSTID_API_KEY`. For large collections, a local MusicBrainz mirror removes the rate limit: `docs/architecture/musicbrainz-mirror.md`.

## HTTPS and remote access

The server speaks plain HTTP on port 8400. For access beyond the local network, put a reverse proxy with TLS in front (e.g. Caddy, Traefik, nginx) and forward WebSocket upgrades for `/api/v1/ws`. The server trusts `X-Forwarded-*` headers from `127.0.0.1` only; if the proxy reaches it from another address, set `FORWARDED_ALLOW_IPS` to that address in the server unit.

## Updates

Quadlet: `podman auto-update` works if you add `AutoUpdate=registry` to the container units; otherwise `podman pull` the images and `systemctl --user restart anthology-pod`. Compose: `docker compose pull && docker compose up -d`. Database migrations run automatically when the server starts.
