# Eine Sammlung importieren

Administratoren importieren Ordner vom Server: **Streaming › Ordner importieren**. Wählbar sind nur Ordner unterhalb der Import-Ordner (`ANTHOLOGY_IMPORT_ROOTS`, Vorgabe `/data/imports`).

<Screenshot name="import-dialog" alt="Der Dialog zur Wahl eines Ordners für den Import" />

## So läuft ein Import

1. **Ordner wählen** und den Speichermodus, dann die Prüfung starten.
2. Anthology **liest und analysiert** jede Datei: Tags, technische Daten und einen akustischen Fingerabdruck. Noch wird nichts verschoben oder geändert.
3. Du erhältst einen **Bericht**: neue Titel, Duplikate von Titeln, die du schon hast, bessere oder schlechtere Kopien, Dateien, die eine Entscheidung brauchen.
4. **Bestätige** den Bericht. Erst jetzt werden die Dateien abgelegt und die Einträge der Bibliothek angelegt. Danach erkennt Anthology die Aufnahmen und holt Cover.

Du kannst die App schliessen, während ein Import läuft; er läuft auf dem Server weiter, und sein Fortschritt wird live angezeigt.

## Speichermodi

| Modus | Was geschieht |
|---|---|
| Verweisen | die Dateien bleiben, wo sie sind; Anthology verschiebt, benennt oder löscht sie nie |
| Verlinken | ein zweiter Name (Hardlink) oder ein Copy-on-Write-Klon (Reflink) in der Bibliothek – ohne zusätzlichen Platz; der Ordner muss auf demselben Dateisystem liegen wie die Bibliothek |
| Verschieben | die Dateien wandern in die Bibliothek (über Laufwerke hinweg: kopiert, per Prüfsumme geprüft, dann entfernt) |
| Kopieren | die Dateien werden kopiert und geprüft; die Quelle bleibt unverändert |

Der Import schlägt den sparsamsten Modus vor, den die Dateisysteme erlauben. Referenzierte Dateien lassen sich später unter Einstellungen in die verwaltete Ablage übernehmen.

## Duplikate und Qualität

Ist eine Datei eine Aufnahme, die du schon hast, vergleicht der Import die **tatsächliche Qualität** beider: Eine wirklich bessere Kopie kann das bestehende Original ersetzen, die schlechtere wird übersprungen. Unklare Fälle landen in der Prüfliste.
