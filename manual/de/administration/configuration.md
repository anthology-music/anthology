# Konfiguration

Der Server wird mit Umgebungsvariablen eingerichtet, die mit `ANTHOLOGY_` beginnen. In den Quadlet-Dateien sind es `Environment=`-Zeilen von `anthology-server.container`, in Compose stehen sie unter `environment:` von `anthology-server`.

## Wichtige Einstellungen

| Variable | Vorgabe | Bedeutung |
|---|---|---|
| `ANTHOLOGY_DATABASE_URL` | vom Pod gesetzt | PostgreSQL-Verbindung; das Passwort kommt aus `ANTHOLOGY_DATABASE_PASSWORD_FILE` |
| `ANTHOLOGY_TIME_ZONE` | `UTC` | Zeitzone der Zeitpläne, z. B. `Europe/Zurich` |
| `ANTHOLOGY_IMPORT_ROOTS` | `/data/imports` | Ordner, aus denen Administratoren importieren dürfen, durch Kommas getrennt |
| `ANTHOLOGY_MUSICBRAINZ_CONTACT` | – | deine E-Mail oder URL, an MusicBrainz als verlangter Kontakt gesendet |
| `ANTHOLOGY_ACOUSTID_API_KEY` | – | schaltet Fingerabdruck-Abfragen bei AcoustID frei |
| `ANTHOLOGY_MUSICBRAINZ_URL` | – | ein lokaler MusicBrainz-Spiegel (ohne Ratenbegrenzung) |
| `ANTHOLOGY_SOURCE_SERVICES` | – | URLs der Quelldienste, durch Kommas getrennt |
| `ANTHOLOGY_RAUMFELD_HOSTS` | – | Adressen von Raumfeld-Hosts, wenn die Suche sie nicht findet |
| `ANTHOLOGY_OUTPUT_MEDIA_URL` | – | die Adresse des Servers, wie die Lautsprecher sie sehen |
| `ANTHOLOGY_TRANSCODE_CACHE_GB` | `20` | Grösse des Umwandlungs-Caches |
| `ANTHOLOGY_THUMBNAIL_CACHE_MB` | `512` | Grösse der Cover-Vorschaubilder |
| `ANTHOLOGY_JOBS_THROTTLE` | `normal` | gleichzeitige Hintergrundaufträge: `gentle`, `normal`, `fast` |

## Daten-Volumes

| Volume | Eingehängt unter | Inhalt | Sichern |
|---|---|---|---|
| `anthology-library` | `/data/library` | deine Musik (Originale) und die Coverbilder | ja |
| `anthology-db` | PostgreSQL | die Datenbank | ja (`pg_dump`) |
| `anthology-keys` | `/data/keys` | Signaturschlüssel; ohne sie sind alle Geräte abgemeldet | ja |
| `anthology-imports` | `/data/imports` | eingehende Dateien | optional |
| `anthology-cache` | `/data/cache` | Umwandlungen, getaggte Kopien, Vorschaubilder | nein |

Eine bestehende Sammlung kann das Bibliotheks-Volume durch einen Bind-Mount eines Host-Ordners ersetzen (`Volume=/srv/music:/data/library:Z`); Server und Tagger brauchen denselben Pfad.

## HTTPS und Zugriff von aussen

Der Server spricht einfaches HTTP auf Port 8400. Für den Zugriff von ausserhalb deines Netzes stelle einen Reverse-Proxy mit TLS davor (etwa Caddy, Traefik oder nginx) und leite WebSocket-Upgrades für `/api/v1/ws` weiter. Der Server vertraut `X-Forwarded-*`-Kopfzeilen nur von `127.0.0.1`; läuft der Proxy anderswo, setze `FORWARDED_ALLOW_IPS` auf seine Adresse.
