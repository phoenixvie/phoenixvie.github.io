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

**1. Taktgeber** (`wu-lunch-takt.yml`, `scripts/takt.py`): Ein Wächter-Job wartet auf feste Termine und löst den Import selbst pünktlich aus.

| Wann (Wiener Zeit) | Termine |
| --- | --- |
| Freitagnacht | Samstag 00:10 – holt alles, was bis Freitagabend für die neue Woche veröffentlicht wurde |
| Samstag | 08:00, 13:00, 18:00 |
| Sonntag | 09:00, 15:00, 21:00 |
| Montag | ab 05:30 **alle 15 Minuten, solange Menüs fehlen** (bis 13:30); zusätzlich feste Termine 05:30, 07:00, 08:30, 10:00, 11:30, 13:30, 15:30, 17:30 |
| Dienstag bis Freitag | 07:00 und 10:30, **solange noch ein Menü fehlt** |
| Montag bis Freitag (Wels) | 08:30, 09:30, 10:30 und 11:30 stößt der Wächter den **Welser Import** an, solange die Tageskarte eines Lokals mit täglich neuer Karte fehlt (derzeit Gasthaus Huber) |

Warum "Freitagnacht" kurz nach Mitternacht liegt: Bis Freitag 24:00 zeigen Seite und App die laufende Woche. Der Import stellt deshalb erst am
Samstag auf die neue Woche um; ein Lauf am Freitagabend könnte Menüs der nächsten Woche noch nirgends ablegen. Um 00:10 ist alles vom
Freitagabend erfasst und ab Samstag früh sichtbar.

Lokale mit täglich neuer Karte veröffentlichen erst am Vormittag des Tages. Am 24.11.2026 stand Hubers Dienstagsmenü um 09:50 auf
der Webseite, aber nicht in der App: Seit der Nacht war kein Import gelaufen, weil bei den WU-Lokalen nichts fehlte. Seither hält eine
fehlende Tageskarte den Wächter wach (auch über Nacht, damit er am Morgen sicher läuft); die Zeiten stehen in `update-policy.json`
unter `watch.daily`. Ein Lokal, das bis zur Wochenmitte noch gar nichts gezeigt hat (Betriebsurlaub), zählt dabei nicht.

Der Wächter ist von **Freitag 18:00 bis Montag 18:00 immer aktiv** und darüber hinaus, solange ein Menü fehlt (dann auch über Nacht, damit der
Termin um 07:00 sicher stattfindet). Ist alles veröffentlicht, endet er bis zum nächsten Wochenende. Alle Zeiten stehen in `update-policy.json`
(Abschnitt `watch`: `slots`, `dense`, `periods`) und lassen sich dort ändern.

**2. Auffangnetz** (`wu-lunch-menus.yml`, Zeitplan): Jeder Start, den GitHub tatsächlich ausführt (täglich zwischen 05:15 und 22:15, erfahrungsgemäß
ein- bis zweimal pro Tag zu unvorhersehbarer Zeit), importiert sofort. Verspätete Läufe werden nicht mehr übersprungen. Das ist die tägliche
Prüfung für Wochen, in denen nichts mehr fehlt.

### Bereits veröffentlichte Wochenkarten werden nicht mehr abgerufen

Hat ein Restaurant seine Wochenkarte für genau diese Woche geprüft und vollständig (alle fünf Tage) veröffentlicht, wird es in dieser Woche
**nicht mehr neu abgerufen** – weder am Wochenende noch bei den dichten Montagsprüfungen. Das spart Abrufe und KI-Kosten und verhindert, dass ein
guter Stand durch eine misslungene Neu-Auswertung ersetzt wird (so geschehen bei der Mensa am 16.11.2026: 63 → 20 Gerichte).

- Weiter geprüft werden: Restaurants, die noch nichts veröffentlicht haben; Wochen, in denen ein Tag fehlt; Baschly (die Karte trägt kein
  Datum, daher lässt sich nicht sicher sagen, ob sie schon die neue Woche zeigt – hier läuft nur ein günstiger "hat sich etwas geändert?"-Vergleich).
- Folge: Ändert ein Restaurant seine bereits veröffentlichte Karte nachträglich, erscheint die Änderung nicht automatisch. Dafür gibt es beim
  manuellen Start das Häkchen **"Alle Restaurants neu prüfen"**; im Admin lassen sich Menüs außerdem direkt korrigieren.

**Selbstheilung des Taktgebers:** Jeder tatsächlich gestartete Zeitplan-Lauf (Import, Übersetzung, Veröffentlichungsmonitor und der eigene
Zeitplan des Taktgebers) prüft, ob eine Wache gebraucht wird und läuft, und startet sie sonst neu. Läuft bereits eine, beendet sich die neue sofort.
Ein verpasster Termin wird beim nächsten Start sofort nachgeholt. Vor Ablauf der GitHub-Höchstlaufzeit (6 Stunden) übergibt der Wächter selbst an
einen Nachfolger.

Kurze GitHub-Störungen reißen die Kette nicht (ergänzt am 17.11.2026, nach dem ersten echten Wachlauf): Der alte Wächter endet erst, wenn GitHub
den Nachfolger wirklich führt – wartend, laufend oder schon wieder regulär beendet; sonst übergibt er nach einer Minute erneut. Nimmt GitHub den
Start eines Imports nicht an, wird er im Minutenabstand bis zu fünfmal wiederholt, statt den Termin auszulassen. Bleibt beim Start die Abfrage
"läuft schon ein Wächter?" unbeantwortet, wacht der Lauf trotzdem: Ein doppelter Wächter ist harmlos (der Import überspringt zu dichte Starts,
und bei der nächsten Übergabe weicht der jüngere), ein fehlender wäre es nicht.

**Grenzen, ehrlich benannt:** Der Wächter belegt in seinem Zeitraum einen GitHub-Rechner, der meist nur wartet (Freitagabend bis Montagabend,
rund 72 Stunden pro Woche; länger, solange Menüs fehlen). Für öffentliche Repositories ist das kostenlos; GitHub sieht Dauerläufer aber nicht gern.
Garantiert minutengenau und ohne wartenden Rechner ist nur ein externer Auslöser (siehe unten).

### Optional: exakter externer Auslöser

Der Import lässt sich auch von außen anstoßen, z. B. mit `pg_cron` in Supabase oder einem Cron-Dienst, der die GitHub-Schnittstelle
`workflow_dispatch` für `wu-lunch-menus.yml` aufruft. Dafür ist ein GitHub-Zugriffstoken ("fine-grained", nur dieses Repository, Berechtigung
*Actions: Read and write*) nötig, das **nicht** ins Repository gehört. Der Import-Workflow ist darauf vorbereitet: Jeder manuelle oder externe
Start läuft sofort.

## Was passiert bei Fehlern? (Selbstkorrektur)

| Situation | Früher | Jetzt |
| --- | --- | --- |
| KI-Dienst kurz nicht erreichbar oder überlastet | Schritt scheitert, neuer Versuch frühestens am nächsten Tag | Bis zu drei automatische Wiederholungen mit Pausen im selben Lauf |
| KI-Antwort zur Mensa besteht eine Prüfung nicht (z. B. Preis im falschen Feld) | Ganze Mensa-Karte bleibt auf dem reduzierten Notstand | Bis zu drei Korrekturrunden: Das Modell bekommt dasselbe PDF, seine Antwort und den genauen Befund; das Ergebnis durchläuft wieder alle Prüfungen |
| KI-Lesung (Mensa-PDF, Finn-Bild) scheitert endgültig | Erst am nächsten Tag wieder | Ein weiterer Versuch am selben Tag nach 60 Minuten; bei geänderter Quelle sofort |
| Topf & Deckel: Browserabruf fällt aus oder Lauf startet zur "falschen" Stunde | Nur das Tagesmenü, restliche Woche leer | Der Browserabruf läuft bei jedem Import, bis alle fünf Tage geprüft vorliegen (Wiederholung nach 40 Minuten) |
| Mensa tauscht ihr PDF aus und die neue KI-Lesung scheitert | Volle Karte wurde durch die reduzierte Notauswertung ersetzt | Die geprüfte volle Karte der Woche bleibt stehen |
| Abschlussprüfung beanstandet **ein** Restaurant | Kein einziges neues Menü geht online | Nur dieses Restaurant behält seinen bisherigen Stand; alle anderen gehen online. Die Quelle wird beim nächsten Lauf neu ausgewertet |
| Ein einzelner Text lässt sich nicht geprüft übersetzen | Gar keine neue englische Übersetzung | Alle anderen werden gespeichert; nur dieser Text bleibt "English translation pending" (im Admin ergänzbar) |
| Während des Imports schreibt ein anderer Workflow ins Repository | Das fertige Ergebnis wurde verworfen und alles samt KI-Lesungen wiederholt (17.11.2026: korrekt gelesene Mensa-Karte ging verloren) | Das Ergebnis bleibt erhalten und wird auf den neuen Stand gesetzt (`scripts/publish_data.sh`); nur bei echter Überschneidung in Importdateien wird neu importiert |
| Die KI formuliert einen Hinweis anders ("Spezialpasta lt. Tagesaushang", "Änderungen vorbehalten.") | Ganze Mensa-Karte verworfen | Nur Warnungen, die Zweifel oder Widersprüche melden, blockieren; reine Hinweise nicht |
| GitHub startet einen Lauf Stunden zu spät | Lauf wird als "außerhalb des Fensters" verworfen | Lauf importiert trotzdem |

Unverändert gilt: **Nichts wird erfunden.** Eine Korrekturrunde ersetzt keine Prüfung – ein Preis, der nicht im Original steht, fällt weiterhin durch.
Bei einem Quellenproblem bleiben gültige Daten derselben Woche stehen; Menüs einer alten Woche werden nie als neue Woche gezeigt.

## Englische Übersetzung

Neue Gerichte werden **im Import selbst** übersetzt, unmittelbar nach der Abschlussprüfung und bevor die deutsche Karte online geht. Die
englische Fassung liegt damit schon bereit, wenn das Gericht erscheint. Scheitert die Übersetzung, erscheint die deutsche Karte trotzdem
pünktlich; der eigene Übersetzungs-Workflow (`wu-lunch-english.yml`) holt das Englische nach jedem Import und stündlich nach. Für im Admin
von Hand eingetragene deutsche Texte gilt weiterhin dieser Nachholweg.

## Wo sehe ich, was passiert ist?

- **Admin → Aktualisierung:** letzter echter Quellenabruf je Restaurant, Ergebnis (übernommen, unverändert, noch nicht veröffentlicht, Fehler, zurückgehalten) und Link zum Lauf.
- `status.json`: Zustand je Quelle und offene Probleme. `data/update-status.json`: tatsächlich ausgeführte Schritte des letzten Laufs.
- `data/menu-sanity-report.json`: Abschlussprüfung; `withheld` nennt zurückgehaltene Restaurants samt Grund.
- GitHub → Actions: "WU Lunch – Speisepläne aktualisieren" (Import) und "WU Lunch – Taktgeber" (Wächter).

Ein geplanter Termin ist kein Beleg für einen Abruf; angezeigt werden deshalb echte Abrufzeiten.

## Manuell starten

GitHub → Actions → "WU Lunch – Speisepläne aktualisieren" → "Run workflow". Der Lauf importiert sofort, unabhängig von der Uhrzeit.
Ohne Häkchen werden nur Restaurants geprüft, deren Wochenkarte noch nicht vollständig veröffentlicht ist; mit Häkchen
**"Alle Restaurants neu prüfen"** auch die bereits veröffentlichten.

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

## Robustheit gegen geänderte Karten (Stand 23.11.2026)

Anlass: Am Montag, 23.11.2026, fehlten Karma Food (WU) sowie Dok Khun und OX (Wels), obwohl die Karten auf den
Webseiten standen. Ursachen: ein vertipptes Enddatum im Wochenkopf, eine fehlende Jahreszahl, eine neue
Kartenform – und der Wels-Import lief seit Sonntagabend nicht mehr.

Grundsatz seither: **Der Beleg für die richtige Woche bleibt streng, alles andere ist nachsichtig.** Eine Karte
einer anderen Woche wird nie gezeigt. Tippfehler, fehlende Jahreszahlen, ein geschlossener Tag oder ein einzelnes
unvollständiges Gericht sperren aber nicht mehr das ganze Lokal.

Vier Schichten:

1. **Eigener Leser je Lokal** – liefert die beste Darstellung. Jeder Störfall wird mit der Originalquelle als
   Testfall hinterlegt (`scripts/fixtures/`), damit er nicht wiederkehrt.
2. **Ersatzleser (Wels, `generic_week` in `update_wels.py`)** – springt ein, wenn der eigene Leser scheitert und
   für die Woche noch nichts Gutes vorliegt. Er sucht nur Wochentage und übernimmt die Zeilen darunter wörtlich;
   er zeigt nichts ohne Beleg für die Woche (Zeitraum, Tagesdatum oder Kalenderwoche in der Karte). Zustand
   `fallback`.
3. **KI-Leser (Wels, `ai_week`)** – letzte Rückfallebene, wenn auch der Ersatzleser scheitert. Braucht das
   Secret `OPENAI_API_KEY`; je Kartentext höchstens ein Aufruf. Übernommen wird nur, was wörtlich in der Karte
   steht (Gerichtnamen und Preise werden im Text gesucht); den Beleg für die Woche prüft der Code, nicht das
   Modell. Probelauf ohne Veröffentlichung: Workflow „Wels – Mittagsmenüs aktualisieren" mit `ki_probe`.
4. **Störungsmeldung (`scripts/report_problems.py`)** – läuft nach jedem Import. Für jede anhaltende Störung
   gibt es genau ein offenes GitHub-Issue mit dem Etikett `import-stoerung` (E-Mail an den Betreiber); es
   schließt sich selbst, sobald die Karte wieder gelesen wird. „Noch nicht veröffentlicht“ ist keine Störung.

Weitere Regeln aus der Durchsicht vom 23.11.2026:

- **Startdatum belegt die Woche** (`week_identity`): Ein vertipptes Enddatum sperrt weder Mensa noch Topf & Deckel,
  Karma Food oder Grüne Hütte. Beginnt ein Plan nach einem Feiertag später in der Woche, zählt er nur mit der
  passenden Kalenderwoche.
- **Geschlossene Tage:** Ein Feiertag bleibt als leerer Tag stehen und sperrt nicht die Woche – bei Mensa und Finn
  nur, wenn Plan bzw. Bildlesung den Tag ausdrücklich als geschlossen nennen; überall gelten mindestens drei
  gefüllte Tage. Wie Mensa und Topf & Deckel einen Feiertag tatsächlich drucken, war noch nicht zu sehen
  (erster Fall: 8.12.2026) – der tägliche Selbst-Check prüft diese Woche mit.
- **Einzelne auffällige Gerichte** (`candidate_quality_gate`, Karma, Baschly): Ein unbrauchbarer Name wird
  weggelassen, ein unmöglicher Preis entfernt; erst mehrere solche Einträge sperren die Karte.
- **Karte ohne Datum (Baschly):** gilt erst als Karte der neuen Woche, wenn sie sich gegenüber der zuletzt gezeigten
  geändert hat (`undated_card_is_stale`, Feld `shown_week` im Status). Vorher „noch nicht veröffentlicht".
- **Stille Fälle:** Die Störungsmeldung meldet ab Dienstag 8 Uhr jedes Lokal ganz ohne Karte für die Woche,
  zurückgehaltene Freigaben, anhaltende Mensa-KI-Fehler und ab drei Fehlversuchen den Browser-Import von
  Topf & Deckel.
- **Wels-Lauf:** setzt immer auf dem aktuellen `master` auf und veröffentlicht ohne Rebase (zwei kurz
  aufeinanderfolgende Läufe führten am 23.11.2026 zu einem Konflikt).

Auslöser: Vom Taktgeber gestartete Importe lösen bei GitHub keine `workflow_run`-Folgeläufe aus. Der Import
startet den Wels-Import und die englischen Menüs deshalb im letzten Schritt ausdrücklich.

## Leseübung an fremden Karten (seit 23.11.2026)

Damit die allgemeinen Leser immer mehr Kartenformen kennen, üben sie jede Woche an Wochenkarten von Lokalen,
die WU Food gar nicht zeigt (`wu-lunch/practice/sources.json`, derzeit 16 Karten aus ganz Österreich).

1. **Dienstags** holt der Workflow „WU Lunch – Leseübung an fremden Karten“ die Karten. Der Ersatzleser (Regeln)
   und der KI-Leser lesen jede Karte unabhängig; der KI-Leser dient als Vergleichslesung und darf nur übernehmen,
   was wörtlich in der Karte steht.
2. Je Karte gibt es ein Urteil: `einig`, `mehr_gelesen` (der Ersatzleser nennt alles aus der Vergleichslesung und
   dazu mehr, etwa Vorspeise oder Wochengericht), `nur_ki` (der Ersatzleser scheitert, die Karte ist lesbar – der Lernfall),
   `uneinig`, `beide_gescheitert`, `andere_woche` (alte Karte, kein Lesefehler), `abruf_fehlgeschlagen`.
3. **Mittwochs** wertet Claude die Fälle aus, verbessert den Ersatzleser mit allgemeinen Regeln (nie mit
   Sonderregeln für ein Übungslokal) und hält geprüfte Karten als feste Tests fest (`practice/expected`).
4. Die Punktetafel (`practice/scoreboard.json`) wird über alle gespeicherten Karten neu berechnet
   (`python3 wu-lunch/scripts/practice.py --rescore`). So sieht man, ob eine Verbesserung wirkt – und die
   bestehenden Tests zeigen, dass kein gelistetes Lokal darunter leidet.

Quellen sind ausschließlich die eigenen Webseiten der Lokale. Sammelportale wie mittag.at werden nicht gelesen:
Deren Nutzungsbedingungen untersagen das automatische Auslesen (Stand 23.11.2026); ein Zugang wäre nur über
eine Anfrage bei mittag.at möglich.

Erste Runde (23.11.2026, nur Ersatzleser): 8 von 14 erreichbaren Karten gelesen, nach vier allgemeinen
Verbesserungen 11 von 14 (Zeitraum mit „bis“, Datum ohne Jahr, Aufzählungszeichen, Preiszeile mit Zusatz;
Urlaubshinweise im Seitenkopf gelten nicht mehr als Kartenwoche). Bekannte offene Fälle: zweispaltige PDFs
(Menü 1 / Menü 2 nebeneinander), PDFs mit verwürfelter Lesereihenfolge, Gericht vor der Tagesüberschrift.

Zweite Runde (23.11.2026, mit Vergleichslesung): Von 15 lesbaren Karten waren zunächst 6 einig und 4 uneinig.
Aus den vier Abweichungen gelernt (alles allgemeine Regeln im Ersatzleser):

- mehrere Menüblöcke mit denselben Wochentagen direkt hintereinander („Menü 1 / Menü 2“) gehören zur selben Woche;
- nennt eine Seite jedes Gericht zusätzlich direkt vor der Tagesüberschrift, zählt diese Zeile nicht zum Vortag;
- ein Wochengericht hinter dem letzten Tag („Vegetarische Alternative“) gilt an jedem Tag;
- Trennzeilen („***“) beenden die Karte nicht; Gerichte aus einem Wort („Käsespätzle“) zählen; Linktexte
  („… als PDF laden“) und Datumsbruchstücke sind keine Gerichte.

Danach: 7 einig, 2 mehr gelesen, 1 uneinig. Fünf Karten sind von Hand geprüft und feste Tests (`practice/expected`).

Die verbleibende Abweichung (Gericht steht VOR der Tagesüberschrift, ohne Wiederholung) lässt sich mit Regeln nicht
sicher erkennen. Deshalb fragt der Wels-Import in der Rückfallebene jetzt **beide** Leser: Sind sie sich einig (oder
hat der Ersatzleser nur mehr gelesen), gilt der Ersatzleser; weichen sie ab, gilt die wörtlich geprüfte KI-Lesung;
belegt die KI-Lesung eine andere Woche, wird nichts gezeigt. Je Kartentext bleibt es bei höchstens einem KI-Aufruf.

