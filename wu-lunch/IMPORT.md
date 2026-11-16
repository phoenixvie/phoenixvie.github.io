# WU Food / WU Lunch – So kommen die Menüs auf die Seite

Stand: 17. November 2026. Diese Datei beschreibt den **tatsächlichen** Ablauf in einfacher Sprache.
Details zu Prüfregeln stehen in `IMPORT-QUALITY.md`, `AI-REPAIR.md` und `knowledge/EXTRAKTION-UND-AKTUALISIERUNG.md`.

## Kurzfassung

1. Ein Programm auf GitHub ("Import") ruft die Seiten, PDFs und Bilder der Restaurants ab.
2. Je nach Quelle liest ein fester Parser (Webseitentext), ein echter Browser (Topf & Deckel) oder ein KI-Modell (Mensa-PDF, Finn-Bild) das Menü aus.
3. Unabhängige Prüfungen kontrollieren Woche, Preise, Vollständigkeit und Widersprüche. Nur was besteht, geht online.
4. Website und App lesen dieselbe Datei `data/menus.json`; Admin-Änderungen kommen zusätzlich aus Supabase und haben Vorrang.

Die KI "surft" nie selbst: Das Programm lädt die Originale herunter und übergibt sie dem Modell.

## Wann wird geprüft?

GitHub startet zeitgesteuerte Läufe dieses Repositorys erfahrungsgemäß **nur wenige Male pro Tag und oft viele Stunden verspätet**
(Messung 7.–16.11.2026: etwa zwei Starts pro Tag, rund acht Stunden nach dem geplanten Zeitpunkt). Am Montag, 16.11.2026 lief der erste
Import deshalb erst um 13:42 Uhr – Finn, Lia und Topf & Deckel erschienen verspätet. Darum gibt es zwei Ebenen:

| Ebene | Was sie tut | Wann |
| --- | --- | --- |
| **Taktgeber** (`wu-lunch-takt.yml`, `scripts/takt.py`) | Ein Wächter-Job bleibt aktiv und löst den Import selbst pünktlich aus. | Sonntag 17:00 bis Montag 13:30 durchgehend. Außerdem Mo–Fr 05:30–13:30, solange für den Tag noch ein Menü fehlt und GitHub den Wächter an diesem Vormittag einmal gestartet hat. |
| **Auffangnetz** (`wu-lunch-menus.yml`, Zeitplan) | Jeder Start, den GitHub tatsächlich ausführt, importiert sofort. | Täglich zwischen 05:15 und 22:15, sooft GitHub startet. Verspätete Läufe werden nicht mehr übersprungen. |

Im Wachzeitraum prüft der Taktgeber **alle 15 Minuten**, solange Menüs fehlen (Vormittag), sonst **stündlich**; nachts 22:30–05:30 ruht er.
Alle Zeiten stehen in `update-policy.json` (Abschnitt `watch`) und lassen sich dort ändern, z. B. um die Wache auf weitere Tage auszudehnen.

**Selbstheilung des Taktgebers:** Jeder tatsächlich gestartete Zeitplan-Lauf (Import, Übersetzung, Veröffentlichungsmonitor und der eigene
Zeitplan des Taktgebers) prüft, ob eine Wache gebraucht wird und läuft, und startet sie sonst neu. Läuft bereits eine, beendet sich die neue sofort.
Vor Ablauf der GitHub-Höchstlaufzeit (6 Stunden) übergibt der Wächter selbst an einen Nachfolger.

**Grenzen, ehrlich benannt:** Der Wächter belegt in seinem Zeitraum einen GitHub-Rechner, der meist nur wartet (rund 20 Stunden pro Woche).
Für öffentliche Repositories ist das kostenlos; GitHub sieht Dauerläufer aber nicht gern. Deshalb läuft er bewusst nur rund um den Wochenstart
und nicht rund um die Uhr. Garantiert minutengenau ist nur ein externer Auslöser (siehe unten).

### Optional: exakter externer Auslöser

Wer an jedem Werktag garantierte Zeiten will, kann den Import von außen anstoßen lassen, z. B. mit `pg_cron` in Supabase oder einem
Cron-Dienst, der die GitHub-Schnittstelle `workflow_dispatch` für `wu-lunch-menus.yml` aufruft. Dafür ist ein GitHub-Zugriffstoken
("fine-grained", nur dieses Repository, Berechtigung *Actions: Read and write*) nötig, das **nicht** ins Repository gehört. Der Import-Workflow
ist darauf vorbereitet: Jeder manuelle oder externe Start läuft sofort.

## Was passiert bei Fehlern? (Selbstkorrektur)

| Situation | Früher | Jetzt |
| --- | --- | --- |
| KI-Dienst kurz nicht erreichbar oder überlastet | Schritt scheitert, neuer Versuch frühestens am nächsten Tag | Bis zu drei automatische Wiederholungen mit Pausen im selben Lauf |
| KI-Antwort zur Mensa besteht eine Prüfung nicht (z. B. Preis im falschen Feld) | Ganze Mensa-Karte bleibt auf dem reduzierten Notstand | Bis zu drei Korrekturrunden: Das Modell bekommt dasselbe PDF, seine Antwort und den genauen Befund; das Ergebnis durchläuft wieder alle Prüfungen |
| KI-Lesung (Mensa-PDF, Finn-Bild) scheitert endgültig | Erst am nächsten Tag wieder | Ein weiterer Versuch am selben Tag nach 60 Minuten; bei geänderter Quelle sofort |
| Topf & Deckel: Browserabruf fällt aus oder Lauf startet zur "falschen" Stunde | Nur das Tagesmenü, restliche Woche leer | Der Browserabruf läuft bei jedem Import, bis alle fünf Tage geprüft vorliegen (Wiederholung nach 40 Minuten) |
| Abschlussprüfung beanstandet **ein** Restaurant | Kein einziges neues Menü geht online | Nur dieses Restaurant behält seinen bisherigen Stand; alle anderen gehen online. Die Quelle wird beim nächsten Lauf neu ausgewertet |
| Ein einzelner Text lässt sich nicht geprüft übersetzen | Gar keine neue englische Übersetzung | Alle anderen werden gespeichert; nur dieser Text bleibt "English translation pending" (im Admin ergänzbar) |
| GitHub startet einen Lauf Stunden zu spät | Lauf wird als "außerhalb des Fensters" verworfen | Lauf importiert trotzdem |

Unverändert gilt: **Nichts wird erfunden.** Eine Korrekturrunde ersetzt keine Prüfung – ein Preis, der nicht im Original steht, fällt weiterhin durch.
Bei einem Quellenproblem bleiben gültige Daten derselben Woche stehen; Menüs einer alten Woche werden nie als neue Woche gezeigt.

## Wo sehe ich, was passiert ist?

- **Admin → Aktualisierung:** letzter echter Quellenabruf je Restaurant, Ergebnis (übernommen, unverändert, noch nicht veröffentlicht, Fehler, zurückgehalten) und Link zum Lauf.
- `status.json`: Zustand je Quelle und offene Probleme. `data/update-status.json`: tatsächlich ausgeführte Schritte des letzten Laufs.
- `data/menu-sanity-report.json`: Abschlussprüfung; `withheld` nennt zurückgehaltene Restaurants samt Grund.
- GitHub → Actions: "WU Lunch – Speisepläne aktualisieren" (Import) und "WU Lunch – Taktgeber" (Wächter).

Ein geplanter Termin ist kein Beleg für einen Abruf; angezeigt werden deshalb echte Abrufzeiten.

## Manuell starten

GitHub → Actions → "WU Lunch – Speisepläne aktualisieren" → "Run workflow". Der Lauf importiert sofort, unabhängig von der Uhrzeit.

## Lokal prüfen (ohne Internet und ohne KI-Kosten)

```sh
pip install -r wu-lunch/requirements.txt
python wu-lunch/scripts/update_schedule.py --check
python wu-lunch/scripts/update_menus.py --smoke-test
python -m unittest discover -s wu-lunch/scripts -p 'test_*.py'
python -m unittest discover -s wu-lunch/ai-pilot -p 'test_*.py'
```

## Benötigte Einstellungen

GitHub-Secrets `OPENAI_API_KEY` (KI-Lesungen) und `SUPABASE_SERVICE_ROLE_KEY` (Archiv, Übersetzungen). Die Workflows brauchen Schreibrechte auf
Repository-Inhalte sowie das Recht, Workflows zu starten (`actions: write`, in den Dateien gesetzt). Keine Geheimnisse im Frontend.
