# Quelldienste

Quelldienste sind optionale, eigenständige Container, die Musik aus anderen Quellen anbieten – etwa von Streamingdiensten oder Online-Shops. Sie leben in eigenen Repositories (Organisation `anthology-sources`) unter eigenen Lizenzen; Anthology spricht mit ihnen über eine dokumentierte Schnittstelle (siehe [API für Quellen](/de/source-api/)).

## Einen Quelldienst hinzufügen

1. Nimm den Container des Dienstes in den Pod auf, mit dem Import-Volume unter `/data/imports`.
2. Trage seine URL in `ANTHOLOGY_SOURCE_SERVICES` ein (durch Kommas getrennt, z. B. `http://localhost:8420`).
3. Starte den Server neu. Er prüft jeden Dienst jede Minute; **Streaming › Quellenstatus** zeigt, ob er verfügbar ist und warum nicht.

Braucht ein Dienst eine Anmeldung, tragen Administratoren sie unter **Einstellungen › Quellen** ein. Die Werte werden verschlüsselt gespeichert und nie wieder angezeigt.

## Quellen nutzen

Redaktion und Administratoren durchsuchen auf der Seite **Streaming** eine Quelle oder fügen einen Link ein. Anthology zeigt bei jedem Titel, ob du ihn schon hast und in welcher Qualität. Eine Bestellung lädt die Titel im Hintergrund und importiert sie; der Import bestätigt sich selbst, und sein Ergebnis wird pro Titel angezeigt.

<Screenshot name="source-search" alt="Ein bei einem Quelldienst gefundenes Album mit seinen Titeln" />

::: tip Deine Verantwortung
Downloads von kommerziellen Diensten unterliegen deren Bedingungen. Die Nutzung von Quelldiensten liegt bei dir.
:::
