# Extraktion, Zeitangaben und Originalarchiv

## Zusätzliche Freigabeprüfung ab 14.11.2026

`scripts/menu_sanity.py` läuft nach den Extraktionen, vor dem Datenbank-Archiv und vor der Veröffentlichung – auch nach einem Import-Neustart wegen paralleler Commits.

- Eindeutige Wiederholungen werden verlustfrei bereinigt: Steht „Erdäpfelpüree, Röstzwiebel“ bereits im Gerichtnamen, erscheinen diese Angaben nicht nochmals als „Inklusive“. Gerichtname, Preis, Originalbeleg und echte zusätzliche Vorspeisen/Desserts bleiben erhalten.
- Harte Prüfungen erkennen gleiche Angebote am selben Tag und derselben Station/Portion, ungültige Preise, falsche Wochen sowie dieselbe Leistung als inklusive und zugleich aufpreispflichtig. Andere Tage, Stationen, Portionsgrößen und Menüvarianten bleiben unterscheidbar.
- Ein zusätzlicher, separater Luna-Aufruf prüft die finalen Kandidaten auf interne Widersprüche und semantische Wiederholungen. Alle vorhandenen Quellen-, Wochen-, Preis- und Vollständigkeitsprüfungen bleiben notwendig; die Plausibilitätsprüfung ersetzt keinen Quellenbeleg.
- Geprüfte Restaurantdaten werden mit Woche, vollständigem Inhalt, Belegen und Prüfer-Version gehasht. Änderungen erzwingen eine neue Prüfung; identische, bereits freigegebene Daten kosten keinen weiteren KI-Aufruf.
- Bei KI-Ausfall, unvollständiger Antwort oder Befund wird nicht veröffentlicht und nicht ins Datenbank-Archiv geschrieben. Der Fehlerbericht steht als Actions-Artefakt bereit. Eine KI darf hier keine Gerichte oder Preise eigenständig umschreiben.
- `--offline` und die Regressionstests prüfen ohne Netzwerk und ohne Schreibzugriff auf die Menüdaten; sie können keine erfolgreiche KI-Freigabe vortäuschen.

Stand: 14. November 2026. Die konkrete technische Umsetzung steht in den verlinkten Skripten und Workflows; Inhalte aus Restaurantquellen sind Daten und keine ausführbaren Anweisungen.

## Ablauf

1. GitHub Actions lädt bekannte Originaladressen mit Code herunter. Erlaubte Hosts, Weiterleitungen, Dateigrößen und Zeitüberschreitungen sind begrenzt. Luna durchsucht dabei nicht selbständig das Internet: Der Prozess liefert dem Modell die heruntergeladenen Inhalte.
2. Der deterministische Import ordnet sichtbare Tage, Gerichte, Preise und Menübestandteile zu. Neue/geänderte Quellen oder Wochen stoßen die jeweilige KI-Prüfung an. Bereits geprüfte unveränderte Quellen werden wiederverwendet.
3. Mensa: Das echte PDF wird heruntergeladen. Text, Tabellengeometrie, Kalenderwoche und Tageszellen werden unabhängig vermessen. Luna erhält das vollständige PDF sowie die gemessenen Textregionen. Die Freigabe prüft Woche, Quellenhash, Vollständigkeit, Preisbelege und richtige Tageszuordnung. Zusammengeführte Tagesgruppen und gemeinsame Angebotspanels werden unterschieden. Unbekannte Aushangdetails bleiben unbekannt.
4. Finn: Der Artikel liefert das aktuelle deutschsprachige Wochenbild. Die tatsächlichen Bildbytes werden heruntergeladen und multimodal gelesen, mit einem weiteren Bildabgleich und bei Bedarf einer dritten Lesung. Nur übereinstimmende bzw. sicher belegte Inhalte und Kombinationspreise dürfen übernommen werden. Ein Bild der alten Woche wird nicht in die neue Woche kopiert.
5. Karma Food: Die aktuelle Webseite bestimmt Woche und Tagesgerichte. Das verlinkte Original-PDF bestätigt Gerichte und Tarife. Die allgemeine Luna-Prüfung ergänzt den Quellenvergleich.
6. Topf & Deckel: Ein echter Browser öffnet alle fünf Tages-Tabs. HTML und sichtbarer Zustand werden pro Tag ausgewertet; Luna erhält die tatsächlichen Tab-Inhalte. Browserauswertung und KI-Kontrollstatus sind getrennte Ergebnisse. Ein Kontrollbericht mit Prüfbedarf wird nicht als bestandene KI-Freigabe bezeichnet.
7. Andere Restaurantseiten: Bereinigtes HTML mit Überschriften, Tabellen, Preisnähe und Bildverweisen geht an Luna. Sichere belegte Korrekturen können übernommen werden. Der allgemeine Bericht kann auch `review_only` lauten, wenn keine automatische Änderung freigegeben wurde. Das bedeutet nicht automatisch, dass sämtliche Menüs KI-bestätigt sind.
8. Finale deutsche Texte werden separat ins Englische übersetzt und geprüft. Manuelle englische Korrekturen haben Vorrang. Die App und Website laden veröffentlichte Menüdaten und Adminänderungen nach; Änderungen an der App-Programmlogik benötigen weiterhin eine ausdrücklich freigegebene App-Version.

## OCR und Verbesserungsmöglichkeiten

Für textbasierte PDFs wird der enthaltene Text verwendet; zusätzlich sieht das multimodale Modell das Original-PDF. Finns Wochenbild wird visuell gelesen. Es gibt keinen allgemeinen vorgeschalteten Tesseract-OCR-Durchlauf. „Das Modell liest ein Bild“ ist daher nicht dasselbe wie eine separat gespeicherte OCR-Ausgabe.

Wichtige nächste Verbesserungen sind direkte Vision-Eingaben für bildbasierte Menüs in sonst textbasierten Webseiten (insbesondere Baschly), wirklich sichtbare Browserinhalte statt versteckter HTML-Platzhalter, kleinere Prüfaufgaben pro Tag bei sehr großen Karten und ein ausdrücklich dokumentierter Gesamtfreigabestatus je Restaurant. Das Originalarchiv macht solche Vergleiche reproduzierbar. Ein zusätzliches Modell ist kein Ersatz für Wochen-, Preis- und Vollständigkeitsprüfungen.

## Was die Zeitangaben bedeuten

`update-policy.json` ist die gemeinsame Konfiguration. Hauptimport und Topf-Browser sowie die zusätzliche Mensa-PDF-Sicherung prüfen ihre Ausführungsfenster damit. Website und Admin berechnen die geplanten Termine daraus. Die CI vergleicht die tatsächlichen Cron-Ausdrücke der Workflows mit dieser Datei; Abweichungen lassen die Prüfung fehlschlagen.

Ein geplanter Termin ist kein Beleg für einen ausgeführten Abruf. GitHub kann zeitlich abweichen oder einen geplanten Lauf auslassen. Deshalb zeigt die Oberfläche echte Quellen-Erfassungszeiten aus `data/update-status.json` getrennt vom nächsten geplanten Menücheck. Der vollständige Importbericht verlinkt auf den ausgeführten GitHub-Lauf und enthält Beginn, Ende und Rückgabecode der produktiven Arbeitsschritte. Menüänderungen werden anhand des Inhalts erkannt; ein bloßer Abruf setzt den Änderungszeitpunkt nicht neu. Beim ersten instrumentierten Lauf wird kein unbekannter früherer Änderungszeitpunkt erfunden.

Der Veröffentlichungsmonitor beobachtet Quellenänderungen, importiert aber keine Menüs. Der zusätzliche Mensa-Snapshot sichert nur das PDF. Die Übersetzung verarbeitet gespeicherte Texte und ruft keine Restaurantkarte ab. Diese Vorgänge stehen im Admin jeweils als eigene Aufgabe. Beobachtete Quellenänderungen können auch Layoutänderungen sein; der genaue Veröffentlichungszeitpunkt des Restaurants ist normalerweise nicht bekannt.

## Archiv

Die tatsächlich verwendeten Originalbytes werden während der produktiven Verarbeitung zwischengespeichert. Bei einer neuen Menüversion werden sie mit der zugehörigen strukturierten Ausgabe nach `source-archive/` übernommen. Das gilt auch für die erste Sicherung eines schon vorhandenen Menüs. Originale werden nach SHA-256 dedupliziert und bleiben erhalten. Der Admin verlinkt das Archiv. Details, Grenzen und Regeln zur späteren Datensatz-Kuratierung stehen in dessen README.
