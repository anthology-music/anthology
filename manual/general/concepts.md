# Concepts

A few ideas run through all of Anthology. Knowing them makes the rest of the manual easier to follow.

## Recordings, releases and tracks

- A **recording** is one performance of a piece of music – the audio itself.
- A **release** (album) is a published collection of tracks.
- A **track** is a recording in the context of a release: its number, its disc, and possibly a title or artist that differs on that album.

The same recording often appears on several releases – the original album, a compilation, a remaster. Anthology keeps **one original file per recording** and lets every release reference it. When you play a track from a compilation, Anthology shows and delivers it with the compilation's tags and cover.

## Managed and referenced originals

- **Managed** originals belong to Anthology: they live in the library volume, and Anthology may move them or replace them with a better copy.
- **Referenced** originals stay in a folder you own. Anthology reads them and never moves, renames or deletes them; it writes their tags only if you allow it.

## Effective quality

The quality a file declares (for example "FLAC, 24 bit") is not always the quality it has: a lossless file can contain upscaled lossy audio. Anthology analyses the audio and shows the **effective quality** as a badge. It uses the effective quality to rank duplicates, to decide replacements and to choose transcodes – and never upscales.

## Jobs

Long work – imports, identification, quality analysis, bulk edits, downloads – runs as a **job** on the server. Jobs show their progress live, can be paused and continue after a restart.

## The review list and conflicts

When Anthology is not sure – two recordings that may be the same, a MusicBrainz suggestion, a better copy of a file – it asks in the **review list**. When an automatic source (such as MusicBrainz) would change a value someone set by hand, the change becomes a **conflict** that you accept or reject.

## Outputs

Music plays on **this device** (the browser) or on an **output** such as a Raumfeld zone. On an output, the server plays the queue track by track, and your device becomes a remote control.
