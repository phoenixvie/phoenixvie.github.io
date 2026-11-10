# WU Food Web-Vorschau

Starten im Repository mit `node wu-lunch-app/preview/server.mjs`, dann `http://localhost:4173` öffnen.

Die Vorschau ist für gemeinsame Design-Iterationen gedacht. Sie liest die öffentlichen Wochenmenüs und die Restaurant- und Menüänderungen aus denselben Quellen wie die Android-App (`src/data.ts`). Alle drei Sekunden werden Änderungen geprüft und bei neuen Daten angezeigt. Die Karte verwendet MapLibre und OpenFreeMap. Die UI-Symbole stammen aus Google Material Symbols.

Die Android-App nutzt dieselben Menüdaten und Kontaktinformationen. Das bisherige App-Icon bleibt erhalten. Ein neues APK wird erst nach erneuter Erstellung in GitHub Actions verfügbar.

Die Kontaktansicht zeigt recherchierte Öffnungszeiten mit Links auf die Restaurantquellen. Telefon und E-Mail aus dem Adminbereich haben Vorrang. Nicht verifizierte Zeiten werden nicht angezeigt.
