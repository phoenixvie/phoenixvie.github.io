# WU Lunch – automatisierte Qualitätskontrolle und KI-Reparatur

## Betriebsmodus (Stand: 6. November 2026; 11 Restaurants)

Das werktägliche GitHub Actions-Importverfahren bleibt Hauptdatenquelle. Nach den
bestehenden Parsern und dem **Playwright-Import aller Topf-&-Deckel-Tabs** wird
um **11:15 Wiener Zeit** beziehungsweise bei manuellem Workflowstart
die separate Mensa-PDF-KI und danach der begrenzte Restaurant-Repair-Agent
ausgeführt.

Der Agent ruft die vorhandene `ai-pilot/ai_direct.py`-Extraktion mit den direkt
heruntergeladenen Originalquellen auf. Er verwendet die GitHub-Actions-Secret
`OPENAI_API_KEY` und standardmäßig `gpt-6-luna`. **Ohne Secret werden
keine KI-Anfragen durchgeführt**; der reguläre Import bleibt bestehen.

### Behandlung aller elf Restaurants

| Restaurant | Primärer Abruf | KI und Repair |
| --- | --- | --- |
| Mensa | Original-PDF | `scripts/update_mensa_ai.py` prüft das PDF separat |
| Topf & Deckel | Playwright (alle fünf Tabs) | Browser-Import; KI-Audit zeigt offene Probleme, keine HTML-Tab-Fantasie |
| Lia | HTML-Parser | Luna prüft und ergänzt ausschließlich direkt belegte Preise |
| Das Campus | HTML-Parser | Luna prüft und ergänzt ausschließlich direkt belegte Preise |
| Glashaus | HTML-Parser | Luna prüft und ergänzt ausschließlich direkt belegte Preise |
| Grüne Hütte | HTML-Parser | Luna prüft und ergänzt ausschließlich direkt belegte Preise |
| Baschly | Zwei Produktseiten | Luna prüft; nur bestätigte Preise automatisch ergänzbar |
| L’Osteria | Saisonkarte | Luna-Vergleich; keine automatische Umschreibung der Saisonkarte |
| Oma Küche | Wiederkehrendes Angebot/Foto | Datenqualität überwachen; Foto-/Aushangpreise erfordern manuellen Beleg |
| Karma Food (Messe/Prater) | Datierte HTML-Tage und offizielle Preis-PDF | HTML/PDF-Abgleich, getrennte Hauptgericht-/Special-/Lunch-Combo-Preise; keine Veröffentlichung für falsche Woche |
| Finn | Offizielle Shopify-Wochenkarte als Bild | Erst richtige ISO-KW, Bildversion und Datum prüfen; dann zwei unabhängige Bildanalysen mit kompletter Übereinstimmung, sonst keine Veröffentlichung |

Pro normalem Lauf werden höchstens **zwei** HTML-Restaurants mit Luna analysiert.
Dringende Fehler werden priorisiert, wiederkehrende Fehler rotiert, übrige Quellen
stichprobenartig geprüft. Mensa, Topf & Deckel, Karma Food und Finn folgen ihren dedizierten Abläufen;
die kostenpflichtigen Mensa-PDF-Aufrufe sind zusätzlich begrenzt auf die
noch nicht erfolgreich verifizierte Woche.

### Automatische Änderung – bewusst eng begrenzt

Ein bestehendes Gericht mit `price: null` darf **nur** dann einen Preis erhalten,
wenn *alle* Prüfungen erfüllt sind:

1. Exakter Restaurant-, Tages-, Gerichts- und Portionsabgleich.
2. Echte, vollständig abgerufene und unveränderte offizielle HTML-Quelle.
3. Von Luna benanntes Zitat steht normalisiert **wörtlich** im Quelltext.
4. Zitat nennt das konkrete Gericht und genau **einen** eindeutigen EUR-Preis;
   nicht bloß einen allgemeinen, möglicherweise fremden Tarif.
5. Gültigkeit der Kalenderwoche wird **unabhängig von Luna** aus dem Original
   oder über einen Parser mit eigener Datumsprüfung festgestellt.
6. Keine Duplikate, kein existierender bestätigter Preis, keine
   unklaren Modellwarnungen; Schema und Menüoptionen bleiben intakt.

Quelle, Textbeleg, Quell-Hash und Prüfungstyp werden im Gericht protokolliert.
Der nachgelagerte Standardparser übernimmt dokumentierte Preise bei
`price: null` nicht erneut als `null` (gleiches Datum, gleicher Name).
Eine neue **explizite** Preisangabe aus der offiziellen Quelle hat Vorrang.

Alles andere ist **nur Diagnostik**: neue Gerichte, fehlende Wochentage,
abweichende Preise, Suppen, Salate, Inklusivleistungen, Saisonkarten,
Fotos und Layoutänderungen werden **nicht** auf Basis einer einzelnen
KI-Antwort in der Live-Datenbank geändert. Bei unklaren Ergebnissen
bleibt die aktuelle Woche erhalten; eine alte Woche wird nicht umetikettiert.

### Reports

- `wu-lunch/status.json`: `ai_repair` mit letztem Datum, Modell,
  Aktion, Anzahl Ergänzungen und etwaigem Fehler; bestehende
  `sources`-Fehlerhistorie bleibt unverändert.
- `wu-lunch/data/repair-report.json`: letzter detaillierter Lauf,
  erkannte Probleme, KI-/Parser-Differenzen, geprüfte Quellen-Hashes,
  Reparaturen und Tokenverbrauch (nur öffentliche Speisekarten).
- Die bestehenden Warnungen bleiben aktiv; insbesondere `source_error`,
  fehlende Preise und Tage.
- Automatische Codeänderungen oder selbstständige GitHub-PR-Merges
  erfolgen **nicht**. Für echte Parserdefekte ist ein separat getesteter
  und freigegebener Patch erforderlich.

### Tests und manueller Betrieb

Offline-Tests:

```bash
pip install -r wu-lunch/requirements.txt
python -m unittest discover -s wu-lunch/scripts -p 'test_*.py' -v
```

Ein bestimmtes Restaurant prüfen (kostet bei HTML eine Modellanfrage):

```bash
OPENAI_API_KEY=... python wu-lunch/scripts/repair_menus_ai.py --restaurant lia --max-calls 1
```

Alle elf im Bericht prüfen (höchstens sechs reguläre HTML-KI-Analysen,
die anderen folgen dem PDF-/Browser-/Aushangpfad):

```bash
OPENAI_API_KEY=... python wu-lunch/scripts/repair_menus_ai.py --restaurant all --max-calls 9
```

**Grenze:** Eine exakt wiedergefundene Textpassage beweist nicht jede visuelle
Tabellen- oder Preiszuordnung. Deshalb veröffentlicht der Agent nicht
ungeprüft vollständige Menükarten. Unabhängige stichprobenartige Sichtkontrollen
bleiben sinnvoll. Kosten/Qualität anhand realer Läufe kontrollieren,
bevor der Einsatz ausgeweitet wird.

### Häufigere Montagsprüfungen

- Montag stündlich **06:15–18:15 Uhr** Wiener Zeit (13 Prüfungen), auch früh vor 08:00 Uhr.
- Dienstag bis Freitag weiterhin stündlich **08:15–12:15 Uhr** (fünf Prüfungen).
- GitHub-Actions-Zeitpläne sind Best-Effort und können sich aufgrund von Auslastung verspäten.
- Die Quellen werden mehrfach abgefragt, **KI nicht automatisch in jedem Lauf**: Finn nur bei neuem eindeutig aktuellem Bild; HTML-Reparatur und Mensa-KI regulär um 11:15 Uhr.
- Vorab veröffentlichte Menüs der *Folgewoche* werden nicht der laufenden Woche zugewiesen. Das ist bei Karma Food am Freitag, 06.11.2026 bereits vorgekommen (09.–13.11.2026).
