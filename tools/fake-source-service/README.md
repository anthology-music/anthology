# Fake source service

A source service that speaks the Anthology source service interface v1
(`docs/architecture/source-service-api.md`) without contacting any streaming service: a fixed
catalogue of fictional albums, links of the form `https://fake.example/album/<n>`, an optional
login and downloads that write generated tones (FLAC with tags through FFmpeg, WAV without it).

For tests and development only; it is never part of an image. The server tests mount it in
process; the end-to-end tests start it on port 8429.

```
uv run anthology-fake-source --port 8429
```

| Variable | Default | Meaning |
|---|---|---|
| `ANTHOLOGY_FAKE_SOURCE_LOGIN` | empty | `user:secret` makes the service require that login |
| `ANTHOLOGY_FAKE_SOURCE_INTERFACE` | `1` | reported interface version (tests of incompatible services) |
| `ANTHOLOGY_FAKE_SOURCE_DELAY` | `0.2` | seconds per downloaded track |
| `ANTHOLOGY_FAKE_SOURCE_FFMPEG` | `ffmpeg` | FFmpeg for FLAC output |

`POST /test/rate-limit {"seconds": n}` makes downloads wait for `n` seconds (tests only).
