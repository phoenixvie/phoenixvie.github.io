# WU Food Web-Vorschau

Starten im Repository mit `node wu-lunch-app/preview/server.mjs`, dann `http://localhost:4173` öffnen.

Die Vorschau ist für gemeinsame Design-Iterationen gedacht. Sie liest die öffentlichen Wochenmenüs und die Restaurant- und Menüänderungen aus denselben Quellen wie die Android-App (`src/data.ts`). Alle 15 Sekunden werden Änderungen geprüft und bei neuen Daten angezeigt. Die Karte verwendet MapLibre und OpenFreeMap. Die UI-Symbole stammen aus Google Material Symbols.

Die Android-App nutzt dieselben Menüdaten und Kontaktinformationen. Das bisherige App-Icon bleibt erhalten. Ein neues APK wird erst nach erneuter Erstellung in GitHub Actions verfügbar.

Die Kontaktansicht zeigt recherchierte Öffnungszeiten mit Links auf die Restaurantquellen. Telefon und E-Mail aus dem Adminbereich haben Vorrang. Nicht verifizierte Zeiten werden nicht angezeigt.

Die Menüquelle öffnet sich in der Web-Vorschau in einem eingebetteten Browserfenster. Manche Restaurantseiten sperren das Einbetten; dann führt der sichtbare Ausweichlink zur Originalseite. Für die spätere Android-App ist eine native interne Browseransicht vorgesehen.

Vor dem nächsten Android-Build: Das bisherige Logo beibehalten, aber das Motiv für das adaptive Android-Symbol innerhalb der sicheren Bildfläche verkleinern. Der aktuelle Vollbild-Vordergrund wird vom Launcher sichtbar abgeschnitten (Screenshot vom 08.11.2026). Danach das Symbol auf einem Android-Gerät prüfen. Keinen APK-Build ohne ausdrückliche Freigabe starten.
