# Source service API

Anthology acquires music from other sources through **source services**: separate containers that each wrap one source and speak a small HTTP/JSON interface. The core never contains download code for commercial services; a source service can have its own license and its own release cycle.

This part is for developers who want to write a source service.

## How it fits together

1. The server lists the services in `ANTHOLOGY_SOURCE_SERVICES` and checks each one every minute (`GET /v1/info`, `GET /v1/health`).
2. Users search a service or paste a link; the server passes the request on (`/v1/search`, `/v1/resolve`) and shows the results with what the library already has.
3. An order becomes a download task at the service. The service writes the files into the shared imports volume, and the server imports them with its normal import – the service never touches the library.

## Writing a service

- Implement the endpoints of the [interface reference](./reference) for interface version 1.
- Take `tools/fake-source-service/` of the repository as a reference: it speaks every endpoint and is what the end-to-end tests use.
- Respect the terms, rate limits and robots.txt of your source; report rate limits with `rate_limited` and `retry_after`.
- Publish the container as a plain OCI image; it runs in the Anthology pod, on one of the ports 8420–8429.
- Choose your service's license freely. The interface is the only connection to Anthology.

When the interface changes incompatibly, it gets a new version (`/v2`); a service with another version is shown as incompatible and left out.
