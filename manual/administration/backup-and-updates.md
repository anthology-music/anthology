# Backups and updates

## What to back up

| Data | How |
|---|---|
| the database | `pg_dump` of the `anthology` database, e.g. daily |
| the library volume (`/data/library`) | file backup; it holds the managed originals and the cover images |
| the keys volume (`/data/keys`) | file backup; without it every device must sign in again |
| referenced folders | your own backup – Anthology never changes them |

The cache volume (`/data/cache`) can be rebuilt and needs no backup.

After restoring an older backup, check the next result of the system maintenance before you confirm a deletion (see [Maintenance](./maintenance)).

## Updating

Read the [changelog](https://github.com/anthology-music/anthology/blob/main/CHANGELOG.md) of the new version and make a backup first.

- **Pinned version** (an installation package or `:X.Y.Z`): change the tags to the new version, or unpack the new release's package over the old files, then restart (`systemctl --user daemon-reload && systemctl --user restart anthology-pod`, or `docker compose up -d`).
- **`latest`:** with Quadlet, `podman pull` the images and `systemctl --user restart anthology-pod` (or use `podman auto-update` with `AutoUpdate=registry`); with Compose, `docker compose pull && docker compose up -d`.

Database migrations run automatically when the server starts. **Settings › About Anthology** shows the running version.
