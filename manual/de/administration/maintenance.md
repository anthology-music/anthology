# Wartung

## Systempflege

Die Systempflege (**Einstellungen**, Administratoren) läuft in der Vorgabe täglich um 03:00 in der Zeitzone der Installation; Administratoren können den Zeitplan (aus, täglich, wöchentlich), die Schonfrist und die Sicherheitsgrenze ändern oder nur melden lassen. Sie

- löscht verwaiste Dateien und Reste abgebrochener Übertragungen im verwalteten Ordner der Bibliothek, nach einer Schonfrist (Vorgabe 24 Stunden);
- listet verwaltete Originale, deren Datei fehlt (sie ändert sie nie).

Referenzierte Dateien werden nie angefasst. Würde ein Lauf mehr löschen als die Sicherheitsgrenze (Vorgabe 1 % der verwalteten Dateien, mindestens 10), löscht er nichts und wartet auf deine Bestätigung – das schützt vor einer Datenbank aus einer älteren Sicherung oder einer falsch eingehängten Bibliothek.

## Erkennung und Metadaten

Nach jedem Import erkennt Anthology die Aufnahmen: über die ISRC, über den akustischen Fingerabdruck bei AcoustID (mit API-Schlüssel), sonst über eine Suche bei MusicBrainz nach Künstler und Titel. Treffer unterhalb der Gewissheit kommen in die Prüfliste. Ein täglicher Abgleich vergleicht erkannte Aufnahmen mit MusicBrainz; Änderungen an Werten, die jemand von Hand gesetzt hat, werden zu Konflikten.

## Qualitätsanalyse

Redaktion und Administratoren können unter **Einstellungen** die Qualitätsanalyse der ganzen Bibliothek starten. Sie analysiert das Spektrum jeder Datei einmal und speichert ihre **tatsächliche Qualität**. Importe und Bestellungen analysieren nur die Dateien, die sie vergleichen müssen.

## Cover

Cover werden nach jedem Import geholt (eingebettete Bilder, Cover Art Archive). Einmal pro Installation holt ein Auftrag sie für die bestehende Bibliothek. Die Redaktion kann sie für ein Album oder die ganze Bibliothek erneut holen.

## Aufträge

Jede lange Aufgabe ist ein Auftrag. Die Auftragsübersicht zeigt sie mit Fortschritt live; du kannst sie pausieren, fortsetzen oder abbrechen. `ANTHOLOGY_JOBS_THROTTLE` begrenzt, wie viele gleichzeitig laufen.
