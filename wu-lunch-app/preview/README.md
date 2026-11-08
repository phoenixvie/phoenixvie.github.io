# WU Food Web-Vorschau

Starten im Repository mit `node wu-lunch-app/preview/server.mjs`, dann `http://localhost:4173` öffnen.

Die Vorschau ist für gemeinsame Design-Iterationen gedacht. Sie liest die öffentlichen Wochenmenüs und die Restaurant- und Menüänderungen aus denselben Quellen wie die Android-App (`src/data.ts`). Alle 15 Sekunden werden Änderungen geprüft und bei neuen Daten angezeigt. Die Karte verwendet MapLibre und OpenFreeMap. Die UI-Symbole stammen aus Google Material Symbols.

Die bestehenden Android-Dateien und das App-Icon wurden nicht geändert. Nach Designfreigabe wird die abgestimmte Oberfläche in die Android-App übertragen und ein neues APK gebaut.

Die Menüansicht bietet einen Link zu den aktuellen Öffnungszeiten auf Google Maps. Für eine Anzeige der Uhrzeiten direkt in der App ist eine Google Places API-Anbindung mit eigenem Google-Cloud-Projekt, Abrechnung und API-Schlüssel erforderlich. Die Vorschau enthält dafür derzeit noch keine API-Anbindung.
