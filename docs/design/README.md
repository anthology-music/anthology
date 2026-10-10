# Design reference

UI mockups and design tokens for the Anthology client. They are the **visual reference** for implementing the Vue/Quasar client; behavior is defined by the specs in `openspec/specs/`.

## Contents

| Path | Content |
|---|---|
| `mockups/index.html` | Overview with links to all screens |
| `mockups/*.html` | Static HTML export of each screen (initial state, no interactions) |
| `tokens.css` | Design tokens: colors, typography, spacing, radii |

## Screens

| File | Screen | Device |
|---|---|---|
| `Main.html` | Streaming – acquire music, jobs, audio/video toggle, CD entry | Desktop |
| `Lokal-Hoeren.html` | Local – listen (album, skeleton loading, output picker with Raumfeld zones) | Desktop |
| `Lokal-Editieren.html` | Local – edit mode (selection, count, status colors, tag editor) | Desktop |
| `Einstellungen.html` | Settings – this device and my account | Desktop |
| `Einstellungen-Server.html` | Settings – server (admin): users, publishers, library, sources | Desktop |
| `Werk.html` | Work – medley with originals, recordings, review list | Desktop |
| `CD-Import.html` | CD import (desktop client) | Desktop |
| `Mobile-Streaming.html` | Streaming | Phone |
| `Mobile-Hoeren.html` | Local – listen with mini player | Phone |
| `Mobile-Editieren.html` | Local – edit mode with action bar | Phone |
| `Mobile-Einstellungen.html` | Settings with user/device context | Phone |
| `Mobile-Profil.html` | Profile picker with PIN (shared device) | Phone |

UI texts in the mockups are German (the first UI language); in the client they come from i18n files.

## Not yet designed

Sheet-music viewer (page mode, system mode, braced staves) and recognition review, video player, library-import wizard with dry-run report, quality detail with spectrogram, review-list overview, sign-in, works list, mobile versions of work, sheet music and import, light theme.

## Rules for implementing from the mockups

- Use the tokens from `tokens.css`; do not copy hex values from the HTML.
- Rebuild screens with Quasar components and the client's shared components; the mockups' inline styles are a reference, not code to paste.
- Keep: source icon at the far left of rows, effective-quality badge, status color **plus** icon/label, distinct selection background, sticky action bar with selection count, skeleton rows, connection state, touch targets ≥ 44 px.
- Placeholder names in square brackets (e.g. `[Verlag A]`, `[Arrangeur]`) are intentional; artist and album names are fictional.

## Source

The mockups were designed on a design canvas and exported to static HTML. Interactive behavior shown on the canvas (selection in edit mode) is described in the specs, not in the export.
