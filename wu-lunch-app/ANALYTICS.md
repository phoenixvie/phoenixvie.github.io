# App-Statistik mit Aptabase

Die native Android-/iOS-Hülle verwendet das offizielle React-Native-SDK 0.6.0 und den öffentlichen EU-Eingabeschlüssel `A-EU-3618719023`. Dieser Schlüssel ist für App-Clients bestimmt und erlaubt keinen Kontozugriff. Webtracking und automatische Fehler-/Crashberichte sind deaktiviert. Die Webseite und die Browser-App-Vorschau senden keine Aptabase-Ereignisse. Das SDK sendet asynchron in Chargen, etwa alle zehn Sekunden und bei App-Zustandswechseln. Netzwerkprobleme blockieren die Menüs nicht; Zählungen sind deshalb keine garantierte vollständige Personenstatistik.

| Ereignis | Auslöser | Zusatzfelder |
| --- | --- | --- |
| `app_open` | Kaltstart nach Laden der Sprachwahl oder Rückkehr aus dem echten Hintergrund | `entry`: `cold_start`/`foreground`, `app_language` |
| `restaurant_open` | Restaurant aus Liste/Karte öffnen oder Weiter/Zurück verwenden | `restaurant_id`, `entry`, `view`, `app_language` |
| `restaurant_view` | Zwischen Menü und Restaurantinfo wechseln | `restaurant_id`, `view`, `app_language` |
| `menu_day_changed` | Einen anderen Wochentag anklicken oder dorthin wischen | `restaurant_id`, `weekday` (1–5), `app_language` |
| `language_changed` | Sprache manuell wechseln | `app_language` |

`entry` bei Restaurantaufrufen ist `list`, `map`, `next` oder `previous`. Restaurantkennungen und Ereignisse sind begrenzt; zusätzliche Felder werden verworfen. Keine E-Mail-Adressen, Namen, Menütexte, vollständigen Links oder selbst angelegten dauerhaften Nutzerkennungen. Das SDK ergänzt Zeit, Sitzungskennung, Betriebssystem und App-Version. `app_language` enthält die tatsächlich gewählte Sprache; auf das vom SDK gelieferte Locale-Feld verlassen wir uns nicht.

Das dreisekündliche Nachladen von Menüs, Preis-/Profiländerungen, Karten-Pins und Texten erzeugt keine Nutzungsereignisse. Ein unverändert erneut angeklickter Tag bzw. eine unveränderte Ansicht zählt ebenfalls nicht. Kurzzeitige `inactive`-Zustände (z. B. Systemdialoge) zählen nicht als erneute App-Öffnung.

Die native Nachrichtenbrücke akzeptiert Statistik nur aus der eigenen App-Oberfläche, nicht aus Restaurantseiten oder PDFs. Das öffentliche Impressum beschreibt die Statistik zweisprachig. Aptabase verarbeitet IP/User-Agent nach seiner eigenen Datenschutzbeschreibung vorübergehend für tagesweise wechselnde Kennungen; Cookies oder dauerhafte Gerätekennungen werden dafür nicht verwendet. Aus mehreren App-Öffnungen darf keine entsprechende Zahl unterschiedlicher Personen abgeleitet werden.

## Prüfung und Freigabe

Unit-Tests prüfen Zählung, Feldbegrenzung, ungültige Wochentage, fremde Quellen und Fehlerisolation. Der integrierte Vorschautest prüft, dass Laden/Polling keine Restaurantaufrufe erzeugt. Am 13.11.2026 nahm der EU-Ereignisendpunkt ein ausdrücklich als Debug markiertes `integration_test` mit HTTP 200 an. Das bestätigt den Eingabeschlüssel und die Erreichbarkeit, nicht die Anzeige einer neuen Android-App auf einem echten Gerät.

Die installierte ältere APK sendet diese Ereignisse noch nicht. Erst eine ausdrücklich gewünschte neue APK enthält das SDK und die Zählung. Bei einer späteren Geräteprüfung im Aptabase-Dashboard auf den passenden Debug-/Release-Modus achten. Die Anbindung selbst wurde ohne APK umgesetzt. Der ausdrücklich beauftragte nachfolgende Build 0.4.0 enthält diese Funktion.

Anbieter: https://aptabase.com/docs und https://aptabase.com/legal/privacy

Android-Emulatoren mit üblichen SDK-/Generic-Modellkennungen sowie als automatisierte Tests markierte Geräte initialisieren Aptabase nicht. Daher senden die Release-APK-Prüfungen im GitHub-Emulator keine Produktionsereignisse. Für echte Geräte enthält jedes Ereignis app_language=de/en; automatische Spracherkennung und manuelle Auswahl werden gleich behandelt.
