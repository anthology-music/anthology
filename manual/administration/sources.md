# Source services

Source services are optional, separate containers that offer music from other sources – for example streaming services or online shops. They live in their own repositories (organisation `anthology-sources`) under their own licenses; Anthology talks to them through a documented interface (see [Source service API](/source-api/)).

## Adding a source service

1. Add the service's container to the pod, with the imports volume mounted at `/data/imports`.
2. List its URL in `ANTHOLOGY_SOURCE_SERVICES` (comma-separated, e.g. `http://localhost:8420`).
3. Restart the server. It checks every service each minute; **Streaming › Source status** shows whether it is available and why not.

If a service needs a login, admins enter it in **Settings › Sources**. The values are stored encrypted and never shown again.

## Using sources

Editors and admins search a source or paste a link on the **Streaming** page. Anthology shows for each track whether you already have it, and in which quality. An order downloads the tracks in the background and imports them; the import confirms itself, and its outcome is shown per track.

<Screenshot name="source-search" alt="An album found at a source service, with its tracks" />

::: tip Your responsibility
Downloading from commercial services is subject to their terms. Anthology leaves the use of source services to you.
:::
