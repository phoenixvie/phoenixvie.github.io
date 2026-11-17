# WU Lunch für Android

Die App zeigt die Restaurantliste, eine OpenStreetMap-Karte über MapLibre, Tagesmenüs und Kontaktmöglichkeiten. Restaurantdaten kommen von `wu-lunch/data/menus.json` auf GitHub Pages. Sichtbarkeit, Reihenfolge, Stammdaten und manuelle Tagesmenüs kommen aus den öffentlich lesbaren, durch Schreibregeln geschützten Supabase-Tabellen. Der Adminbereich bleibt auf der Website; in der App ist kein Admin-Login erforderlich.

Das App-Symbol ist `assets/icon.png` (Gabel, Messer, Löffel auf blauen Streifen). Für Android gibt es zusätzlich `assets/adaptive-icon.png`: Android schneidet Symbole je nach Gerät rund oder als abgerundetes Quadrat zu und zeigt nur die Mitte der Vorlage. Dort liegt das Besteck deshalb vollständig in der garantiert sichtbaren Mitte, und die Streifen laufen bis zum Rand weiter. Erzeugt wird die Datei mit `python3 scripts/make-adaptive-icon.py` (nur nötig, wenn sich `icon.png` ändert); ein Test prüft die Lage des Motivs. Ein nachträglicher Innenabstand wird nicht mehr verwendet. `assets/icon-original.webp` ist das frühere Motiv und wird nicht mehr eingebunden.

Die App fragt Daten beim Start, beim Wechsel zurück in den Vordergrund und alle 15 Sekunden im Vordergrund erneut ab. Admin-Änderungen sind deshalb üblicherweise binnen 15 Sekunden sichtbar. Neue automatisch importierte Menüs erscheinen nach dem GitHub-Pages-Deployment. Ohne Netzverbindung zeigt die App eine Fehlermeldung; bereits geladene Daten bleiben während eines vorübergehenden Fehlers sichtbar.

## Android-Testversion

Der GitHub-Workflow **WU Lunch Android APK** erstellt bei Änderungen unter `wu-lunch-app/` ein eigenständig startbares Test-APK mit eingebettetem App-Code. Nach einem erfolgreichen Lauf unter **Actions → WU Lunch Android APK** den Anhang `wu-lunch-android-apk` herunterladen und `app-release.apk` auf einem Android-Gerät öffnen. Android kann dabei die Freigabe für Installationen aus dem Browser/Dateimanager verlangen. Dieses Test-APK wird vorläufig mit dem Android-Entwicklerschlüssel signiert und ist nicht für den Play Store bestimmt.

Für eine Veröffentlichung im Play Store braucht die App später ein signiertes AAB, Store-Eintrag, Datenschutzhinweise und Tests auf echten Geräten. Das enthaltene `production`-Profil in `eas.json` ist dafür vorbereitet; Signierschlüssel und Store-Zugang sind bewusst nicht im Repository.

## Entwicklung

Node.js 24, npm und für lokale Android-Builds Android Studio/JDK 17 installieren. Dann in diesem Ordner `npm ci`, `npm run test`, `npx tsc --noEmit`, `npx expo run:android` ausführen. MapLibre benötigt einen nativen Android-Build; Expo Go reicht nicht aus. Das GitHub-APK kann ohne lokales Android Studio gebaut werden.

Adressen und Kartenkoordinaten lassen sich im Web-Adminbereich je Restaurant ändern. Wo noch keine geprüften Koordinaten vorliegen, wird kein Kartenmarker erfunden. Die Standardstandorte stammen aus der bisherigen Website und geprüften OpenStreetMap-Einträgen.
# Gemeinsame Designquelle (seit Android 0.2.0)

Die Android-Oberfläche wird aus den lokalen Dateien unter `preview/` eingebettet. `npm run bundle:preview` erstellt daraus `src/previewHtml.ts`; Tests und CI generieren die Datei erneut. Die APK enthält das Layout und die Google-Material-Symbole selbst, lädt Menüs, Adminänderungen und Kartendaten weiterhin online. Die Menüquellen öffnen sich über eine separate native WebView ohne privilegierte Nachrichtenbrücke.

APK-Builds starten nur manuell oder für Pull Requests mit `[APK]` im Titel. Die CI prüft den Design-Fingerabdruck innerhalb der tatsächlichen APK und installiert sie für Oberflächenprüfungen auf einem Android-Emulator. Das Downloadpaket heißt `wu-food-android-<Version>` (aktuell `wu-food-android-0.5.2`) und enthält `WU-Food-<Version>.apk` sowie `build-info.json`. Die Version steht in `app.json`, `package.json` und `package-lock.json`; ein Test stellt sicher, dass alle drei übereinstimmen.


## Was ohne neue APK ankommt – und was nicht

Die installierte App zeigt die **beim Bau eingebettete Oberfläche** (`src/previewHtml.ts`). Sie lädt die Oberfläche nicht von der Webseite
nach. Eine frühere Fassung dieser Datei behauptete das Gegenteil; der aktuelle Code tut das nicht (geprüft am 17.11.2026).

| Änderung | Kommt auf dem Handy an |
| --- | --- |
| Menüs, Preise, Reihenfolge und Sichtbarkeit der Restaurants, Restaurantdaten, manuelle Menüs | sofort (alle drei Sekunden abgefragt, solange die App sichtbar ist; beim Zurückkehren in die App sofort) |
| App-Texte und englische Übersetzungen aus dem Admin | sofort |
| Bilder, die von der Webseite geladen werden (z. B. Treffpunktfoto) | sobald sie auf der Webseite liegen |
| Layout, Navigation, neue Funktionen, Meet-to-eat-Ablauf, App-Symbol | erst mit einer neuen APK |

Die Webvorschau unter https://phoenixvie.github.io/wu-lunch-app/preview/ zeigt den Stand des Hauptzweigs und damit das, was die nächste APK
enthalten würde. Restaurantseiten und PDF-Dateien öffnen in der App intern mit einem einzigen Zurück-Button unten.
