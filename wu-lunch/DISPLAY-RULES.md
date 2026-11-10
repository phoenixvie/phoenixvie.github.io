# Dauerhafte Anzeigeregeln

Betreibervorgaben vom 10.11.2026, für Webseite und App-Webvorschau. Änderungen
betreffen die Präsentation; importierte Originaldaten und Quellbelege bleiben
erhalten. Diese Regeln gelten für neue Wochen, nicht nur für bestimmte Gerichte.

- Mensa: Ausgabe 1+2 = Veggie und Ausgabe 3+4 = Meaty jeweils mit der benannten
  Tagessuppe, ohne deren Preis zum Hauptgerichtpreis zu addieren. Ausgabe 5 nur
  „Pizza“, Ausgabe 6 nur „Pasta“, Ausgabe 7 nur „Bowl“, ohne Detail-/Preislisten.
  Ausgabe 8 bleibt Global & Grill. Keine separate Tagessuppe, kein Soup Deal,
  keine Smart-Menüoption anzeigen.
- Baschly: Hauptgericht und „Mit Tagessuppe oder kleinem Salat“ beibehalten.
- Finn: nur das Hauptgericht als Menü mit Tagessuppe zum bestätigten
  Kombinationsgesamtpreis anzeigen. Einzelgericht, separate Suppe/Salat und
  zusätzliche optionale Menüzeile ausblenden. Fehlenden Kombipreis nicht raten.
- Lia und Karma Food: erklärende Preisbestätigungs-/Rabatt-/Kombitexte entfernen.
- Campus: unverändert, bestehende feste Tarife gelten weiter.
- Topf & Deckel: Suppe ohne Preis und Verkaufskommentar. Light/Big Lunch zu einer
  Zeile „Hauptgericht (klein/groß) + kleine Suppe/Salat, Getränk oder Dessert“
  zusammenfassen, beide bestätigten Gesamtpreise erhalten. Hauptgerichte mit
  „(klein / groß)“, ohne das Wort „Preis“. Haussalat und Dessert ausblenden.
- Oma Küche: „All-you-can-eat-Buffet“, ohne Erwachsenen-, Uhrzeit- und To-go-Text.
- Grüne Hütte: Suppennamen ohne „Suppen zur Auswahl:“, darunter „Optional zum
  Tagesteller“, separaten Suppenpreis erhalten. Aufpreistext an Hauptgerichten
  ausblenden.
- Glashaus und L’Osteria: unverändert, einschließlich ihrer Beschreibungen.

Die umgesetzten Funktionen `restaurantDisplayRules` und `mensaStations` müssen
in beiden Ansichten übereinstimmen; Regressionstests prüfen diese Gleichheit.
