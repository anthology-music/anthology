# Installation

Anthology runs as one pod of containers. Every part is an OCI image and works with **Podman** and **Docker** alike:

| Container | License | Required |
|---|---|---|
| `anthology-server` – API and web app, the only published port (8400) | MIT | yes |
| `anthology-tagger` – reads and writes tags | GPL-2.0-or-later | yes |
| `postgres` – the database | PostgreSQL | yes |
| source services (separate repositories) | their own | optional |

Images are published on ghcr.io for `linux/amd64` and `linux/arm64`: `ghcr.io/anthology-music/anthology-server` and `ghcr.io/anthology-music/anthology-tagger`, tagged with the version (`0.1.0`, `0.1`) and `latest`.

## Requirements

- A Linux host with **Podman 5** or later (recommended, rootless with systemd) or **Docker** with Compose.
- 2 GB of memory for a small library; PostgreSQL and the library grow with your collection.
- Disk space for your music: lossless originals of 500,000 tracks need about 12 to 18 TB.

## Installation packages

Each [release](https://github.com/anthology-music/anthology/releases) offers two packages with the images pinned to that release. Unpack one and follow its `README.md`:

- `anthology-<version>-compose.tar.gz` – for Docker Compose or Podman Compose;
- `anthology-<version>-quadlet.tar.gz` – for Podman Quadlet.

## Podman with Quadlet (recommended)

Quadlet turns the unit files into systemd services, so the pod starts with your user session and restarts when something fails.

```sh
mkdir -p ~/.config/containers/systemd
cp *.pod *.container *.volume ~/.config/containers/systemd/
openssl rand -base64 32 | podman secret create anthology-db-password -
systemctl --user daemon-reload
systemctl --user start anthology-pod
```

To keep the pod running without an open login session: `loginctl enable-linger $USER`.

## Docker or Podman with Compose

```sh
mkdir -p secrets && chmod 700 secrets && openssl rand -base64 32 > secrets/db_password
docker compose up -d        # or: podman compose up -d
```

The `secrets` folder is private (`chmod 700`). Leave the file itself readable: the server and PostgreSQL read it as non-root users inside their containers, so `chmod 600` on the file stops them from starting.

## Check the installation

Open `http://<host>:8400`. A fresh installation opens the setup, where you create the first account – see [First steps](./first-steps). The server reports its state at `/api/v1/health` and `/api/v1/ready`.

## Versions

While Anthology is below 1.0, every release is a pre-release and `latest` follows it. To stay on one version, use its tag (`:0.1.0`) or an installation package. Settings › About Anthology shows the running version.
