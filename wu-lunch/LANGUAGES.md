# Deutsch und Englisch

## Auswahl und Darstellung

Die primäre Sprache entscheidet: `de`, `de-AT`, `de-DE`, `de-CH` usw. verwenden Deutsch; alle anderen Sprachen Englisch. Im Browser ist dies `navigator.language`. Die Android-Hülle übergibt ihre über `Intl` ermittelte Systemsprache ausdrücklich an die eingebettete Oberfläche. Namen, Anschriften, Telefonnummern, E-Mail-Adressen und Linkziele bleiben unverändert. Eigene Bedienoberflächen, Datumsanzeigen und Hinweise werden lokalisiert. Externe Restaurantseiten und Original-PDF-Inhalte bleiben Originalquellen.

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
