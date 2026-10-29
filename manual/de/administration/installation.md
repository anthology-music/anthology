# Installation

Anthology läuft als ein Pod aus Containern. Jeder Teil ist ein OCI-Image und funktioniert mit **Podman** wie mit **Docker**:

| Container | Lizenz | Nötig |
|---|---|---|
| `anthology-server` – API und Web-App, der einzige veröffentlichte Port (8400) | MIT | ja |
| `anthology-tagger` – liest und schreibt Tags | GPL-2.0-or-later | ja |
| `postgres` – die Datenbank | PostgreSQL | ja |
| Quelldienste (eigene Repositories) | eigene | optional |

Die Images liegen auf ghcr.io für `linux/amd64` und `linux/arm64`: `ghcr.io/anthology-music/anthology-server` und `ghcr.io/anthology-music/anthology-tagger`, getaggt mit der Version (`0.1.0`, `0.1`) und `latest`.

## Voraussetzungen

- Ein Linux-Host mit **Podman 5** oder neuer (empfohlen, rootless mit systemd) oder **Docker** mit Compose.
- 2 GB Arbeitsspeicher für eine kleine Bibliothek; PostgreSQL und die Bibliothek wachsen mit deiner Sammlung.
- Speicherplatz für deine Musik: Verlustfreie Originale von 500 000 Titeln brauchen etwa 12 bis 18 TB.

## Installationspakete

Jedes [Release](https://github.com/anthology-music/anthology/releases) bietet zwei Pakete, deren Images auf dieses Release festgelegt sind. Entpacke eines und folge seiner `README.md`:

- `anthology-<version>-compose.tar.gz` – für Docker Compose oder Podman Compose;
- `anthology-<version>-quadlet.tar.gz` – für Podman Quadlet.

## Podman mit Quadlet (empfohlen)

Quadlet macht aus den Unit-Dateien systemd-Dienste: Der Pod startet mit deiner Benutzersitzung und startet neu, wenn etwas ausfällt.

```sh
mkdir -p ~/.config/containers/systemd
cp *.pod *.container *.volume ~/.config/containers/systemd/
openssl rand -base64 32 | podman secret create anthology-db-password -
systemctl --user daemon-reload
systemctl --user start anthology-pod
```

Damit der Pod ohne offene Anmeldung weiterläuft: `loginctl enable-linger $USER`.

## Docker oder Podman mit Compose

```sh
mkdir -p secrets && openssl rand -base64 32 > secrets/db_password
docker compose up -d        # oder: podman compose up -d
```

Halte `secrets/db_password` privat (`chmod 600`).

## Installation prüfen

Öffne `http://<host>:8400`. Eine neue Installation öffnet die Einrichtung, in der du das erste Konto anlegst – siehe [Erste Schritte](./first-steps). Der Server meldet seinen Zustand unter `/api/v1/health` und `/api/v1/ready`.

## Versionen

Solange Anthology unter 1.0 ist, ist jedes Release eine Vorabversion, und `latest` folgt ihr. Um bei einer Version zu bleiben, nimm ihren Tag (`:0.1.0`) oder ein Installationspaket. Einstellungen › Über Anthology zeigt die laufende Version.
