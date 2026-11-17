# Works

A **work** is a piece of music independent of any recording: a song, an arrangement of it for wind band, or a medley of several songs. **Works** in the main navigation lists them, with the number of works of each kind at the top.

<Screenshot name="works" alt="The works list with its kinds" />

## Kinds of works

| Kind | Example |
|---|---|
| Original | a song or a piece as it was written |
| Arrangement | the song arranged for wind band |
| Medley | several originals in one piece, in order |
| Adaptation | another version, e.g. a new text |

Each work has its **credits** – composers, lyricists and arrangers –, and may have an instrumentation, a grade, a duration and an ISWC.

## The work page

<Screenshot name="work" alt="A medley with its originals and recordings" />

- **Originals** lists what a medley or an arrangement contains, in order, with how many of them are in the library. An original in the library has a play button; **Play originals** plays all of them. An original that is missing has **Acquire**: it opens Streaming with the source search filled in, and you decide what to order.
- **Recordings of this work** lists the tracks of the work – from albums, or your band's own concert and rehearsal recordings.
- **Contained in** lists the medleys and arrangements a work appears in.
- The heart marks the work as a favorite; **Search in this work** searches its recordings.

The **⋮** menu of a track and the player show the works of the playing recording.

## Works from MusicBrainz

When Anthology identifies a recording with MusicBrainz, it also fetches the recording's works with their composers and ISWC and links them – in the background, without any action. It does so once for the existing library and checks again monthly. A medley performance is linked to every work it contains.

Changes you make win: a title you correct stays, and a link or credit you remove is not added again.

## Editing works

Editors and admins create works with **New work**, and change them with **Edit work**.

<Screenshot name="work-editor" alt="The dialog to edit a work and its credits" />

- **Credits:** pick an existing person, or type a new name to create one.
- **Originals:** **Add original** finds a work by searching; the arrows change the order.
- **Recordings:** **Link a recording** finds a track by searching; the link icon removes it.
- **Delete work** removes the work with its credits and links; the recordings stay in the library.

A work cannot contain itself, directly or through another medley; Anthology refuses such a change.

## Persons

**Persons** lists the composers, lyricists and arrangers; a person's page shows their works by role. Editors can rename a person, and **merge** two spellings of the same person ("J. de Haan" and "Jacob de Haan") into one. Persons that MusicBrainz knows as different artists are not merged.

## Searching works

Works appear in the search with their own group. Filters for works:

| Filter | Example | Finds |
|---|---|---|
| `work:` | `work:"Nordlicht-Medley"` | the work and the tracks of its recordings |
| `arranger:` | `arranger:"de Haan"` | works by arranger |
| `grade:` | `grade:3` | works by grade |
| `composer:` | `composer:Nord` | tracks and works by composer |
