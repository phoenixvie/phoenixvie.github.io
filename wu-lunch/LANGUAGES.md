# Deutsch und Englisch

## Auswahl und Darstellung

Ohne gespeicherte Auswahl entscheidet die primäre Sprache: `de`, `de-AT`, `de-DE`, `de-CH` usw. verwenden Deutsch; alle anderen Sprachen Englisch. Im Browser ist dies `navigator.language`. Die Android-Hülle übergibt ihre über `Intl` ermittelte Systemsprache ausdrücklich an die eingebettete Oberfläche. Namen, Anschriften, Telefonnummern, E-Mail-Adressen und Linkziele bleiben unverändert. Eigene Bedienoberflächen, Datumsanzeigen und Hinweise werden lokalisiert. Externe Restaurantseiten und Original-PDF-Inhalte bleiben Originalquellen.

Der Link „Change Language“ neben dem Impressum wechselt sofort zwischen Deutsch und Englisch. Die Auswahl wird lokal gespeichert und hat beim nächsten Öffnen Vorrang vor der Systemsprache. Aktuelles Restaurant und ausgewählter Tag bleiben erhalten. Die native Hülle übernimmt die gewählte Sprache auch für eigene Zurück-/Fehleranzeigen und den PDF-Betrachter.

`i18n.js` wird von Webseite, Admin und App-Vorschau gemeinsam genutzt und für Android mit eingebettet. Fehlende englische Menütexte heißen „English translation pending“; es gibt keinen stillen Rückfall auf ein altes englisches Gericht oder eine erfundene Übersetzung. Deutsch bleibt die maßgebliche Quelle. Übersetzung verändert weder Preise, Wochen-/Tageszuordnung, Aktivierung noch Reihenfolge.

## Datenbank und Änderungen

`public.lunch_translations` enthält den exakten deutschen Text, dessen SHA-256 als Primärschlüssel, Englisch, Herkunft `ai`/`manual`, Modell und Änderungszeit. Neue deutsche Formulierungen erhalten eigene Übersetzungen. Identische Formulierungen werden wiederverwendet; Admin-Korrekturen gelten deshalb für denselben deutschen Text überall. Mehrzeilige Menükomponenten bleiben separat korrigierbar. RLS erlaubt öffentliche Lesezugriffe, Schreiben ausschließlich für den bestehenden Lunch-Admin. Aktualisierungen erhalten eine Serverzeit.

Die englischen Clients laden zunächst gespeicherte Übersetzungen, dann neue Daten und laufend die Änderungen seit dem letzten Stand. Im normalen Drei-Sekunden-Aktualisierungszyklus werden auch manuelle englische Korrekturen übernommen. Ein neues deutsches Gericht wird in Englisch erst nach Speicherung einer passenden Übersetzung angezeigt. Ein bereits bekanntes unverändertes Gericht benötigt keinen weiteren KI-Aufruf.

## GitHub Actions und KI

`wu-lunch-english.yml` läuft nach abgeschlossenen Menüimporten (auch wenn eine andere Quelle einen Prüffehler meldet), Änderungen an finalen Menüdaten und relevanter Übersetzungslogik sowie zusätzlich stündlich um Minute 27 für manuelle deutsche Änderungen. Gelesen werden ausschließlich die bereits freigegebenen Menüdaten. Manueller Start ist möglich. Feature-PRs führen ausschließlich Offline-Tests aus. Für die Produktion werden nur die bereits vorhandenen GitHub-Secrets `OPENAI_API_KEY` und `SUPABASE_SERVICE_ROLE_KEY` verwendet. Keine geheimen Schlüssel in Browser oder APK.

`collect_translation_texts.cjs` sammelt Rohtexte und die finalen Darstellungsformen mit denselben Restaurantregeln wie App/Webseite. Aktuelle Woche, archivierte Wochen, manuelle Tagesfassungen, Restauranttyp, Öffnungszeiten und Ankündigungen werden berücksichtigt. Die automatische Übersetzung liest öffentlich angezeigte Geschäftsinformationen; Passwörter, Auth-Daten und interne Zugangsdaten werden nicht an das Modell gesendet.

`translate_menus.mjs` nutzt `gpt-6-luna` mit strukturierten Ausgaben und prüft vollständige eindeutige Zuordnung, Textgrenzen, erhaltene Zahlen, Links und Zeilenstruktur. Ein zweiter unabhängiger Modellaufruf prüft inhaltliche Treue, insbesondere Zutaten, optionale/inkludierte Leistungen, „und“/„oder“ und Ernährungsangaben. Nur vollständig akzeptierte Chargen werden gespeichert. Fehler führen zu einem fehlgeschlagenen Job und zu weiterhin als ausstehend markierten Texten; abgeschlossene korrekte Chargen bleiben erhalten.

Automatische Schreibvorgänge sind ausschließlich Einfügungen mit Konflikt-ignorieren. Dadurch überschreibt die KI auch bei gleichzeitiger Admin-Bearbeitung keine manuelle Übersetzung. Die deutsche Menüdatei wird von diesem Prozess nicht verändert. Alte Einträge können aus Nachvollziehbarkeitsgründen erhalten bleiben, werden aber nur bei exaktem Ausgangstext verwendet.

## Admin-Bedienung

Der Schalter „Texte bearbeiten / Edit texts“ wählt die Inhaltssprache. Deutsch bearbeitet Menüs und Struktur wie bisher. English bearbeitet Namen/Beschreibungen von Speisen, Vorspeisen, Dessert, Restauranttyp, Öffnungszeiten und Ankündigungen als Übersetzungen. Preise und strukturelle Zuordnung werden im englischen Modus nicht geändert. Neue Angaben zuerst auf Deutsch eintragen. Bei mehrzeiligen Texten die Zeilenstruktur erhalten.

Der zusätzliche Bereich „Englische Texte bearbeiten“ bietet eine Suche und direkte Korrekturen; die Liste zeigt bis zu 100 Suchtreffer. Herkunft KI/manuell ist sichtbar. Die maschinelle Erstübersetzung ist asynchron: Nach manuellen deutschen Änderungen außerhalb der Importzeiten kann sie bis zum nächsten stündlichen Lauf ausstehen. Eine manuell eingetragene englische Fassung ist davon unabhängig sofort nach dem nächsten Abruf verfügbar.

Neue Sprachfunktionen in der nativen App benötigen eine ausdrücklich freigegebene neue APK. Die ältere APK erhält weiterhin ihre bisher unterstützten Backend-Änderungen, aber nicht automatisch eingebauten neuen Programmcode.

## Texte zentral bearbeiten

Im Admin zeigt „App-Texte bearbeiten“ alle registrierten eigenen Bedienungstexte mit Suche, Sprachschalter und Wiederherstellung des Standards. `public.lunch_ui_texts` speichert stabile Schlüssel und getrennte deutsche/englische Texte. Die App lädt Änderungen ohne Blockieren im Drei-Sekunden-Zyklus und verwendet bei Verbindungsproblemen den letzten gespeicherten Stand. Menüs, Restaurantangaben und Ankündigungen bleiben in ihren bisherigen Editoren. Die Kontaktadresse ist als „Kontakt-E-Mail“ ebenfalls änderbar. Browser-, PDF- und native Fehler-/Zurücktexte übernehmen denselben Katalog. Originale externer Restaurantseiten/PDFs und Texte des Betriebssystems (Berechtigungen, Teilen-Dialog, App-Name im Launcher) sind davon ausgenommen. Neue Funktionen, neue Oberflächen und neue native Anbindungen benötigen weiterhin eine App-Version. Die vorhandene installierte APK muss diese Textanbindung einmal mit einem ausdrücklich gewünschten Update erhalten.

Die manuelle Sprache wird zusätzlich zum WebView-Speicher über AsyncStorage auf dem Gerät gespeichert. Sie wird vor dem ersten WebView-Aufbau gelesen und hat Vorrang vor der Systemsprache. Automatische Systemerkennung wird nicht als manuelle Auswahl gespeichert. Die Speichervorgänge sind geordnet, damit schnelle Sprachwechsel den letzten gewählten Wert behalten.
