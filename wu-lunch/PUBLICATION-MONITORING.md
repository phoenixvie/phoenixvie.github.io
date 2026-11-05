# Messung der Menü-Veröffentlichungszeiten

**Messzeitraum:** 6. November – 3. Dezember 2026. Automatische Auswertung am 4. Dezember.

**Ziel:** Ermitteln, in welchen **Zeitfenstern** ein Restaurant seinen Menüinhalt tatsächlich ändert. Der Änderungszeitpunkt selbst liegt zwischen der letzten unveränderten und der ersten geänderten Stichprobe und wird nicht als exakte Minute interpretiert.

- Freitag, Sonntag, Montag, Dienstag: 07:00, 10:00, 13:00 und 17:00 Uhr (Wien).
- Mittwoch, Donnerstag: 07:00 und 10:00 Uhr, nur für Baschly.
- Stichproben unabhängig vom normalen GitHub-Menüimport.
- Verarbeitete Ergebnisse in `wu-lunch/data/publication-observations.json`; pro Quelle letzter Hash, Format, Quelle-Gültigkeitszeitraum (wenn ermittelbar), und Zeitfenster der Änderungen.
- Kein Speiseplan wird aufgrund einer bloßen Hash-Änderung als bestätigt veröffentlicht; Datenqualität bestimmt weiterhin `update_menus.py`.
- Für Mensa-PDF wird bei jeder Messtichprobe geprüft, ob der tatsächlich verlinkte Plan geändert wurde, auch wenn der Parser den Tabelleninhalt noch nicht verifizieren kann.
- Ende: Nach 3. Dezember erfolgen automatisch keine weiteren Datenabrufe durch das Monitoring. Das GitHub-Workflow-Scheduling wird bei der geplanten Auswertung deaktiviert.
- Der normale Menüimport läuft unabhängig davon weiter.

**Bekannte Grenze:** HTML-Rahmen oder PDF-Metadaten können Hash-Änderungen ohne echte Menüänderung auslösen. Änderungen werden daher bei der Auswertung anhand von Menüinhalten und Gültigkeitszeiträumen plausibilisiert.

**Wochenend-UX:** Die Navigation enthält nur Montag bis Freitag. Samstag und Sonntag wählen den Montag der nächsten Woche; fehlende Menüs erhalten einen Hinweis pro Restaurant und es werden keine Datensätze der vorherigen Woche übernommen. Die separate Saisonkarte von L'Osteria darf weiterhin erscheinen.
