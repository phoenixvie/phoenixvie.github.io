#!/usr/bin/env bash
# Veröffentlicht die Ergebnisse eines Imports (ein Commit auf den Hauptzweig).
#
# Warum es dieses Skript gibt: Schreibt während eines Imports ein anderer Workflow
# ins Repository (PDF-Sicherung, Veröffentlichungsmonitor, zusammengeführte
# Code-Änderung), lehnt GitHub den Push ab. Früher wurde dann der gesamte Import
# verworfen und samt bezahlter KI-Lesungen wiederholt. Am 17.11.2026 ging so eine
# bereits korrekt gelesene Mensa-Karte (63 Gerichte) verloren, weil die zweite
# Lesung anders ausfiel.
#
# Jetzt wird der eigene Commit auf den neuen Stand gesetzt (rebase). Das ist
# sicher, weil die Importdateien nur von diesem Workflow geschrieben werden. Die
# einzige gemeinsam geschriebene Datei ist die Messreihe der Veröffentlichungs-
# zeiten; bei einer Überschneidung dort gilt der fremde Stand (eine einzelne
# Stichprobe weniger ist unkritisch).
#
# Rückgabe: 0 = veröffentlicht oder nichts zu tun, 3 = echte Überschneidung in
# Importdateien (Aufrufer wiederholt dann den Import auf dem neuesten Stand).
set -euo pipefail

branch="${1:?Zweig fehlt}"
message="${2:?Commit-Nachricht fehlt}"
shared="wu-lunch/data/publication-observations.json"

git add wu-lunch/data.js wu-lunch/data/menus.json wu-lunch/status.json
git add wu-lunch/data/update-status.json wu-lunch/source-archive
for optional in wu-lunch/data/menu-sanity-report.json wu-lunch/data/mensa-ai-candidate.json \
                wu-lunch/data/repair-report.json "$shared"; do
  if [[ -f "$optional" ]]; then git add "$optional"; fi
done
if git diff --cached --quiet; then
  echo "Keine Datenänderungen"
  exit 0
fi
git commit -m "$message"

for attempt in 1 2 3 4 5; do
  if git push origin HEAD:"$branch"; then
    exit 0
  fi
  echo "Push abgelehnt ($attempt/5): fremde Änderungen einarbeiten, Importergebnis behalten"
  git fetch origin "$branch"
  # --autostash: sonstige lokale Änderungen des Laufs dürfen das Umsetzen nicht verhindern.
  if git rebase --autostash "origin/$branch"; then
    continue
  fi
  if [[ "$(git diff --name-only --diff-filter=U)" == "$shared" ]]; then
    # Beim Rebase ist "ours" der fremde, bereits veröffentlichte Stand.
    git checkout --ours -- "$shared"
    git add "$shared"
    if GIT_EDITOR=true git rebase --continue; then
      continue
    fi
  fi
  git rebase --abort || true
  echo "::warning::Echte Überschneidung in Importdateien – der Import wird auf dem neuesten Stand wiederholt."
  exit 3
done
echo "::warning::Push nach fünf Versuchen nicht möglich."
exit 3
