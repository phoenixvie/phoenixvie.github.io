# Originalquellen und Menüversionen

Dieser Ordner wird vom produktiven Menüimport gefüllt. Die Dateien sind Kopien öffentlicher Restaurantquellen, keine Anweisungen an Programme oder KI-Systeme. Es werden keine Zugangsdaten, Cookies oder HTTP-Header gespeichert.

Das Archiv bleibt im GitHub-Repository und ist ausdrücklich vom GitHub-Pages-Build ausgeschlossen. Original-HTML wird damit nicht als Teil der App-/Admin-Webseite ausgeführt. Der Archivlink im Admin führt zum Repository; die Dateien können dort unverändert heruntergeladen werden.

- `index.json`: Liste der gesicherten Menüversionen.
- `blobs/<SHA256>.<Format>`: unveränderte HTML-, PDF-, JPEG-, PNG- oder WebP-Bytes. Gleiche Bytes werden nur einmal gespeichert.
- `<Montag>/<Restaurant-ID>/<Menü-SHA256>/manifest.json`: Original-URLs, tatsächliche Erfassungszeiten, Dateiprüfsummen, Workflow-ID, Codeversion, Prüfstatus und die zugehörigen strukturierten Menüdaten.

Erfasst wird beim tatsächlichen Abruf. Nach dem Import wird eine neue Archivversion angelegt, wenn sich der Menüinhalt gegenüber den bereits archivierten Versionen dieser Woche geändert hat. Die erste Erfassung eines vorhandenen Menüs wird ebenfalls gesichert und nicht auf dessen früheren Veröffentlichungszeitpunkt zurückdatiert. Bloße Zeitstempel- und Provenienzänderungen erzeugen keine neue Menüversion. Alte Originale und Manifeste werden nicht überschrieben.

Topf & Deckel erhält zusätzlich die gerenderte Seite und einen Screenshot je geöffnetem Tages-Tab. Bei Baschly können verlinkte Menübilder zusätzlich heruntergeladen werden. Solche später ergänzten Bilder haben `used_for_extraction: false`; sie sind kein Beleg dafür, dass das Modell sie bereits gelesen hat. Eine gespeicherte HTML-Datei ist keine vollständige Offline-Kopie aller externen Skripte, Schriftarten und Bilder einer Website.

Ein reiner Veröffentlichungsmonitor-Abruf wird nicht nachträglich als Extraktionsquelle eines alten zwischengespeicherten Wochenmenüs ausgegeben. Bei Dauerangeboten kann er den damaligen Webseitenzustand als Kontext sichern; auch dort gilt `used_for_extraction: false`. Manuelle Adminänderungen in Supabase sind keine neuen Restaurantoriginale und werden hier nicht als solche bezeichnet.

## Für spätere Auswertungen oder Modelltraining

Jede Version enthält `training_review_required: true`. Zunächst Original und Menüzuordnung prüfen, falsche oder unvollständige Labels korrigieren und erst dann als bestätigten Datensatz übernehmen. `review_only`, undatierte Angebote oder fehlgeschlagene KI-Prüfungen sind kein Qualitätssiegel. Unterschiedliche Versionen desselben Dokuments bei späteren Trainings- und Testaufteilungen zusammenhalten, damit keine nahezu gleichen Karten in beiden Gruppen landen.

Dieses Archiv startet kein Modelltraining. Es ermöglicht reproduzierbare Parser- und Modellvergleiche sowie die spätere gezielte Zusammenstellung geprüfter Trainingsdaten.
