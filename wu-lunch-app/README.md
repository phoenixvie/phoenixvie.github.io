# WU Lunch für Android

Die App zeigt die Restaurantliste, eine OpenStreetMap-Karte über MapLibre, Tagesmenüs und Kontaktmöglichkeiten. Restaurantdaten kommen von `wu-lunch/data/menus.json` auf GitHub Pages. Sichtbarkeit, Reihenfolge, Stammdaten und manuelle Tagesmenüs kommen aus den öffentlich lesbaren, durch Schreibregeln geschützten Supabase-Tabellen. Der Adminbereich bleibt auf der Website; in der App ist kein Admin-Login erforderlich.

Das App-Symbol ist `assets/icon.png` (Gabel, Messer, Löffel auf blauen Streifen). Für Android gibt es zusätzlich `assets/adaptive-icon.png`: Android schneidet Symbole je nach Gerät rund oder als abgerundetes Quadrat zu und zeigt nur die Mitte der Vorlage. Dort ist das Besteck groß herangezoomt: Oben bleibt es vollständig sichtbar, unten wird es vom Rand des Symbols knapp abgeschnitten (Vorgabe des Betreibers vom 17.11.2026); die Streifen laufen bis zum Rand weiter. Erzeugt wird die Datei mit `python3 scripts/make-adaptive-icon.py` (nur nötig, wenn sich `icon.png` ändert); ein Test prüft die Lage des Motivs. Ein nachträglicher Innenabstand wird nicht mehr verwendet. `assets/icon-original.webp` ist das frühere Motiv und wird nicht mehr eingebunden.

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

## Zweit-Ausgabe „Mittag in Wels" (Zwischenprojekt, 17.11.2026)

Unter `preview/wels/` läuft dieselbe App für 14 Restaurants in Wels – für den Vater des Betreibers. Der Schwerpunkt bleibt WU Food.

- **Kein kopierter Code:** `preview/wels/index.html` setzt nur `window.WU_FOOD_SITE` (eigene Menüdatei, Titel, Kartenmitte) und lädt `../app.js` und `../style.css`. Ohne diese Angabe verhält sich `app.js` unverändert wie WU Food. In der Wels-Ausgabe gibt es keine Admin-Daten, kein Meet to eat und keine Sprachumschaltung.
- **Daten:** `wu-lunch/scripts/update_wels.py` liest die Mittagsmenüs direkt von den Restaurantseiten (Text, PDF-Text, beim BILLA-Plakat über die Textposition) und schreibt `preview/wels/menus.json`. Keine KI, keine Zugangsschlüssel. Zeigt eine Quelle eine andere Woche, bleibt der Tag leer.
- **Ablauf:** Workflow `wels-mittag.yml`, getrennt vom WU-Import; er läuft nach jedem WU-Import mit und zusätzlich nach GitHub-Zeitplan.
- **Besonderheiten einzelner Quellen:** Sorry Mama veröffentlicht die Wochenkarte nur als Bild – sie wird per Texterkennung (tesseract) zweimal gelesen und nur übernommen, wenn beide Lesungen übereinstimmen. Hayashi hat eine feste Mittagskarte als Bild; ihr Inhalt ist im Skript hinterlegt und an genau diese Bilddatei gebunden (ändert sich das Bild, wird nichts mehr gezeigt, bis die Karte nachgezogen ist). OX nennt kein Datum; die Karte gilt erst als neue Woche, wenn sie sich gegenüber der Vorwoche geändert hat. Gasthaus Huber veröffentlicht nur die Tageskarte; frühere Tage der Woche bleiben stehen. Gösserbräu nennt im Monatsplan keine Preise.
- **Nicht aufgenommen (Stand 17.11.2026):** Agape (auf der Webseite gibt es kein Mittagsmenü mehr, die genannte Seite existiert nicht), Rex Lounge (unter der Adresse erscheint ein fremdes Online-Casino) und Interspar Restaurant (die Seite sperrt automatische Abrufe).
- **In der Android-App nicht enthalten:** Die Wels-Ausgabe ist nur eine Webseite.

## Meet to eat: Kontrolle im Admin (Stand 17.11.2026)

- Im Admin der Webseite (`wu-lunch/admin.html`) gibt es den Bereich „Meet to eat: Anmeldungen": alle Vornamen ab heute, nach Termin gruppiert, je Eintrag ein Knopf „Löschen".
- Voraussetzung ist die Datenbank-Freigabe `wu-lunch/supabase/20261117_meet_admin.sql` (einmal in Supabase ausführen). Fehlt sie, zeigt der Bereich einen klaren Hinweis statt einer scheinbar leeren Liste.
- Eine Deinstallation der App kann technisch nicht erkannt werden (Android meldet sie weder der App noch dem Server). Anmeldungen gelten immer nur für einen Termin und verschwinden danach von selbst; bis dahin lässt sich ein Name im Admin entfernen.

## Treffpunkt-Foto und Symbole in der installierten App (Stand 17.11.2026)

- Das Treffpunkt-Foto (`preview/meeting-point.webp`) wird beim Bündeln (`npm run bundle:preview`) fest in die App eingebaut. Früher lud die installierte App es von der Webseite und zeigte deshalb das Bild des dort veröffentlichten Stands statt des eigenen.
- Die App enthält nur eine kleine Auswahl der Symbolschrift (`assets/material-symbols-font.json`). Jedes weitere Symbol muss als Zeichnung in `meetIcons` (`preview/app.js`) stehen, sonst erscheint sein Name als Text (so stand in 0.5.3 „CLOSE" statt des Kreuzes). Ein Test prüft das.

## Nutzungsstatistik (Stand 17.11.2026)

Die installierte Android-App zählt anonym über Aptabase (EU), ohne Cookies und ohne dauerhafte Gerätekennung. Die Webseite, die Web-Vorschau und die Wels-Ausgabe messen nichts. Auswertung: im Aptabase-Konto des Betreibers.

Gesendet werden nur Ereignisnamen mit festen Wertelisten (`src/usage.ts` weist alles andere ab) – nie Namen, E-Mail-Adressen, Codes, Gerichte oder Linkziele. Jedes Ereignis trägt zusätzlich die App-Sprache.

| Ereignis | Bedeutung | Angaben |
|---|---|---|
| `app_open` | App geöffnet | Kaltstart oder Rückkehr aus dem Hintergrund |
| `restaurant_open` | Restaurant geöffnet | Restaurant, Einstieg (Liste, Karte, weiter/zurück), Ansicht |
| `restaurant_view` | Wechsel Menü ↔ Restaurant-Info | Restaurant, Ansicht |
| `menu_day_changed` | anderer Wochentag | Restaurant, Tag, getippt oder gewischt |
| `home_view` | Wechsel Liste ↔ Karte | Ansicht |
| `map_pin_selected` | Punkt auf der Karte angetippt | Restaurant |
| `restaurant_link` | Link angetippt | Restaurant, Art (Telefon, E-Mail, Webseite, Mittagsmenü-Seite, Google Maps, Hinweis unter dem Menü) |
| `restaurant_shared` | „Teilen" benutzt | Restaurant |
| `footer_link` | Link in der Fußzeile | Impressum, Kontakt oder Webseite |
| `language_changed` | Sprache gewechselt | – |
| `meet_open` | Meet to eat geöffnet | über die Liste oder den Hinweis unter dem Menü |
| `meet_date_changed` | anderer Termin gewählt | nächster oder übernächster Termin |
| `meet_signup_started` | „Teilnehmen" angetippt | Termin |
| `meet_input_rejected` | Eingabe abgelehnt | Grund (Name fehlt, Namensform, gesperrter Name, E-Mail ungültig, keine WU-Adresse) |
| `meet_code_requested` | Code angefordert | erstmals oder erneut |
| `meet_code_result` | Code eingegeben | gültig oder ungültig |
| `meet_joined` | Anmeldung abgeschlossen | Termin, Montag oder Mittwoch |
| `meet_left` | Abmeldung | Termin |
| `meet_maps_opened` | Google Maps zum Treffpunkt | über die Übersicht oder den Knopf |

Neue Ereignisse kommen erst mit einer neuen APK in die Statistik. Der Datenschutztext (Impressum-Seite, `wu-lunch/i18n.js`) nennt diese Kategorien und muss bei Erweiterungen mitgezogen werden.
