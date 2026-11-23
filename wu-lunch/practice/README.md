# Leseübung – Übungssammlung

Hier üben die beiden allgemeinen Leser von WU Food an Wochenkarten von Lokalen, die gar nicht angezeigt werden.
Nichts aus diesem Ordner erscheint auf der Webseite oder in der App.

- `sources.json` – die Übungslokale (nur deren eigene Webseiten oder PDFs; keine Sammelportale).
- `cards/<lokal>/<montag>.txt` – der Kartenausschnitt der Woche (rund um die Wochentage, nicht die ganze Seite).
- `results/<lokal>/<montag>.json` – was der Ersatzleser (Regeln) und der KI-Leser (Vergleichslesung) gelesen haben, und das Urteil.
- `expected/<lokal>-<montag>.json` – von Hand geprüfte Fälle. Sie sind feste Tests: Der Ersatzleser muss sie weiter genau so lesen.
- `scoreboard.json` – je Woche: wie viele Karten der Ersatzleser allein geschafft hat.

Ablauf und Regeln: `../scripts/practice.py` und der Abschnitt „Leseübung“ in `../IMPORT.md`.
