# API für Quellen

Anthology nimmt Musik aus anderen Quellen über **Quelldienste** auf: eigenständige Container, die je eine Quelle umhüllen und eine kleine HTTP/JSON-Schnittstelle sprechen. Der Kern enthält nie Download-Code für kommerzielle Dienste; ein Quelldienst kann eine eigene Lizenz und einen eigenen Release-Zyklus haben.

Dieser Teil richtet sich an Entwicklerinnen und Entwickler, die einen Quelldienst schreiben wollen.

## Wie es zusammenspielt

1. Der Server liest die Dienste aus `ANTHOLOGY_SOURCE_SERVICES` und prüft jeden jede Minute (`GET /v1/info`, `GET /v1/health`).
2. Benutzer durchsuchen einen Dienst oder fügen einen Link ein; der Server reicht die Anfrage weiter (`/v1/search`, `/v1/resolve`) und zeigt die Ergebnisse mit dem, was die Bibliothek schon hat.
3. Eine Bestellung wird beim Dienst zur Download-Aufgabe. Der Dienst schreibt die Dateien in das gemeinsame Import-Volume, und der Server importiert sie mit seinem normalen Import – der Dienst berührt die Bibliothek nie.

## Einen Dienst schreiben

- Setze die Endpunkte der [Referenz der Schnittstelle](./reference) für die Schnittstellenversion 1 um.
- Nimm `tools/fake-source-service/` aus dem Repository als Vorlage: Er spricht jeden Endpunkt und wird von den End-to-End-Tests verwendet.
- Halte die Bedingungen, Ratenbegrenzungen und die robots.txt deiner Quelle ein; melde Ratenbegrenzungen mit `rate_limited` und `retry_after`.
- Veröffentliche den Container als einfaches OCI-Image; er läuft im Anthology-Pod auf einem der Ports 8420–8429.
- Wähle die Lizenz deines Dienstes frei. Die Schnittstelle ist die einzige Verbindung zu Anthology.

Ändert sich die Schnittstelle inkompatibel, erhält sie eine neue Version (`/v2`); ein Dienst mit anderer Version wird als inkompatibel angezeigt und ausgelassen.
