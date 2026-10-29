# Was Anthology ist

Anthology ist eine quelloffene, selbst betriebene Musikanwendung. Du betreibst sie auf deinem eigenen Server oder NAS, und alle in deinem Haushalt nutzen sie im Browser. Sie vereint, wofür es sonst mehrere Programme braucht:

- **Musik aufnehmen** – eine bestehende Sammlung aus einem Ordner importieren oder Alben bei optionalen Quelldiensten bestellen.
- **Hören** – im Browser auf jedem Gerät oder auf Teufel-Raumfeld-Lautsprechern in jedem Raum.
- **Pflegen** – Tags bearbeiten, unsichere Ergebnisse prüfen, Cover ergänzen, Playlists und Favoriten führen.

<Screenshot name="library-albums" alt="Die Albenliste der Ansicht Lokal" />

## Die zwei Ansichten

Anthology hat zwei Hauptansichten, die in der Navigation links stehen:

- **Streaming** – hier kommt Musik herein: Quelldienste durchsuchen, Alben bestellen, Ordner importieren.
- **Lokal** – deine Bibliothek: Alben, Künstler, Titel, deine Playlists, Favoriten und dein Verlauf.

Werke (Kompositionen, Arrangements und Medleys) und Noten folgen in späteren Versionen.

## Wie es läuft

Anthology ist ein Server mit einer Web-App. Der Server erledigt alle Arbeit – Importe, Erkennung, Qualitätsanalyse, Umwandlung – im Hintergrund, und jeder Client sendet nur Aufträge. Du kannst die App jederzeit schliessen; die Arbeit läuft weiter, und die Listen sind aktuell, wenn du zurückkommst.

Die Installation ist ein Pod aus Containern: der Server (MIT-Lizenz), ein Tagger-Dienst zum Lesen und Schreiben von Tags (GPL) und PostgreSQL. Siehe [Installation und Administration](/de/administration/).

::: warning Vorabversion
Versionen unter 1.0 sind Vorabversionen. Sie sind zum Ausprobieren gedacht, noch nicht für den produktiven Einsatz.
:::
