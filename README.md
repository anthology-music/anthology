# Anthology

Open-source, self-hosted music application: acquire music, listen to it on any device or across rooms, edit tags, link works, arrangements and medleys, and follow sheet music – in one integrated app.

> Status: concept and specifications. No release yet.

## Highlights

- One original per recording – albums and compilations only reference it.
- Sources: CD, existing collections, upload; Tidal, Spotify and YouTube through optional source services (separate repositories); audio only or video.
- Multi-room playback (Teufel Raumfeld first) through output adapters.
- Works, arrangements and medleys with publishers and sheet music (score and parts).
- Effective-quality detection of upscaled files.
- Multi-user: shared library, personal settings per user and device.
- Instant UI through progressive loading; built for 500,000 tracks.

## Repository

| Path | Content |
|---|---|
| `openspec/specs/` | Specifications – the source of truth |
| `openspec/changes/` | Proposed and archived changes |
| `server/` | Python / FastAPI server (MIT) |
| `services/` | Separately licensed containers (tagger, Tidal source, Audiveris) |
| `deploy/` | Podman Quadlet files and Compose file |
| `client/` | Vue 3 + Quasar client (web, Tauri desktop, Capacitor mobile) |
| `packages/` | Shared packages (generated API types) |
| `docs/` | Six-pager, architecture, ADRs (decisions), design (UI reference) |

## Development

This project is developed spec-driven with [OpenSpec](https://github.com/Fission-AI/OpenSpec) and AI coding agents (Claude Code, opencode). Agent rules: `AGENTS.md`.

```
npm install -g @fission-ai/openspec@latest
openspec init        # select Claude Code and OpenCode
openspec list
```

## Running (planned)

Anthology runs as one pod of OCI containers. **Podman is the primary platform** (rootless, managed by Quadlet); Docker works via Compose.

| Container | License | Required |
|---|---|---|
| `anthology-server` | MIT | yes |
| `anthology-tagger` | GPL-2.0-or-later | yes |
| `postgres` | PostgreSQL | yes |
| `anthology-source-tidal` / `-spotify` / `-youtube` | GPL-3.0-only / MIT / MIT | optional, separate repositories |
| `audiveris` | AGPL-3.0 | optional |

```
# Podman with Quadlet (recommended)
cp deploy/quadlet/* ~/.config/containers/systemd/
systemctl --user daemon-reload && systemctl --user start anthology-pod

# Podman or Docker with Compose
podman compose -f deploy/compose.yaml up -d
```

## Sheet music and your responsibility

All signed-in users of an installation can see and play all stored sheet music (scores and parts); there is no public sharing. As an operator you are responsible for the legal conditions of the sheet music you store (e.g. licences from publishers) and must restrict who gets an account accordingly.

## License

MIT – see [`LICENSE`](LICENSE). Components with copyleft licenses run in their own containers under `services/` with their own licenses – see `docs/adr/0004-license.md` and `docs/adr/0005-containers-podman.md`.
