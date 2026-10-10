# audiveris

Optional optical music recognition for Anthology, using [Audiveris](https://github.com/Audiveris/audiveris) unmodified.

- **License: AGPL-3.0** (upstream). This folder only contains the `Containerfile` and configuration to run the unmodified upstream release; Audiveris' own license applies to the image.
- Runs as its own, optional container (`audiveris`). Without it, sheet music can still be uploaded as MusicXML; recognition from PDFs is hidden.
- The Anthology core passes page images through a shared volume and reads the resulting MusicXML.

Status: placeholder – nothing built yet.
