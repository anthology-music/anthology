# Review and conflicts

Anthology decides on its own only when it is certain. Everything else waits for an editor or admin in the **Review list** or among the **Conflicts**. Only the decision changes the library.

## Review list

<Screenshot name="review" alt="The review list with an open entry" />

The review list collects uncertain results:

| Kind | Question | Answers |
|---|---|---|
| Same recording? | are two recordings the same? | merge, or keep separate |
| MusicBrainz suggestion | does a MusicBrainz recording match? | assign the ID, or reject |
| Different title | does an imported file belong to a recording despite its title? | same recording, or own recording |
| Inconclusive quality comparison | should a new file replace the original? | use as original, or keep the original |
| Quality finding | is a file genuine or upscaled? (with a spectrogram) | genuine, or upscaled |

Each entry shows the evidence: titles, durations, formats, fingerprints. **Defer** puts an entry aside. Filter the list by status, kind, origin and confidence, and decide many entries at once with **Accept all** or **Reject all**. Rejected suggestions do not come back.

## Conflicts

<Screenshot name="conflicts" alt="The conflict list" />

A conflict arises when an automatic source – for example a MusicBrainz update – proposes a new value for a field that a person or an import set. Group the conflicts by album, artist, field or source, and **Accept** the proposal or **Keep** the current value, one at a time or for a whole group.
