# Installation

Anthology runs as one pod: `anthology-server` (MIT, API and web client, the only published port), `anthology-tagger` (GPL-2.0-or-later) and PostgreSQL; optional services are added as further containers (ADR 0005). Images are published for `linux/amd64` and `linux/arm64`:

| Image | Tags |
|---|---|
| `ghcr.io/anthology-music/anthology-server` | `X.Y.Z` and `X.Y` for releases, `latest` for the newest release, `edge` and `sha-<commit>` for the current `main` |
| `ghcr.io/anthology-music/anthology-tagger` | same |

The images are OCI images and work with Docker and Podman alike. While Anthology is below 1.0, every release is a pre-release and `latest` follows it; to stay on one version, use its tag (`:0.1.0`) instead of `latest`.

## Installation packages

Every [release](https://github.com/anthology-music/anthology/releases) offers two packages with the images pinned to that release:

| Package | For |
|---|---|
| `anthology-X.Y.Z-compose.tar.gz` | Docker Compose or Podman Compose (`compose.yaml`) |
| `anthology-X.Y.Z-quadlet.tar.gz` | Podman Quadlet (rootless systemd units) |

Unpack one and follow its `README.md`; it contains the same files as `deploy/` below, with fixed image tags. The user manual (installation, administration, usage) is published at <https://anthology-music.github.io/anthology/>.

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

## Importing a collection

Admins import server folders from the Streaming page ("Import folder"). Only folders below the import roots can be chosen: `ANTHOLOGY_IMPORT_ROOTS` (comma-separated, default `/data/imports`). Paths that leave a root through `..` or symbolic links are refused.

The import proposes the most economical storage mode the mounts allow:

| Mode | Originals | Needs |
|---|---|---|
| reference | referenced: files stay where they are, Anthology never moves, renames or deletes them | – |
| link (reflink) | managed: a copy-on-write clone in `/data/library/_originals`, no additional space | a file system with reflinks (Btrfs, XFS) and the folder on the same mount as `/data/library` |
| link (hardlink) | referenced: a second name for the same file in `/data/library/_originals` | the folder on the same mount as `/data/library` |
| move | managed: moved into `/data/library/_originals` (across mounts: copied, verified by checksum, then removed at the source) | – |
| copy | managed: copied and verified by checksum; the source stays unchanged | space for a second copy |

In the standard pod `anthology-imports` and `anthology-library` are separate volumes, so linking is not possible and "copy" is proposed. Hardlinks and reflinks need source and target in **one mount**: Linux refuses them across mount points, even on the same disk. To link an existing collection, bind-mount a host folder that contains it as the library and make the collection an import root, e.g. with the collection in `/srv/music/Collection`: `Volume=/srv/music:/data/library:Z` in the server and tagger units (instead of the library volume) and `Environment=ANTHOLOGY_IMPORT_ROOTS=/data/imports,/data/library/Collection` (Compose: `- /srv/music:/data/library` and `ANTHOLOGY_IMPORT_ROOTS: /data/imports,/data/library/Collection`). Anthology then writes its managed originals to `/srv/music/_originals` and leaves the collection folder as it is.

Referenced files can later be adopted into managed storage in Settings › Library (move, copy or reflink; each file is verified by checksum before anything changes at the source).

## Time zone and system maintenance

Schedules run in the installation's time zone: set `ANTHOLOGY_TIME_ZONE` to an IANA name such as `Europe/Berlin` (default `UTC`).

The system maintenance (Settings › Systempflege, admins) runs daily at 03:00 by default. It deletes orphaned files and leftovers of interrupted transfers in `/data/library/_originals` that are older than the grace period (24 hours), and lists managed originals whose file is missing; referenced files outside `_originals` are never touched. If a run would delete more than the safety limit (1 % of the managed files, at least 10), it deletes nothing and waits for an admin's confirmation. This protects against a database restored from an older backup or a wrong library mount, where the newer originals would look orphaned: after a restore, check the next result before you confirm a deletion.

## Database password

The password is a secret, never part of a unit file or environment variable: PostgreSQL reads it from `POSTGRES_PASSWORD_FILE`, the server from `ANTHOLOGY_DATABASE_PASSWORD_FILE` (it replaces the password in `ANTHOLOGY_DATABASE_URL`). PostgreSQL uses the secret only when it creates the database; to change it later, change it in PostgreSQL (`ALTER USER anthology PASSWORD …`) and in the secret.

## Source services

Streaming sources (Tidal, Spotify, YouTube) are optional source services from the GitHub organisation `anthology-sources` (ADR 0017), each its own container in the pod with the imports volume mounted at `/data/imports`. List their URLs in `ANTHOLOGY_SOURCE_SERVICES`, comma-separated (Quadlet pod: `http://localhost:8420,http://localhost:8421`; Compose: `http://anthology-source-streamrip:8420`). The server checks them every minute; unavailable ones are left out of the Streaming view, and its "Source status" says why. Services that need a login ask for it in Settings › Sources (admins); the values are stored encrypted with the key `sources.key` in the keys volume and are never shown again.

## Raumfeld speakers

Anthology plays on Teufel Raumfeld zones (output picker in the player bar). It needs two things:

- **Finding the Raumfeld host:**
  - With host networking (`Network=host` in `anthology.pod`, `network_mode: host` in Compose), the server finds the host by SSDP multicast.
  - In a rootless pod without host networking, multicast does not reach the server. An admin enters the host's address in Settings › Outputs (the IP address of the Raumfeld base or the speaker that serves as host), or the installation sets `ANTHOLOGY_RAUMFELD_HOSTS` (comma-separated, `host` or `host:47365`).
  - `ANTHOLOGY_OUTPUT_DISCOVERY=false` turns the search off.
- **Speakers reaching the server:**
  - The speakers fetch the music from the server over HTTP. Set `ANTHOLOGY_OUTPUT_MEDIA_URL` to the server's address as the speakers see it, e.g. `http://192.168.1.10:8400`.
  - Without it, the server uses its own address on the route to the speakers and port 8400 (`ANTHOLOGY_PORT`). Behind the pod's port forwarding that address is the container's, so set the URL there.

The server's ports are not opened to the internet for this: speakers and server are in the same local network. Protocol details: `docs/architecture/raumfeld.md`.

## Metadata lookups

Anthology identifies music with MusicBrainz (at most one request per second, cached). Set `ANTHOLOGY_MUSICBRAINZ_CONTACT` to your e-mail address or a URL; MusicBrainz asks every application to name a contact in its User-Agent. For fingerprint lookups, register an application at [AcoustID](https://acoustid.org/new-application) and set `ANTHOLOGY_ACOUSTID_API_KEY`. For large collections, a local MusicBrainz mirror removes the rate limit: `docs/architecture/musicbrainz-mirror.md`.

## HTTPS and remote access

The server speaks plain HTTP on port 8400. For access beyond the local network, put a reverse proxy with TLS in front (e.g. Caddy, Traefik, nginx) and forward WebSocket upgrades for `/api/v1/ws`. The server trusts `X-Forwarded-*` headers from `127.0.0.1` only; if the proxy reaches it from another address, set `FORWARDED_ALLOW_IPS` to that address in the server unit.

## Updates

Read the [changelog](../CHANGELOG.md) of the new version first, and back up the database and the library volume.

- **Pinned version** (an installation package, or `:X.Y.Z` in the units): change the tags to the new version, or unpack the new release's package over the old files, then restart (`systemctl --user daemon-reload && systemctl --user restart anthology-pod`, or `docker compose up -d`).
- **`latest`:** Quadlet: `podman auto-update` works if you add `AutoUpdate=registry` to the container units; otherwise `podman pull` the images and `systemctl --user restart anthology-pod`. Compose: `docker compose pull && docker compose up -d`.

Database migrations run automatically when the server starts. Settings › About Anthology shows the running version.
