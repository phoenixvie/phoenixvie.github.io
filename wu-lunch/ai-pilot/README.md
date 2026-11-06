# WU Lunch – isolierter KI-Direktimport (Pilot)

**Zweck:** Vergleich der bestehenden deterministischen Extraktion mit einer tatsächlichen
KI-Extraktion aus den **Original-HTML-Seiten bzw. dem originalen Mensa-PDF**.

## Trennung vom Live-System

Dieser Test importiert **niemals** nach wu-lunch/data/menus.json,
wu-lunch/data.js oder wu-lunch/status.json. Er verwendet keine
restaurant-spezifischen Extraktions-/Preisparser. Die HTML-Bereinigung mit
BeautifulSoup entfernt lediglich Navigation, Skripte und unsichtbare Elemente;
Überschriften, Tabellen, Text und Preisnachbarschaft bleiben erhalten.

- Code: wu-lunch/ai-pilot/ai_direct.py
- GitHub Action: .github/workflows/wu-lunch-ai-pilot.yml
- **Eigene Ergebnisansicht:** https://phoenixvie.github.io/wu-lunch/ai-pilot/results/latest.html
- **JSON-Ergebnis:** https://phoenixvie.github.io/wu-lunch/ai-pilot/results/latest.json
- Zusätzlich gibt es in jedem gestarteten GitHub-Run ein herunterladbares Artefakt.
- Der normale Workflow .github/workflows/wu-lunch-menus.yml läuft unverändert weiter.

## Einmalige Einrichtung

1. OpenAI-API-Abrechnung in https://platform.openai.com/ einrichten.
2. In **Repository Settings → Secrets and variables → Actions → New repository secret**
   einen Schlüssel mit Namen **OPENAI_API_KEY** hinzufügen. **Niemals hier, im Chat,
   im Quellcode oder in den GitHub-Issues eintragen.**
3. Auf GitHub unter **Actions → WU Lunch – KI-Direktanalyse (getrennter Test)**
   → **Run workflow** die Auswahl **all** (alle elf Restaurants) und
   **gpt-6.1-terra** (gründlicher) oder **gpt-6-luna** (günstiger) treffen.
4. Nach erfolgreichem Lauf den eigenen Ergebnisbericht öffnen. Pro Restaurant
   werden KI-Vorschlag, Originalbelege, Quellen, Warnungen, Preis- und
   Namensvergleich sowie Produktionsdaten getrennt angezeigt.

## Grenzen, Datenschutz, Kosten

- **Kein automatischer KI-Zeitplan:** Ein Lauf wird ausschließlich manuell gestartet.
  Bei einem Push werden nur Offline-Tests ausgeführt, **keine API-Aufrufe**.
- Maximal **11 Modellaufrufe** bei restaurant=all (je ein Aufruf pro Restaurant).
  Quell-HTML ist auf 70.000 Zeichen je URL begrenzt. Mensa-PDF als Original.
- Preis- und Gerichtsbelege sind KI-Vorschläge, nicht automatisch korrekt.
  Unbekannte Preise bleiben null; verdächtige Preise, Daten und Quellen werden
  markiert. Kein KI-Ergebnis wird als produktives Menü veröffentlicht.
- Das KI-Modell erhält die öffentlich zugänglichen Menüinhalte. Die Daten werden
  **über die OpenAI-API** übertragen; store=false wird gesetzt.
- Das Report-HTML/JSON liegt anschließend **öffentlich im GitHub-Pages-Repository**.
  Es enthält öffentliches Restaurantmaterial und Modellresultate, keine API-Schlüssel.
- PDF-Bildanalyse kann zusätzliche Bild-Token verbrauchen. Größenlimits und eine
  Anfrage je Restaurant sind implementiert; ein Ausgabenlimit sollte zusätzlich
  im API-Konto gesetzt werden.
- Der Bericht wird bei jeder Ausführung überschrieben; das GitHub-Artefakt bleibt
  für 30 Tage abrufbar. Fehlgeschlagene Abfragen erscheinen im Bericht.
- HTML mit dynamisch nachgeladenen Gerichten und Bild-Speisekarten kann fehlen.
  Dieser Pilot ist kein Headless-Browser oder OCR-Crawler; das Original-Mensa-PDF
  wird dagegen direkt durch das multimodale Modell interpretiert.
- Für Oma Küche kann die Webseite weniger Details liefern als die im normalen Import
  verwendete Foto-Vorlage. Der Pilot soll **nichts aus diesem Foto erfinden**.

## Validierung

Offline-Tests im GitHub-Workflow (und manuell per unittest discover im ai-pilot-Verzeichnis).

Nach der Auswertung kann entschieden werden, ob einzelne Restaurant-Parser
durch KI-Direktextraktion ersetzt oder nur ergänzt werden sollen.

## Karma Food und Finn (neu)

Der Produktionsworkflow verwendet für Karma Food den datierten HTML-Wochenplan
**und** die offiziell verlinkte PDF zur Kontrolle der Standard-/Specialpreise.
Für Finn werden die Original-JPEG-Bilder über
`scripts/update_new_restaurants.py` geprüft: aktuelle ISO-KW, plausibler
Shopify-Uploadzeitpunkt, Abgleich durch Luna und Terra, nötigenfalls ein
dritter Kontrolllauf. Der isolierte `ai_direct.py`-Pilot liest Finn-Bilder
nicht automatisch aus; die produktive Bildanalyse erfolgt ausschließlich
über den gesonderten, geprüften Importpfad.
