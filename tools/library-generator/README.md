# anthology-library-generator

Deterministic test libraries for Anthology: artists, releases, recordings, track contexts and
audio-file descriptions with fictional names and no media files (spec: library, Test library
generator). MIT-licensed like the repository (see `LICENSE` in the repository root).

```python
from anthology_library_generator import generate

for batch in generate(tracks=500_000):
    ...  # batch.artists (new ones), batch.release, batch.recordings (new ones)
```

The same `tracks` and `seed` always produce the same library. The server seeds a development
database with it: `ANTHOLOGY_DEV_DEMO=true uv run anthology dev seed-library --tracks 500000`.

Tests: `uv run pytest` in this folder.
