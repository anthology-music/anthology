# Raumfeld speakers

Anthology plays on Teufel Raumfeld speakers. The server needs to find the Raumfeld host, and the speakers need to reach the server.

## Finding the Raumfeld host

- **With host networking** (`Network=host` in `anthology.pod`, `network_mode: host` in Compose), the server finds the Raumfeld host automatically by multicast (SSDP).
- **Without host networking** (the default rootless pod), multicast does not reach the server. Enter the address of the Raumfeld host in **Settings › Speakers** – the IP address of the base or of the speaker that serves as host – or set `ANTHOLOGY_RAUMFELD_HOSTS`.

**Settings › Speakers** shows every system with its state, and the reason when it cannot be reached.

## Speakers reaching the server

The speakers fetch the music from the server over HTTP. Set `ANTHOLOGY_OUTPUT_MEDIA_URL` to the server's address as the speakers see it, for example `http://192.168.1.10:8400`. Without it, the server uses its own address on the route to the speakers – behind the pod's port forwarding that is the container's address, so set the URL there.

Speakers and server must be in the same local network; no port needs to be opened to the internet.

How to play on speakers: [Playing on speakers](/guide/speakers).
