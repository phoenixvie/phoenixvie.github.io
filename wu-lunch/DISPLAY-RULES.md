# Dauerhafte Anzeigeregeln

Betreibervorgaben vom 10.11.2026, für Webseite und App-Webvorschau. Änderungen
betreffen die Präsentation; importierte Originaldaten und Quellbelege bleiben
erhalten. Diese Regeln gelten für neue Wochen, nicht nur für bestimmte Gerichte.

- Mensa: Ausgabe 1+2 = Veggie und Ausgabe 3+4 = Meaty jeweils mit der benannten
  Tagessuppe, ohne deren Preis zum Hauptgerichtpreis zu addieren. Ausgabe 5, 6 und 7 werden ausgeblendet. Suppe und Hauptgericht stehen
  jeweils in getrennten Zeilen.
  Ausgabe 8 bleibt Global & Grill. Keine separate Tagessuppe, kein Soup Deal,
  keine Smart-Menüoption anzeigen.
- Baschly: Hauptgericht und „Mit Tagessuppe oder kleinem Salat“ beibehalten.
- Finn: nur das Hauptgericht als Menü mit Tagessuppe zum bestätigten
  Kombinationsgesamtpreis anzeigen. Einzelgericht, separate Suppe/Salat und
  zusätzliche optionale Menüzeile ausblenden. Fehlenden Kombipreis nicht raten.
- Finn: „und grünem Salat“ aus dem Gerichtnamen in die Unterzeile
  „Mit Tagessuppe und grünem Salat“ verschieben, falls der Salat im
  Originalgericht genannt ist. Kein Salat zu anderen Gerichten erfinden.
  Finn behält den bestätigten Kombipreis.
- Lia: keine zusätzliche Suppe/Salat und keine entsprechende Unterzeile;
  grünen Salat aus der bisherigen Beilagenformulierung entfernen. Menüpreis erhalten.
- Karma Food: erklärende Preisbestätigungs-/Rabatt-/Kombitexte entfernen.
- Campus: unverändert, bestehende feste Tarife gelten weiter.
- Topf & Deckel: Suppe ohne Preis und Verkaufskommentar. Light/Big Lunch zu einer
  Zeile „Hauptgericht (klein/groß) + kleine Suppe/Salat, Getränk oder Dessert“
  zusammenfassen, beide bestätigten Gesamtpreise erhalten. Hauptgerichte mit
  „(klein / groß)“, ohne das Wort „Preis“. Haussalat und Dessert ausblenden.
- Oma Küche: „All-you-can-eat-Buffet“, ohne Erwachsenen-, Uhrzeit- und To-go-Text.
- Grüne Hütte: Suppennamen ohne „Suppen zur Auswahl:“, in derselben Textzeile „Optional zum
  Tagesteller“, separaten Suppenpreis erhalten. Aufpreistext an Hauptgerichten
  ausblenden.
- Glashaus und L’Osteria: unverändert, einschließlich ihrer Beschreibungen.

Die umgesetzten Funktionen `restaurantDisplayRules` und `mensaStations` müssen
in beiden Ansichten übereinstimmen; Regressionstests prüfen diese Gleichheit.

- Allgemein: Allergene niemals anzeigen; identische Mensa-Gerichte je Kategorie
  und Preis deduplizieren. Beef und Planted werden bei gleichem Preis als Alternativen in einer Burger-Zeile zusammengefasst.
- App-Restaurantwebseite: voller Inhaltsbereich ohne App-Kopfzeile, unten nur
  ein mittiger Zurück-Button. HTTP-Webseiten und PDFs intern öffnen; Telefon
  und Mail bleiben Systemaktionen.
- Freigegebene Live-Daten alle drei Sekunden ohne parallele Abrufe prüfen und
  beim Wiederöffnen aktualisieren. Die App lädt ihre Weboberfläche online,
  mit eingebauter Oberfläche als Rückfall. Dafür ist einmal eine neue APK nötig.
