# What Anthology is

Anthology is an open-source, self-hosted music application. You run it on your own server or NAS, and everyone in your household uses it from the browser. It brings together what usually takes several programs:

- **Acquiring music** – import an existing collection from a folder, or order albums from optional source services.
- **Listening** – in the browser on any device, or on Teufel Raumfeld speakers in every room.
- **Curating** – edit tags, review uncertain results, add covers, keep playlists and favorites.

<Screenshot name="library-albums" alt="The album list of the Local view" />

## The two views

Anthology has two main views, shown in the navigation on the left:

- **Streaming** – where music comes in: searching source services, ordering albums, importing folders.
- **Local** – your library: albums, artists, tracks, your playlists, favorites and history.

Works (compositions, arrangements and medleys) and sheet music follow in later versions.

## How it runs

Anthology is a server with a web app. The server does all the work – imports, identification, quality analysis, transcoding – in the background, and every client only sends orders. You can close the app at any time; the work continues and the lists update live when you come back.

The installation is a pod of containers: the server (MIT license), a tagger service for reading and writing tags (GPL), and PostgreSQL. See [Installation and administration](/administration/).

::: warning Pre-release
Versions below 1.0 are pre-releases. They are meant for trying Anthology out, not for production use yet.
:::
