# Anthology – One Home for a Music Collection

*Six-pager · Status: proposal · Date: 2026-10-09 · Authors: The Anthology contributors*

## 1. Introduction

This document proposes Anthology, an open-source, self-hosted application that lets a household or a small community acquire, organise, listen to and work with music in one place. It explains who Anthology is for, which problems it solves, how it works, how we intend to build it, and what we do not yet know. Decisions that are already settled are recorded as architecture decision records in `docs/adr/`; the expected behaviour is specified in `openspec/specs/`. This document provides the narrative that connects them. Questions that a reader is likely to ask are answered in the appendix.

## 2. Tenets

These tenets guide decisions when goals conflict. Unless you know better ones, these are the ones we use.

1. **One integrated product beats a toolbox.** Users should not need to learn five tools to do one job; if a capability belongs to the job, it belongs in Anthology.
2. **Every recording exists once.** Storage, duplicates and metadata are managed around the recording, not around the file.
3. **The user never waits for the system.** Long work happens in the background; the screen is usable at once, even with half a million tracks.
4. **Honest quality.** What a file really contains matters more than what its format claims.
5. **Respect for creators and services.** Anthology does not bypass terms of service, rate limits or copyright, and keeps legally sensitive parts separable.
6. **Open and replaceable.** Every integration is an adapter, every copyleft component has its own boundary, and the core stays MIT-licensed.

## 3. The State of the World

People who care about music rarely rely on a single streaming subscription. They own CDs, keep folders of files collected over decades, download lossless albums, save concert recordings from video platforms, and play music in several rooms. To do this today, a capable user strings together a command-line downloader for each source, a tagging tool, a separate music server for listening, a multi-room vendor app, and a spreadsheet or memory to know what they already have. Each tool has its own view of the collection. None of them knows that the song on the deluxe album, on a compilation and in a YouTube concert video is the same recording. The result is predictable: the same music is stored three or four times, tags drift apart, and "lossless" files turn out to be converted MP3s that silently replace better copies.

A second group of users has an additional problem. Members of amateur wind bands and similar ensembles – the author plays in a Swiss *Harmoniemusik* – work with arrangements and medleys of well-known songs. The link between a medley and the originals it contains lives in printed programme notes and in the heads of the members. Sheet music is handled as loose PDFs; practising one's own part against the rest of the band means hunting for a recording. Publisher catalogues contain the needed facts – arranger, original, instrumentation, grade – but nobody connects them to the music collection.

Existing open-source projects each solve a slice well. Downloaders acquire, taggers clean, music servers stream, score viewers display notes. What is missing is the product that treats these as one workflow over one shared model of the music.

## 4. Customers

We design for two primary customers. The first is the **home collector**: a technically curious person who runs a small home server or NAS, shares it with a family, owns a collection of tens to hundreds of thousands of tracks, uses several sources, and listens on phones, laptops and multi-room speakers. Today they spend evenings managing tools instead of listening. The second is the **ensemble musician**, together with their conductor: they need to see which originals a medley contains, listen to them, read their own part on a tablet at rehearsal, and practise at home with the other parts playing. Both customers often share one installation – a family where one member plays in a band is the typical case – so Anthology supports several users with personal settings on shared and personal devices.

## 5. Goals and Non-Goals

Anthology will, first, let a user acquire music from streaming services, video platforms, CDs and existing collections through one interface, choosing per order whether to keep only the audio or the whole video. Second, it will store every recording exactly once, recognise duplicates across sources and formats, and always keep the best genuine quality. Third, it will present correct metadata for every context in which a recording appears, and let users edit tags for single files, selections or whole folders, with the number of selected items always visible. Fourth, it will play music on the device in hand or on multi-room systems in the network. Fifth, it will model works, arrangements and medleys, connect them to publishers and to sheet music, and play sheet music back while following along. Sixth, it will remain usable at any size: the current view is interactive within two seconds, for libraries of 500,000 tracks.

Anthology will not be a streaming service, will not distribute music to third parties, and will not offer public sharing of sheet music. It will not circumvent digital rights management or the terms of the services it connects to. It will not try to replace professional notation software; it reads, displays and plays sheet music, and leaves engraving to dedicated tools.

## 6. The Product

A user opens Anthology and sees two main views. **Streaming** is where music comes in. The user pastes a link or searches across the connected sources, selects audio only or video with a maximum resolution, and sends the order. Before anything is downloaded, Anthology checks every track against the library: tracks that already exist in equal or better quality are skipped, tracks that exist in worse quality are marked for replacement. The order becomes a job on the server and the user can close the app; when they return on any device, the job list shows progress, counts, the effective quality of each result and who started the job. From the same view, the desktop client imports CDs – identifying the disc, ripping it with error correction and verification, and uploading the result – and every user can import an existing collection. The import first shows a dry-run report: how many files are new, already present, better than what exists, duplicated within the collection itself, broken or of suspicious quality, and how much storage the import will use or save. Nothing is moved or copied before the user confirms, and where possible nothing is copied at all: files are referenced in place or linked on the same file system.

**Local** is where music is enjoyed and maintained. In listening mode the user browses the library, plays a track and chooses where it plays: on this device, or on a room or zone of the multi-room system, in which case the phone becomes a remote control and the music continues if it is closed. Every row shows the source as an icon at the far left and the *effective* quality as a badge. In edit mode the rows gain checkboxes; selected rows are clearly highlighted, a sticky bar shows how many items are selected, and tags can be changed for one file, a multi-selection or an entire folder. Status is shown by colour together with an icon: complete, tags missing, possible duplicate, error, suspicious quality.

**Works** connect the music to the people who play it. A medley lists its originals in order, each with a play button if it is in the library, or a button to acquire it if not. Every song shows the arrangements and medleys it appears in. Publishers can be registered; their catalogues are searched to find arrangers, originals and editions. Findings that are not confirmed by a hard identifier land in a review list with their source, confidence and the evidence from the publisher's page. Sheet music can be attached to a work, as a conductor's score or as individual parts with instrument and transposition. Anthology plays the notes at concert pitch and follows along: a score page by page, a part system by system, and for piano or accordion with both staves of a system together. In practice mode all other parts play while one's own part stays silent.

Behind all views, Anthology knows who is using it. The library is shared by everyone; bitrate, maximum video resolution, offline storage, default output and preferences belong to a user on a particular device. Every person has one account; on a shared device such as a family tablet one account is signed in at a time. Changes to shared data are recorded with user and time.

## 7. How It Works

Anthology is a server with thin clients. The **server** – Python with FastAPI – owns the library, runs all long work as background jobs, and talks to the outside world through **adapters**: source adapters acquire music, output adapters play it, publisher adapters search catalogues. New integrations are added as adapters without touching the core.

At the centre is the decision that **every recording exists once**. The original file lives in a managed store; releases and compilations reference it through track contexts in the database. Because a file can only carry one album tag, the database – not the file – is the source of truth for metadata. Clients receive context metadata from the API; downloads and streams of an original get a generated tag header for their context; transcodes are tagged during transcoding; multi-room speakers receive metadata alongside the stream. Identity comes from MusicBrainz: recordings are matched by ISRC, then by acoustic fingerprint, and only suggested by fuzzy matching. Works use MusicBrainz work IDs and ISWC, printed editions ISMN; whatever is missing gets an internal identifier. Quality is judged by what a file really contains: an analysis of the spectrum and bit depth estimates its **effective quality**, which drives ranking, replacement and transcoding.

Speed comes from **progressive loading through every layer**. The database pages by key instead of offset and keeps counters up to date. The server streams results as chunks, visible window first. Each client holds one WebSocket connection with subscriptions: it receives the total count immediately, then the rows it needs, then only changes. After a network interruption it receives only what it missed. The client starts from its local cache, scrolls virtually, shows skeleton rows for what is still loading, and expresses bulk actions as rules ("this folder") rather than lists of thousands of IDs. Audio and video travel over plain HTTP with range requests; music is transcoded on demand to the bitrate of the device, never above the quality of the original, and videos are streamed adaptively.

All clients share one **Vue and Quasar** code base: the web app and PWA, a **Tauri** desktop app that also performs CD ripping, and **Capacitor** apps for phones and tablets that can store music offline and play in the background.

Anthology is **MIT-licensed**. Components with strong copyleft licenses are kept out of the MIT code and run as separate containers with their own licenses: tag writing (based on mutagen), and the optional sheet-music recognition (Audiveris). Sources for commercial streaming services (Tidal, Spotify, YouTube) are optional source services developed in separate repositories. A PDF library under AGPL was replaced by a permissive alternative. The whole installation is one **pod** of OCI containers, documented first for rootless **Podman** with Quadlet and also runnable with Docker Compose. Optional features are enabled by adding a container, not by building a different image.

## 8. Plan

We build in an order that delivers a usable product early and lays the foundations that are expensive to change later. The **first milestone** establishes the server skeleton, the job system, user accounts with device settings, the tagging service, the pod setup and – most importantly – the WebSocket protocol with progressive loading, because every later feature depends on it. The **second milestone** delivers the core library: the single-original store, MusicBrainz identification, duplicate detection with effective quality, and the import of existing collections, followed by the Streaming and Local views with listening and editing. With this milestone a household can move its collection into Anthology. The **third milestone** adds sources and delivery: the generic source service interface with optional source services for YouTube, Spotify and Tidal (separate repositories), transcoding per device, the multi-room adapter for Teufel Raumfeld, and the native desktop and mobile apps with offline storage. The **fourth milestone** adds works, arrangements and medleys, publisher adapters including the LLM-based extractor, CD import and video. The **fifth milestone** adds sheet music in three steps: storage and playback from MusicXML, recognition from PDFs with review, and practice features. A virtual file system that presents context tags to other programs, and further multi-room systems, follow later.

Each feature enters the code base through a specification change, is implemented against its scenarios, and is verified by performance budgets in continuous integration, including a synthetic library of 500,000 tracks.

## 9. Risks and Open Questions

The largest risk is **legal exposure through sources**. Downloading from streaming services is subject to their terms; Anthology therefore keeps such sources in separate, optional components, leaves their use to the user, and limits itself to private use. Sheet music is copyrighted: in Switzerland it may be copied for the private circle but not for associations without the publisher's permission, so Anthology offers sheet music only to signed-in users of an installation, offers no external sharing, logs downloads and favours licensed digital editions; operators are responsible for the legal conditions and for who gets an account. The second risk is **license compliance**: several valuable libraries are GPL or AGPL; our separation into containers is a technical judgement that we will have reviewed by an open-source license expert before the first public release. The third risk is **dependency health**: the Raumfeld libraries and some downloaders are thinly maintained, and publishers' websites change; adapters keep the blast radius small. The fourth risk is **recognition quality**: optical music recognition and quality analysis cannot be perfect, so both report confidence and route uncertain results to people. The fifth risk is **scale and storage**: 500,000 tracks need PostgreSQL, a local MusicBrainz mirror and roughly twelve to eighteen terabytes for lossless originals. Open questions include who holds the paid Apple developer account needed to distribute the iOS app (building works without it), whether rootless Podman can discover multi-room speakers without host networking, which name variants we register on package registries, and how strongly we invest in a light theme and accessibility audits before the first release.

---

## Appendix A – Customer FAQ

**Do I have to move my existing collection?** No. Anthology can reference files where they are. If the collection is on the same file system, Anthology can link files into its store without using extra space.

**What happens to my existing tags?** They are imported and never overwritten. Differences to MusicBrainz appear as suggestions you can accept or ignore.

**Will Anthology download a song I already have?** Not if you already have it in equal or better genuine quality. If the new source is better, the old file is replaced and every album that contains the song keeps working.

**How do I know a FLAC file is really lossless?** Anthology analyses each file and shows its effective quality. Suspicious files are marked, with a spectrogram to judge them yourself.

**Can my family use it with different settings?** Yes. Everyone sees the same music; bitrate, offline music, favourites and playlists are personal, per device.

**Does it work with my multi-room speakers?** Teufel Raumfeld is supported first. Other systems can be added as output adapters.

**Can our band share sheet music with Anthology?** Each member can be given access to their own part and the conductor to the score, within your installation. Anthology has no public sharing, and you are responsible for having the rights to the sheet music you store.

**Do I need Docker?** No. Anthology runs as standard containers; Podman is the documented default, Docker works as well.

## Appendix B – Internal FAQ

**Why not build on an existing music server?** Existing servers model files, not recordings, and treat acquisition and tagging as someone else's problem. The single-original model and the works model would have to be retrofitted into their core.

**Why a WebSocket protocol instead of REST paging?** Counts first, visible rows first, deltas and resumable sessions are needed in every view; implementing them once as a protocol is cheaper than re-implementing them per screen.

**Why is the tagger a separate service?** The best tagging library is GPL-licensed. A separate service keeps the core MIT-licensed and isolates heavy file I/O.

**Why AAC for transcodes?** It plays everywhere, including Apple devices, and is good at 128 kbit/s. Opus may be added later as an option.

**Why Verovio for sheet music?** It computes page and system layout and produces MIDI and a timemap from the same source, on the server and in the browser.

**How do we keep the two-second budget?** Keyset pagination, maintained counters, chunked streaming, local caches and virtual scrolling, enforced by performance tests on a 500,000-track library in CI.

## Appendix C – Non-Functional Requirements

| Requirement | Target |
|---|---|
| Current view interactive (cold start, LAN, no cache) | ≤ 2 s (95th percentile) |
| First data from local cache | < 300 ms |
| View switch | ≤ 500 ms |
| First search results | ≤ 300 ms |
| Library size | ≥ 500,000 tracks |
| Playback start (LAN) | ≤ 500 ms |
| Bulk action on 5,000 files | acknowledged ≤ 200 ms, progress live |

## Appendix D – Glossary

**Recording** – one specific performance of a piece; the unit of deduplication. **Release / track context** – an album, EP or compilation and the position of a recording on it. **Work** – a composition independent of any recording; arrangements and medleys are works linked to their originals. **Effective quality** – the quality a file really contains, as opposed to what its format declares. **Score / part** – the conductor's full sheet music versus the music for one instrument. **System** – what is read at once; for piano or accordion several braced staves. **Adapter** – a plug-in implementing a source, output or publisher integration. **Pod** – a group of containers that run together and share a local network.

## Appendix E – Decision Records

| ADR | Decision |
|---|---|
| 0001 | Monorepo for server and all clients |
| 0002 | Tauri for the desktop client |
| 0003 | Progressive loading over one WebSocket per client |
| 0004 | MIT license; copyleft components kept separate |
| 0005 | One pod, one container per license boundary – Podman first |
| 0006 | Python with FastAPI for the server |
| 0007 | Vue 3 with Quasar for all clients |
| 0008 | One original per recording, metadata from the database by context |
| 0009 | MusicBrainz as the identity backbone |
| 0010 | PostgreSQL in production, SQLite for development |
| 0011 | Adapters for sources, outputs and publishers |
| 0012 | Effective quality instead of declared quality |
| 0013 | AAC as the transcoding format |
| 0014 | Verovio as the sheet-music engine |
| 0015 | Local user accounts with device registration |
| 0016 | HLS for video playback |
