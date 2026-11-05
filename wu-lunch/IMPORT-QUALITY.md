# WU Lunch – Regeln für Quellen und Vollständigkeit

## Datenmodell

Jede Speise erhält einen **eigenen Eintrag** mit folgenden Feldern:
- `name` (Hauptgericht, keine Beilage in diesem Feld), `category`, `price`, `diet`, `description`, `allergens`
- `included_soup`: **konkreter Name** der Tagessuppe, wenn ausdrücklich veröffentlicht; sonst `null`
- `included_choices`: **alle wählbaren Inklusivleistungen**, z. B. `["Tagessuppe","kleiner Salat"]` oder `["Suppe","Salat"]`.
- Die Auswahl ist ein logisches **oder**, nicht **und**. Keinesfalls die Suppe als zusätzlich kostenlosen Bestandteil darstellen, wenn nur ein Aufpreis-/Upgrade-Menü angeboten wird.

## Verbindlicher Ablauf beim Hinzufügen eines Restaurants

1. Alle relevanten Quellen inklusive Unterseiten und PDF-Verlinkungen auffinden, **gültigen Zeitraum** auf jedem veröffentlichten Plan prüfen.
2. Nicht nur Hauptgerichte und Preise, sondern systematisch **Suppen, Salate, Beilagen, freie Auswahl, Extras, Vorspeisen, Getränke und Upgrade-Konditionen** prüfen; dabei kostenlos inkludiert und aufpreispflichtig strikt trennen.
3. Pro Wochentag alle Optionen strukturiert im JSON speichern. Nicht nur Beschreibungstext hinterlegen, wenn die öffentliche Anzeige ihn sonst nicht zeigt.
4. Parserfixture mit echten HTML- oder PDF-Ausschnitten erstellen, mindestens einen Regressionstest pro Besonderheit inklusive Negativfall (Fehler bei fehlendem Menübestandteil).
5. Prüfung gegen Livequelle und gegen dargestellte Webseite durchführen. Bei fehlendem Datum, verdächtig kurzer Ausgabe, fehlender Inklusivleistung oder widersprüchlichen Angaben **keine automatische Verifikation**.
6. Bei neuem Restaurant bewusst die jeweilige Aktualisierungshäufigkeit konfigurieren: datierte vollständige Wochenpläne einmal pro Woche, Tagesspecials täglich, Saisonkarten in längeren Intervallen.
7. Einheitliche Anzeige: `[konkrete Suppe] oder [Salatoption] + [Hauptgericht]`; bei nicht genannter Suppe `Suppe oder Salat + [Hauptgericht]`. Falls Extras nur gegen Aufpreis: Preis und Bedingung ausdrücklich separat darstellen. Kein stilles Ersetzen von `oder` durch `und`.
8. Visuelle Änderungen nur nach ausdrücklichem Wunsch; Parser und UI bleiben entkoppelt.

## Mensa-PDF

- Layoutdaten mittels PyMuPDF **Wort-Bounding-Boxes** innerhalb geometrisch definierter Tagesspalten erfassen; Preise/Allergene und Smart-Menü-Werbebanner separat behandeln.
- Kalenderwoche und Gültigkeitsdatum **aus PDF-Inhalt** prüfen, niemals HTTP-Verfügbarkeit oder PDF-URL als Aktualitätsbeleg verwenden.
- Geometrische Extraktion mit Regressionstests, Spaltenzuordnung, Mindestabdeckung und Vergleich vorheriger bestätigter Daten.
- Bei Qualitätsfehlern bisherige bestätigte Wochenwerte erhalten (keine alte Woche als neue), Status `degraded` und Kontrollbericht erstellen.
- Zweite Option bei komplizierten PDFs: PDF-Seite als Bild rendern und mit visueller Tabelle-/Layoutanalyse **nachprüfen**; nicht ungeprüft durch OCR ersetzen.
- Mehrfache Abrufe derselben bereits bestätigten Woche vermeiden. Ein erneuter Download nur bei nicht verifiziertem Plan oder geänderter Quelle.

## Monitoring

GitHub Actions führt werktags den Import aus. ChatGPT-Aufgabe kontrolliert nachgelagert `status.json`, die ausgelieferten JSON-Daten und die App. Nur ungelöste oder kritische Probleme per Mail melden; gleiche Meldung nicht täglich wiederholen. Die HTML-Oberfläche darf durch Datenimporte nicht überschrieben werden.
