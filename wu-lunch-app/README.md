# WU Lunch für Android

Die App zeigt die Restaurantliste, eine OpenStreetMap-Karte über MapLibre, Tagesmenüs und Kontaktmöglichkeiten. Restaurantdaten kommen von `wu-lunch/data/menus.json` auf GitHub Pages. Sichtbarkeit, Reihenfolge, Stammdaten und manuelle Tagesmenüs kommen aus den öffentlich lesbaren, durch Schreibregeln geschützten Supabase-Tabellen. Der Adminbereich bleibt auf der Website; in der App ist kein Admin-Login erforderlich.

Das App-Symbol verwendet die bereitgestellte Originaldatei `assets/icon-original.webp`; `assets/icon.png` ist die für den Android-Build benötigte PNG-Fassung.

Die App fragt Daten beim Start, beim Wechsel zurück in den Vordergrund und alle 15 Sekunden im Vordergrund erneut ab. Admin-Änderungen sind deshalb üblicherweise binnen 15 Sekunden sichtbar. Neue automatisch importierte Menüs erscheinen nach dem GitHub-Pages-Deployment. Ohne Netzverbindung zeigt die App eine Fehlermeldung; bereits geladene Daten bleiben während eines vorübergehenden Fehlers sichtbar.

## Android-Testversion

Der GitHub-Workflow **WU Lunch Android APK** erstellt bei Änderungen unter `wu-lunch-app/` ein eigenständig startbares Test-APK mit eingebettetem App-Code. Nach einem erfolgreichen Lauf unter **Actions → WU Lunch Android APK** den Anhang `wu-lunch-android-apk` herunterladen und `app-release.apk` auf einem Android-Gerät öffnen. Android kann dabei die Freigabe für Installationen aus dem Browser/Dateimanager verlangen. Dieses Test-APK wird vorläufig mit dem Android-Entwicklerschlüssel signiert und ist nicht für den Play Store bestimmt.

Für eine Veröffentlichung im Play Store braucht die App später ein signiertes AAB, Store-Eintrag, Datenschutzhinweise und Tests auf echten Geräten. Das enthaltene `production`-Profil in `eas.json` ist dafür vorbereitet; Signierschlüssel und Store-Zugang sind bewusst nicht im Repository.

## Entwicklung

Node.js 24, npm und für lokale Android-Builds Android Studio/JDK 17 installieren. Dann in diesem Ordner `npm ci`, `npm run test`, `npx tsc --noEmit`, `npx expo run:android` ausführen. MapLibre benötigt einen nativen Android-Build; Expo Go reicht nicht aus. Das GitHub-APK kann ohne lokales Android Studio gebaut werden.

Adressen und Kartenkoordinaten lassen sich im Web-Adminbereich je Restaurant ändern. Wo noch keine geprüften Koordinaten vorliegen, wird kein Kartenmarker erfunden. Die Standardstandorte stammen aus der bisherigen Website und geprüften OpenStreetMap-Einträgen.
# Android 0.2.0: gemeinsame Designquelle

Die Android-Oberfläche wird aus den lokalen Dateien unter `preview/` eingebettet. `npm run bundle:preview` erstellt daraus `src/previewHtml.ts`; Tests und CI generieren die Datei erneut. Die APK enthält das Layout und die Google-Material-Symbole selbst, lädt Menüs, Adminänderungen und Kartendaten weiterhin online. Die Menüquellen öffnen sich über eine separate native WebView ohne privilegierte Nachrichtenbrücke. Das adaptive Android-Symbol behält das alte Motiv mit 20 Prozent zusätzlichem Innenabstand.

APK-Builds starten nur manuell oder für Pull Requests mit `[APK]` im Titel. Die CI prüft den Design-Fingerabdruck innerhalb der tatsächlichen APK und installiert sie für Oberflächenprüfungen auf einem Android-Emulator. Das Downloadpaket heißt `wu-food-android-0.2.0` und enthält `WU-Food-0.2.0.apk` sowie `build-info.json`.

