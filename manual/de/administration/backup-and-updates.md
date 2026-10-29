# Sicherung und Updates

## Was zu sichern ist

| Daten | Wie |
|---|---|
| die Datenbank | `pg_dump` der Datenbank `anthology`, z. B. täglich |
| das Bibliotheks-Volume (`/data/library`) | Dateisicherung; es enthält die verwalteten Originale und die Coverbilder |
| das Schlüssel-Volume (`/data/keys`) | Dateisicherung; ohne es müssen sich alle Geräte neu anmelden |
| referenzierte Ordner | deine eigene Sicherung – Anthology ändert sie nie |

Das Cache-Volume (`/data/cache`) lässt sich neu aufbauen und braucht keine Sicherung.

Nach dem Zurückspielen einer älteren Sicherung prüfe das nächste Ergebnis der Systempflege, bevor du eine Löschung bestätigst (siehe [Wartung](./maintenance)).

## Aktualisieren

Lies das [Changelog](https://github.com/anthology-music/anthology/blob/main/CHANGELOG.md) der neuen Version und mache vorher eine Sicherung.

- **Feste Version** (ein Installationspaket oder `:X.Y.Z`): Ändere die Tags auf die neue Version oder entpacke das Paket des neuen Releases über die alten Dateien, dann neu starten (`systemctl --user daemon-reload && systemctl --user restart anthology-pod` oder `docker compose up -d`).
- **`latest`:** mit Quadlet die Images mit `podman pull` holen und `systemctl --user restart anthology-pod` (oder `podman auto-update` mit `AutoUpdate=registry`); mit Compose `docker compose pull && docker compose up -d`.

Datenbank-Migrationen laufen beim Start des Servers automatisch. **Einstellungen › Über Anthology** zeigt die laufende Version.
