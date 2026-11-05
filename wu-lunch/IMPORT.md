# WU Lunch – Datenpipeline

## Architektur

Die bestehende Webseite `wu-lunch/index.html` bleibt unverändert. Sie liest `data.js` mit demselben Datenformat wie bisher. Der täglich gestartete GitHub-Actions-Workflow `.github/workflows/wu-lunch-menus.yml` schreibt die aktualisierten Speisepläne in `wu-lunch/data.js` und `wu-lunch/data/menus.json`. Der Prüfbericht steht unter `wu-lunch/status.json`. Es werden keine Zugangsdaten oder Geheimnisse im Frontend benötigt.

## Abrufzeiten (Europe/Vienna)

Mo–Fr ca. 08:15 Uhr durch GitHub Actions; bei erheblicher Verzögerung manuell über „Run workflow“ starten. GitHub-Workflow-Timer sind nicht minutengenau garantiert.

| Quelle | Prüfung | Cache / Ablauf |
| --- | --- | --- |
| WU Mensa | Montags + täglich erneut, falls die aktuelle Woche fehlt | Erfolgreich geparstes, datiertes PDF wird bis zum Wochenende zwischengespeichert |
| Das Glashaus | Montags + täglich erneut, falls die aktuelle Woche fehlt | Datierter Wochenplan wird zwischengespeichert |
| Das Campus | Mo–Fr täglich | HTML prüfen, Gültigkeit und Datumsbereich kontrollieren |
| Baschly | Mo–Fr täglich, 2 Produktseiten | Undatierten Plan neu lesen, als „undated“ behandeln |
| L'Osteria | ca. alle 14 Tage oder bei fehlenden Daten | Saisongerichte; nicht als Tagesmenü kennzeichnen |

## Fehlerbehandlung

- HTTPS-Abrufe ausschließlich von erlaubten Restaurant-Domains, Timeout, Antwortgröße, maximal drei Wiederholungen.
- Die Mensa-PDF wird nach Gültigkeitsdatum und Tabellenspalten ausgewertet. Falsches Datum oder unvollständige Tabelle -> Fehler, **keine** falschen Daten.
- Bei Quellenproblemen bleiben bereits gültige Daten derselben Kalenderwoche erhalten. Alte Wochen werden beim Wochenwechsel nie als neue Woche ausgegeben.
- `status.json` zeigt Probleme, erfolgreiche Abrufe und aufeinanderfolgende Fehlversuche.
- ChatGPT-Automation „WU Mittagsmenüs täglich“ überwacht die Daten und kann über Gmail auf hartnäckige Fehler hinweisen. **Gmail ist nicht im GitHub-Workflow selbst eingerichtet.**

## Manuell prüfen

```sh
pip install -r wu-lunch/requirements.txt
python wu-lunch/scripts/update_menus.py --smoke-test
python wu-lunch/scripts/update_menus.py
```

Der Workflow braucht GitHub Actions sowie `GITHUB_TOKEN` mit Schreibzugriff auf Repository-Inhalte. Wenn die Repository-Einstellung GitHub Actions auf read-only beschränkt, muss der Owner die „Workflow permissions“ auf „Read and write“ ändern. Keine zusätzlichen Geheimnisse erforderlich.

## Darstellung

Die UI-Logik (Mensa: Tagessuppe + Hauptspeise; Glashaus: Suppe + Hauptspeise; Listen- und Kartenansicht; Buchstabenlogos; Mobilansicht) ist ausschließlich im Frontend implementiert und bleibt von der Datenpipeline unabhängig.
