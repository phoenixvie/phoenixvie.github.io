# WU Food – UI/UX-Testskript für eine KI (Stand 22.11.2026)

Dieses Skript ist für eine KI gedacht, die WU Food wie echte Nutzerinnen und Nutzer bedient und
Auffälligkeiten meldet. Es geht um Bedienbarkeit, Verständlichkeit und Vertrauen, nicht um Code.

## 0. Rahmen

**Was getestet wird**

| Ausgabe | Zugang | Hinweise |
| --- | --- | --- |
| Web-Vorschau (identisch mit dem Inhalt der Apps) | https://phoenixvie.github.io/wu-lunch-app/preview/ | Im Browser mit Handy-Maßen prüfen (z. B. 390 × 844 und 360 × 780); Karte und Restaurant-Webseiten laden hier echt. |
| Android-App | APK aus dem GitHub-Workflow „WU Lunch Android APK" oder Google-Play-Test | Zurück-Taste, Teilen, Systemsprache. |
| iOS-App | TestFlight | Kein Zurück-Knopf des Systems; Wisch-Geste von links, Pfeil oben links. |
| Webseite (Desktop/Mobil) | https://phoenixvie.github.io/wu-lunch/ | Nur Vergleich der Menüinhalte mit der App, kein eigener UX-Durchlauf. |

**Regeln für die testende KI**

1. Teste als die jeweilige Persona: ihre Sprache, ihre Eile, ihr Vorwissen. Erfinde keine Funktionen; melde, was du siehst.
2. Jeder Befund bekommt: Persona, Schritt, Gerät/Ausgabe, Erwartung, Beobachtung, Schweregrad, Screenshot.
3. Schweregrade: **A** Abbruch (Ziel nicht erreichbar, Absturz, falsche Daten) · **B** Hürde (Ziel mit Umweg oder Verwirrung erreicht) · **C** Schönheitsfehler · **W** Wunsch/Idee.
4. **Echte Daten:** Meet to eat arbeitet mit der echten Datenbank. Namen, die du einträgst, sehen alle. Verwende nur den Vornamen `Testa`, melde dich am Ende jedes Durchlaufs wieder ab und prüfe, dass `Testa` verschwunden ist. Trage niemals mehr als eine Testanmeldung gleichzeitig ein.
5. **Uhrzeit (Wien):** Die App richtet sich nach der Wiener Zeit. Meet to eat findet mittwochs statt (im Admin änderbar). Am Termintag zwischen 12:05 und 14:00 Uhr ist die Anmeldung für den angezeigten Termin geschlossen; ab 14:00 rückt der nächste Termin nach. Am Wochenende zeigt die Menüansicht die kommende Woche („Noch nicht veröffentlicht", solange die Lokale nichts veröffentlicht haben). Notiere bei jedem Durchlauf Datum und Uhrzeit.
6. Sprache: Die App startet in der Systemsprache (Deutsch oder Englisch), „Change language." unter jedem Menü wechselt. Prüfe jede Persona in ihrer Sprache und einmal den Wechsel.
7. Keine Bewertung der Küche, keine Preisvergleiche. Menüinhalte nur stichprobenartig mit der Lokal-Webseite vergleichen (Abschnitt 4).

**Aufbau der App (zur Orientierung)**

- Startseite: Liste der Lokale (Name, Küche), oben Umschalter „Liste | Karte", unten Fußzeile mit Impressum, Kontakt, Change Language, Webseite. Letzter Eintrag der Liste: „Meet to eat", rechts ggf. eine kleine Zahl (Angemeldete beim nächsten Termin).
- Lokal → Menü: Wochentage Montag bis Freitag als Leiste und Wischen zwischen Tagen; unten Reiter „Menü | Restaurant | Zurück | Weiter"; unter dem Menü ein zweizeiliger Hinweis mit Links (Meet to eat, Restaurantwebseite, Change language).
- Lokal → Restaurant: Telefon, E-Mail, Webseite, Menü-Seite, Adresse, Öffnungszeiten, Kartenausschnitt; Links öffnen den eingebauten Browser (PDF-Menüs im eingebauten PDF-Betrachter) oder Telefon/Mail-App.
- Karte: alle Lokale als farbige Buchstaben-Pins; Tipp auf Pin zeigt eine Zeile zum Lokal.
- Meet to eat: Zeichnung, Einleitung, Tabelle (Datum als Auswahlliste mit zwei Terminen, Uhrzeit 12:00, Losgehen 12:05, Treffpunkt „Info nach Anmeldung", Teilnehmer, „Bereits angemeldet" mit Namen und Link „Unpassenden Namen melden"), Feld „Dein Vorname", Knopf „Teilnehmen". Nach Anmeldung: grüne Bestätigung, blauer Knopf „Abmelden", Foto und Google-Maps-Knopf des Treffpunkts.

## 1. Personas

| Kürzel | Persona | Gerät/Sprache | Ziel | Typische Lage |
| --- | --- | --- | --- | --- |
| **P1 Lena** | WU-Studentin, 2. Semester, 20 | Android, Deutsch, Dunkelmodus, günstiger Datentarif | Schnell sehen, wo es heute etwas Veganes um 8 € gibt; will Leute kennenlernen | Zwischen zwei Vorlesungen, 11:50 Uhr, 3 Minuten Zeit |
| **P2 Priya** | Austauschstudentin aus Indien, 24 | iPhone, Englisch, kein Deutsch | Verstehen, was auf der Karte steht; vegetarisch; Meet to eat als Kontaktchance | Neu in Wien, erste Woche |
| **P3 Thomas** | WU-Mitarbeiter in der Verwaltung, 48 | iPhone, Deutsch, große Schrift im System | Immer dasselbe Lokal, will nur das Tagesmenü und ob es heute Schnitzel gibt | 30-Minuten-Mittagspause, kennt Campus |
| **P4 Sandra** | Angestellte in einem Büro im Viertel Zwei, 35, nicht WU | Android, Deutsch | Abwechslung zur Kantine; braucht Adresse und Fußweg; fühlt sich bei „WU Studenten" eventuell nicht angesprochen | Plant am Vormittag für die Gruppe im Büro |
| **P5 Herr Kovac** | Pensionist, wohnt neben dem Campus, 71 | Android, Deutsch, Lesebrille, tippt vorsichtig | Günstig und gut essen, telefonisch reservieren, Öffnungszeiten | Nachmittags für morgen; wenig Erfahrung mit Apps |
| **P6 Jonas** | Student mit Sehbehinderung, 22 | iPhone mit VoiceOver, Englisch | Alles per Screenreader erreichen | Wie P1, aber nicht-visuell |
| **P7 Max** | Student, der Grenzen austestet, 19 | Android, Deutsch | Unsinn eintragen, doppelt anmelden, Namen anderer löschen | Langweilt sich |
| **P8 Reviewer** | App-Prüfer bei Apple/Google, kein Deutsch | iPad (iPhone-Modus) bzw. Android-Tablet, Englisch | Funktioniert alles ohne Login? Gibt es tote Enden, kaputte Links, Inhalte Dritter? | Prüft 10 Minuten, kennt Wien nicht |

## 2. Szenarien je Persona

Jedes Szenario: Schritte ausführen, Erwartung prüfen, abweichende Beobachtung melden. Zeitangaben sind Richtwerte für „fühlt sich schnell an".

### P1 Lena – „Was gibt es heute Veganes?"

1. App öffnen. Erwartung: Liste in unter 2 s sichtbar, heutiges Datum ist in der Menüansicht vorausgewählt (bei Wochenende: Montag der kommenden Woche).
2. Drei Lokale nacheinander öffnen (Mensa, Karma Food, Finn). Erwartung: pro Lokal ein Tipp, Rückweg über Pfeil oder Android-Zurück ohne App-Ende; Reiter „Weiter" springt zum nächsten Lokal.
3. In der Mensa zwischen Tagen wischen. Erwartung: Wischen wechselt den Tag, die Leiste oben folgt, kein versehentliches Zurück.
4. Vegane Gerichte finden. Erwartung: Kennzeichnung „(vegan)" o. ä. im Text erkennbar; Preis rechts, gut lesbar. Befund, wenn sie raten muss.
5. Hinweis unter dem Menü lesen: „Montags & Mittwochs gemeinsam essen gehen." tippen. Erwartung: Meet to eat öffnet sich.
6. Meet to eat: Einleitung lesen, Termin in der Auswahlliste wechseln, Vornamen `Testa` eintragen, „Teilnehmen". Erwartung: grüne Bestätigung, eigener Name mit Kreuz in der Tabelle, Treffpunkt-Foto und Google-Maps-Knopf erscheinen, Zahl am Listeneintrag erhöht sich.
7. Zurück zur Liste, App schließen, neu öffnen, Meet to eat öffnen. Erwartung: Anmeldung besteht weiter, Namensfeld ist leer (wird bewusst nicht gespeichert).
8. „Abmelden". Erwartung: Name weg, Zahl am Listeneintrag sinkt, Foto verschwindet.
9. Dunkelmodus des Systems aktiv: Alles lesbar? (Die App ist bewusst hell; melden, wenn Systemleisten oder Kanten unpassend wirken.)

**Fragen an Lena:** Hat sie in 3 Minuten eine Entscheidung getroffen? Wusste sie ohne Erklärung, was Meet to eat ist und was nach „Teilnehmen" passiert? War klar, wo der Treffpunkt ist?

### P2 Priya – „I don't read German"

1. iPhone-Systemsprache Englisch. App öffnen. Erwartung: Oberfläche vollständig englisch (Liste, Reiter, Fußzeile, Meet to eat), Gerichte englisch übersetzt; wo eine Übersetzung fehlt, steht „English translation pending" statt Deutsch ohne Hinweis.
2. Jede Küchenangabe in der Liste prüfen (International, Middle Eastern, Café …). Befund bei deutschen Resten.
3. Menü eines Lokals lesen: Sind Beilagen, „Suppe oder Salat", Preisformate verständlich? „€" vor oder nach der Zahl konsistent?
4. Restaurant-Reiter: Öffnungszeiten auf Englisch? Adresse per Tipp in Karten-App öffnen (sofern Link), sonst Befund W.
5. Restaurant-Webseite im eingebauten Browser öffnen (ist meist deutsch, das ist in Ordnung). Erwartung: „Back" unten bringt sie in die App zurück; kein Verlassen der App ohne Hinweis.
6. Meet to eat auf Englisch: Alle Texte englisch, Datumsformat englisch („Monday 24 November"), „Your first name", „Take part"/„Sign up to eat together" verständlich. `Testa` anmelden und wieder abmelden.
7. „Change language." tippen und zurückwechseln. Erwartung: sofortiger Wechsel ohne Neustart, Position in der App bleibt.

**Fragen an Priya:** Versteht sie ohne Deutsch, dass Meet to eat ein offenes Treffen ist und wo der Treffpunkt liegt? Gibt es Begriffe, die nur Insider kennen (Mensa, Ausgabe, Semmel)?

### P3 Thomas – „Nur mein Lokal, nur heute"

1. Systemschrift auf größte Stufe stellen. App öffnen. Erwartung: Liste bleibt bedienbar, Namen werden abgekürzt statt überlappt, Zeilen nicht abgeschnitten.
2. Sein Lokal (z. B. Topf & Deckel) in unter 10 s finden. Befund, wenn Scrollen nötig und keine Suche/Sortierung hilft (Wunsch W: Favoriten/Zuletzt).
3. Tagesmenü lesen: Preis und Gericht in einer Zeile? Bei großer Schrift Umbrüche sauber?
4. Auf Schnitzel prüfen (Text-Scan). Erwartung: Gerichtnamen vollständig, nicht abgeschnitten („…" nur mit Grund).
5. Hinweis „Prüfe die Menüs auf der Restaurantwebseite." tippen: Öffnet die Menü-Seite des Lokals, nicht nur die Startseite. Bei PDF: PDF-Betrachter mit Zoom per Finger, Rückweg „Zurück" unten.
6. Reservieren: Restaurant-Reiter → Telefonnummer tippen. Erwartung: Telefon-App mit vorgewählter Nummer (nur auf Gerät, nicht in der Web-Vorschau).
7. Teilen: Gibt es eine Teilen-Funktion für „Gehen wir heute zu …"? Falls ja, Nachricht in WhatsApp/Mail prüfen; falls nicht auffindbar, Befund B.

**Fragen an Thomas:** Schafft er es in 30 s vom Öffnen bis zur Entscheidung? Stört ihn Meet to eat (für ihn irrelevant) im Weg?

### P4 Sandra – „Nicht von der WU"

1. App im Play Store/App Store (Eintrag) lesen: Wird klar, dass die App auch für Nicht-WU-Leute nützlich ist? Befund W mit Formulierungsvorschlag.
2. Karte öffnen. Erwartung: Lage aller Lokale zur Messe/Prater/Viertel Zwei erkennbar; Zoom und Verschieben flüssig; Pins unterscheidbar; Tipp auf Pin zeigt Name und Küche; Tipp auf diese Zeile öffnet das Menü.
3. Für sechs Kolleginnen planen: In mehreren Lokalen Preise und Küche vergleichen; Rückweg über „Zurück" in der Reiterleiste. Erwartung: kein Verlust der zuletzt gewählten Ansicht (Karte bleibt Karte).
4. Adresse und Fußweg: Adresse im Restaurant-Reiter antippen → Karten-App? Falls nur Text: Befund W.
5. Meet to eat lesen: Teilnehmer „WU-Studenten Gruppe", Einleitung „mit anderen Studierenden". Fühlt sie sich ausgeschlossen? Notieren, ob die App irgendwo klarstellt, wer willkommen ist.
6. Öffnungszeiten: Sind sie für Nicht-Campus-Leute vollständig (Wochenende, Feiertage)?

### P5 Herr Kovac – „Vorsichtig und genau"

1. App zum ersten Mal öffnen, keine Erklärung lesen. Erwartung: ohne Einführung verständlich; keine Pop-ups, keine Berechtigungsabfragen.
2. Lesbarkeit: Kontrast der grauen Texte (Küche, Hinweis unter dem Menü, Tabellen-Überschriften in Meet to eat) bei Tageslicht. Kleinste Schrift messen (Hinweis unter dem Menü ist 9,5–11 px) und als Befund melden, wenn für ihn unlesbar.
3. Tippziele: Wochentage in der Leiste, kleine Pfeile, das Kreuz zum Abmelden. Erwartung: mindestens fingerbreit; Fehltipps notieren.
4. Versehentliches Wischen: Beim Scrollen im Menü darf kein Tageswechsel passieren; beim Tageswechsel kein Zurück.
5. Morgen planen: Tag „Dienstag" wählen, Lokal wechseln über „Weiter". Erwartung: der gewählte Tag bleibt beim Lokalwechsel.
6. Telefonieren: Nummer im Restaurant-Reiter gut sichtbar, Tipp startet den Anruf, Abbruch möglich.
7. Fehlerfall: Flugmodus einschalten, App öffnen. Erwartung: zuletzt geladene Menüs erscheinen (Zwischenspeicher) oder eine verständliche Meldung mit „Erneut versuchen"; keine leere weiße Seite.

### P6 Jonas – „Mit VoiceOver"

1. VoiceOver (iOS) bzw. TalkBack (Android) einschalten. Startseite durchgehen. Erwartung: jedes Lokal wird mit Name und Küche vorgelesen, der Umschalter „Liste/Karte" als Schalter mit Zustand, Symbole mit Bedeutung (nicht „chevron_right").
2. Menü: Tage als Schaltflächen mit Datum, aktueller Tag als „ausgewählt"; Gerichte mit Preis in sinnvoller Reihenfolge.
3. Karte: Pins fokussierbar? Falls die Karte nicht zugänglich ist, muss die Liste alles bieten (Befund C, nicht A).
4. Meet to eat: Auswahlliste „Datum" bedienbar, Feld „Dein Vorname" mit Beschriftung, Fehlermeldung wird vorgelesen (role=alert), Knopf „Teilnehmen"/„Abmelden" klar benannt, Kreuz als „Meine Anmeldung entfernen".
5. Eingebauter Browser: „Zurück"-Schaltfläche erreichbar, Fokus nach dem Schließen wieder in der App.
6. Schriftvergrößerung (Dynamic Type / Schriftgröße) mit VoiceOver kombiniert: keine abgeschnittenen Texte.

### P7 Max – „Was passiert, wenn …"

1. Vorname: leer, `a`, `Max123`, `Free Palestine`, `Hitler`, `Anna-Lena`, `anna`, 25 Zeichen, Emoji, HTML `<b>x</b>`. Erwartung: leer/`a`/Zahlen/Leerzeichen/Emoji/HTML → rote Meldung unter dem Feld; `Hitler` → „Dieser Name ist hier nicht möglich"; `Anna-Lena` angenommen; `anna` wird zu `Anna`. Nichts davon erscheint in der Liste anderer.
2. Doppelt anmelden: nach „Teilnehmen" sofort nochmals (anderer Termin). Erwartung: höchstens eine aktive Anmeldung pro Gerät; Verhalten beim zweiten Termin dokumentieren (Fehlermeldung verständlich?).
3. Fremde Namen: Gibt es eine Möglichkeit, andere zu löschen? Erwartung: nein; nur „Unpassenden Namen melden" (öffnet Mail an Kontaktadresse mit Betreff).
4. Schnell tippen: „Teilnehmen" fünfmal hintereinander. Erwartung: Knopf gesperrt, keine Mehrfacheinträge.
5. Zeitgrenzen (wenn möglich zu diesen Zeiten testen): am Termintag 12:04 anmelden (geht), 12:06 (Meldung „Anmeldung geschlossen"), 14:01 (nächster Termin wird angezeigt).
6. App-Daten löschen/App neu installieren: Alte Anmeldung ist nicht mehr „meine" (kein Kreuz) – ist das für Max verständlich? Befund W, falls verwirrend.
7. Links manipulieren: Restaurant-Webseite im eingebauten Browser auf eine fremde Seite weiterklicken. Erwartung: bleibt im Browser der App, „Zurück" funktioniert, keine Download-Dialoge.

### P8 Reviewer – „Zehn Minuten, kein Login"

1. Gerät: iPad (App läuft im iPhone-Modus) bzw. Android-Tablet. Hochformat. Erwartung: Darstellung zentriert, nichts abgeschnitten, Start ohne Abfragen.
2. Jeden Reiter und jeden Link der Fußzeile öffnen (Impressum, Kontakt, Change Language, Webseite). Erwartung: alle führen irgendwohin Sinnvolles; Impressum nennt Betreiber und Datenschutz.
3. Alle elf Lokale öffnen, pro Lokal Menü und Restaurant. Erwartung: keine leeren Bildschirme außer „Noch nicht veröffentlicht" mit sichtbarem Datum.
4. Meet to eat vollständig durchspielen (anmelden `Testa`, abmelden). Erwartung: funktioniert ohne Konto; Meldelink vorhanden; Datenschutzlink im Impressum erklärt Vorname und Kennung.
5. Inhalte Dritter: Kartenquelle (OpenStreetMap/OpenFreeMap) am Kartenrand genannt? Treffpunkt-Foto zeigt ein „Google Maps"-Wasserzeichen – als Risiko melden (Richtlinie Inhalte Dritter).
6. Querformat drehen: App bleibt im Hochformat (gewollt) – kein Absturz.
7. Hintergrund/Vordergrund: App 2 Minuten in den Hintergrund, zurückholen. Erwartung: Stand bleibt, Menüs aktualisieren sich still.

## 3. Querschnitt (einmal pro Ausgabe)

- **Erster Eindruck (5-Sekunden-Test):** Screenshot der Startseite 5 s zeigen; was ist die App, was kann ich tun? Antwort notieren.
- **Geschwindigkeit:** Kaltstart bis Liste, Lokal → Menü, Karte bis alle Pins; jeweils gefühlt und gemessen.
- **Schriftgrößen:** System „klein", „Standard", „sehr groß": Abschneiden, Überlappen, horizontales Scrollen.
- **Gerätegrößen:** 320 px breit (iPhone SE 1. Gen. / kleine Androids), 360–393 px, 430 px, Tablet. Besonders: zweizeiliger Hinweis unter dem Menü (erste Zeile kürzer als zweite), Datumsauswahl in Meet to eat, Tabelle „Bereits angemeldet".
- **Dunkelmodus:** Systemleisten, Tastatur, Auswahlliste, Teilen-Dialog.
- **Netz:** langsames 3G (Karte, Lokal-Webseiten, PDF), Offline (Zwischenspeicher, Meldungen), Wiederverbindung.
- **Sprachwechsel:** mitten in Meet to eat, mitten im Menü; Texte des Betreibers (Admin-Texte) folgen der Sprache.
- **Rückwege:** Android-Zurück auf jedem Bildschirm (Liste → App verlassen, sonst eine Ebene zurück); iOS Wischen von links im eingebauten Browser.
- **Zustände:** Wochenende, Feiertag, Lokal ohne Menü, Tag ohne Menü, Meet to eat ohne Angemeldete, mit 1 und mit 8 Angemeldeten (lange Namensliste).
- **Konsistenz:** gleiche Begriffe überall (Restaurant/Lokal, Menü/Speisen, anmelden/teilnehmen), Zahlenformat (11,9 € vs. 11,90 €), Datumsformat je Sprache.

## 4. Datenstichprobe (Vertrauen)

Pro Durchlauf drei zufällige Lokale: Tagesmenü in der App mit der Lokal-Webseite vergleichen (Gericht, Preis, Beilagen, Tag). Abweichungen als **A** melden, wenn Preis oder Gericht falsch; als **B**, wenn unvollständig (z. B. fehlende Beilage). Immer Datum/Uhrzeit des Vergleichs angeben, weil Lokale nachträglich ändern.

## 5. Berichtsformat

```
# WU Food UX-Test – <Datum, Uhrzeit Wien> – <Ausgabe/Version/Gerät>

## Zusammenfassung
3 Sätze: Gesamteindruck, größte Hürde, größte Stärke.

## Befunde (sortiert A → W)
| Nr | Grad | Persona | Bildschirm | Schritt | Erwartung | Beobachtung | Screenshot |

## Je Persona: Ziel erreicht? (ja / mit Umweg / nein) + ein Satz

## Querschnitt: Tabelle der Prüfpunkte aus Abschnitt 3 mit ok / Befund-Nr

## Datenstichprobe: 3 Lokale, Ergebnis

## Aufräumen: bestätigt, dass `Testa` abgemeldet ist (Screenshot der Teilnehmerliste)

## Vorschläge (max. 5, priorisiert nach Nutzen für die meisten Personas)
```

## 6. Nicht Teil dieses Tests

- Admin-Seite der Webseite (nur für den Betreiber).
- Wels-Ausgabe (https://phoenixvie.github.io/wu-lunch-app/preview/wels/), eigenes Projekt.
- Inhaltliche Richtigkeit aller Menüs (nur Stichprobe), Import-Zeitpunkte.
