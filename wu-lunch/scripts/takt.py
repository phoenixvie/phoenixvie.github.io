#!/usr/bin/env python3
"""Taktgeber: stößt den Menüimport pünktlich an, auch wenn GitHubs Zeitplan trödelt.

Warum es das gibt
-----------------
GitHub startet zeitgesteuerte Workflows dieses Repositorys nur wenige Male pro
Tag und oft viele Stunden zu spät. Am Montag, 16.11.2026 lief der erste
geplante Import erst um 13:42 statt ab 06:15 – deshalb erschienen Finn, Lia
und Topf & Deckel verspätet.

Wie es funktioniert
-------------------
Ein einzelner Wächter-Job wartet auf die festen Termine aus `watch.slots` in
update-policy.json und löst dann den normalen Import-Workflow aus:

- Freitagnacht (Sa 00:10): alles, was bis Freitagabend für die neue Woche
  veröffentlicht wurde. (Bis Freitag 24:00 zeigen Seite und App die laufende
  Woche; der Import stellt deshalb erst nach Mitternacht auf die neue um.)
- Samstag und Sonntag je dreimal.
- Montag ab 05:30 alle 15 Minuten, solange Menüs fehlen; dazu feste Termine.
- Dienstag bis Freitag 07:00 und 10:30, solange noch ein Menü fehlt.

Der Wächter ist von Freitag 18:00 bis Montag 18:00 immer aktiv und darüber
hinaus, solange ein Menü fehlt. Ist alles da, endet er bis zum nächsten
Wochenende; unter der Woche genügt dann das Auffangnetz des Import-Workflows.
Vor Ablauf der GitHub-Höchstlaufzeit übergibt er an einen Nachfolger.

Selbstheilung
-------------
Der Wächter wird von jedem tatsächlich gestarteten GitHub-Zeitplan neu
angestoßen (eigener Zeitplan plus `ensure` aus anderen Workflows). Läuft schon
einer, beendet sich der neue sofort. Fällt einer aus, übernimmt der nächste.
Ein verpasster Termin wird beim nächsten Start sofort nachgeholt.

Nur Standardbibliothek, damit `ensure` in jedem Workflow ohne Installation läuft.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_STATES = {"in_progress", "queued", "pending", "requested", "waiting"}
# Ein Job darf bei GitHub höchstens sechs Stunden laufen; rechtzeitig übergeben.
BUDGET_MINUTES = 320
STEP_SECONDS = 600
STALE_SOURCE_DAYS = 8
# Ab dieser Stunde zählt Mo–Do bereits das Menü des nächsten Tages.
LOOK_AHEAD_HOUR = 14


def policy():
    return json.loads((ROOT / "update-policy.json").read_text(encoding="utf-8"))


def vienna(now, config):
    return now.astimezone(ZoneInfo(config["timezone"]))


def _minutes(text):
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def _week_minute(local):
    """Minuten seit Sonntag 00:00 (0 = Sonntag wie in update-policy.json)."""
    return (local.isoweekday() % 7) * 1440 + local.hour * 60 + local.minute


def in_period(local, watch):
    position = _week_minute(local)
    for period in watch.get("periods", []):
        start = period["from"][0] * 1440 + _minutes(period["from"][1])
        end = period["to"][0] * 1440 + _minutes(period["to"][1])
        if start <= end:
            if start <= position < end:
                return True
        elif position >= start or position < end:  # Zeitraum über das Wochenende hinaus
            return True
    return False


def slots_on(day, watch, zone):
    texts = watch.get("slots", {}).get(str(day.isoweekday() % 7), [])
    return sorted(datetime.combine(day, clock_time(*map(int, text.split(":"))), tzinfo=zone) for text in texts)


def latest_slot(local, watch):
    """Jüngster fester Termin, der bereits fällig war."""
    for back in range(8):
        due = [slot for slot in slots_on(local.date() - timedelta(days=back), watch, local.tzinfo) if slot <= local]
        if due:
            return due[-1]
    return None


def next_slot(local, watch):
    for ahead in range(8):
        coming = [slot for slot in slots_on(local.date() + timedelta(days=ahead), watch, local.tzinfo) if slot > local]
        if coming:
            return coming[0]
    return None


def dense_interval(local, watch):
    """Minutentakt eines dichten Zeitfensters (Montagvormittag) oder None."""
    minute = local.hour * 60 + local.minute
    for window in watch.get("dense", []):
        if local.isoweekday() % 7 == window["day"] and _minutes(window["from"]) <= minute < _minutes(window["to"]):
            return window["every_minutes"]
    return None


def target_day(local):
    """Tag, dessen Menü als Nächstes gebraucht wird.

    Am Wochenende der kommende Montag; Montag bis Donnerstag ab dem Nachmittag
    schon der nächste Tag, damit der Wächter über Nacht aktiv bleibt, wenn für
    morgen noch etwas fehlt. Freitagnachmittag bleibt Freitag: Die neue Woche
    beginnt für Import und Anzeige erst am Samstag.
    """
    today = local.date()
    if today.weekday() >= 5:
        return today + timedelta(days=7 - today.weekday())
    if today.weekday() <= 3 and local.hour >= LOOK_AHEAD_HOUR:
        return today + timedelta(days=1)
    return today


def missing_menus(data, status, local, watch):
    """Restaurants ohne Menü für den als Nächstes gebrauchten Tag.

    Dauerangebote/Saisonkarten zählen nicht. Eine Quelle, die seit über einer
    Woche nichts mehr geliefert hat, braucht einen Menschen – sie hält den
    Wächter nicht endlos aktiv.
    """
    day = target_day(local)
    monday = day - timedelta(days=day.weekday())
    skipped = set(watch.get("untracked", []))
    restaurants = [r for r in (data or {}).get("restaurants", []) if r.get("id") not in skipped]
    if (data or {}).get("weekStart") != monday.isoformat():
        return sorted(r["id"] for r in restaurants) or ["*"]
    missing = []
    for restaurant in restaurants:
        if restaurant.get("days", {}).get(day.isoformat()):
            continue
        last = ((status or {}).get("sources", {}).get(restaurant["id"], {}) or {}).get("last_success")
        try:
            stale = (local - datetime.fromisoformat(last)).days >= STALE_SOURCE_DAYS if last else False
        except (TypeError, ValueError):
            stale = False
        if not stale:
            missing.append(restaurant["id"])
    return sorted(missing)


def decide(now, *, config, missing, last_import_at, started_at, budget_minutes=BUDGET_MINUTES):
    """Nächster Schritt des Wächters als reine Entscheidung (ohne Nebenwirkungen)."""
    watch = config["watch"]
    local = vienna(now, config)
    if not (in_period(local, watch) or missing):
        return {"action": "stop", "reason": "außerhalb des Wachzeitraums und kein Menü ausständig"}
    if (now - started_at).total_seconds() >= budget_minutes * 60:
        return {"action": "handover", "reason": "Laufzeitgrenze des Jobs erreicht"}
    slot = latest_slot(local, watch)
    if last_import_at is None:
        return {"action": "import", "reason": "noch kein Import bekannt"}
    if slot is not None and last_import_at < slot:
        return {"action": "import", "reason": "fester Termin " + slot.strftime("%d.%m. %H:%M")}
    pause = STEP_SECONDS
    every = dense_interval(local, watch) if missing else None
    if every:
        waited = (now - last_import_at).total_seconds()
        if waited >= every * 60:
            return {"action": "import", "reason": f"Menüs fehlen; letzter Import vor {int(waited // 60)} Minuten (Takt {every})"}
        pause = every * 60 - waited
    coming = next_slot(local, watch)
    if coming is not None:
        pause = min(pause, (coming - local).total_seconds())
    return {"action": "sleep", "seconds": max(1, min(pause, STEP_SECONDS)),
            "reason": "wartet auf " + (coming.strftime("%d.%m. %H:%M") if coming else "den nächsten Termin")
                      + (f" bzw. den {every}-Minuten-Takt" if every else "")}


# ---------------------------------------------------------------------------
# Nebenwirkungen: GitHub-CLI und Git. In Tests ersetzt.
# ---------------------------------------------------------------------------

def gh(*args, check=True):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if check and result.returncode != 0:
        raise RuntimeError("gh " + " ".join(args[:3]) + ": " + result.stderr.strip()[:300])
    return result.stdout


def published(*paths):
    """Dateien vom aktuellen Stand des Hauptzweigs lesen (einmal frisch abgerufen)."""
    branch = (os.environ.get("WU_DEFAULT_BRANCH") or "master")
    try:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "--quiet", "--depth=1", "origin", branch],
                       capture_output=True, check=True, timeout=120)
    except Exception as error:
        print("Hauptzweig nicht abrufbar:", str(error)[:120], flush=True)
        return [None for _ in paths]
    result = []
    for path in paths:
        try:
            raw = subprocess.run(["git", "-C", str(ROOT), "show", f"FETCH_HEAD:./{path}"],
                                 capture_output=True, check=True, timeout=30).stdout
            result.append(json.loads(raw.decode("utf-8")))
        except Exception as error:
            print("Stand nicht lesbar:", path, str(error)[:120], flush=True)
            result.append(None)
    return result


def other_watch(workflow, own_id, predecessor):
    """Kennung eines anderen laufenden Wächters, der Vorrang hat (ältere Laufnummer)."""
    rows = json.loads(gh("run", "list", "--workflow", workflow, "--limit", "30",
                         "--json", "databaseId,status") or "[]")
    ignore = {str(own_id), str(predecessor)}
    older = [row["databaseId"] for row in rows
             if row.get("status") in ACTIVE_STATES and str(row["databaseId"]) not in ignore
             and (not own_id or int(row["databaseId"]) < int(own_id))]
    return min(older) if older else None


def trigger_import(workflow, branch, wait_minutes=25, sleep=time.sleep, clock=time.time):
    """Import-Workflow auslösen und auf dessen Ende warten."""
    began = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    gh("workflow", "run", workflow, "--ref", branch)
    deadline = clock() + wait_minutes * 60
    seen = None
    while clock() < deadline:
        sleep(20)
        rows = json.loads(gh("run", "list", "--workflow", workflow, "--event", "workflow_dispatch",
                             "--limit", "5", "--json", "databaseId,status,conclusion,createdAt", check=False) or "[]")
        fresh = [row for row in rows
                 if datetime.fromisoformat(row["createdAt"].replace("Z", "")) >= began - timedelta(seconds=30)]
        if not fresh:
            continue
        seen = max(fresh, key=lambda row: row["databaseId"])
        if seen.get("status") == "completed":
            return seen
    return seen


def last_completed(record):
    try:
        return datetime.fromisoformat(record["last_completed"])
    except (TypeError, KeyError, ValueError):
        return None


def run():
    config = policy()
    watch = config["watch"]
    branch = (os.environ.get("WU_DEFAULT_BRANCH") or "master")
    own_id = os.environ.get("GITHUB_RUN_ID", "")
    predecessor = os.environ.get("WU_TAKT_PREDECESSOR", "")
    zone = ZoneInfo(config["timezone"])
    started = datetime.now(zone)
    rival = other_watch(watch["workflow"], own_id, predecessor)
    if rival:
        print(f"Wächter {rival} ist bereits aktiv – dieser Lauf beendet sich.")
        return 0
    last_import = last_completed(published("data/update-status.json")[0] or {})
    while True:
        now = datetime.now(zone)
        menus, status = published("data/menus.json", "status.json")
        missing = missing_menus(menus, status, now, watch)
        step = decide(now, config=config, missing=missing, last_import_at=last_import, started_at=started)
        print(now.isoformat(timespec="seconds"), step["action"], "–", step["reason"],
              "| ausständig:", ", ".join(missing) or "nichts", flush=True)
        if step["action"] == "stop":
            return 0
        if step["action"] == "handover":
            gh("workflow", "run", watch["workflow"], "--ref", branch, "-f", "predecessor=" + own_id)
            print("Übergabe an Nachfolger ausgelöst.")
            return 0
        if step["action"] == "import":
            try:
                outcome = trigger_import(watch["import_workflow"], branch)
                print("Import:", json.dumps(outcome, ensure_ascii=False), flush=True)
            except Exception as error:  # Ein Fehlstart beendet die Wache nicht.
                print("::warning::Import konnte nicht ausgelöst werden:", str(error)[:200], flush=True)
            last_import = datetime.now(zone)
            continue
        time.sleep(max(5, step["seconds"]))


def ensure():
    """Aus anderen Workflows: Wächter starten, falls er gebraucht wird und keiner läuft."""
    config = policy()
    watch = config["watch"]
    now = datetime.now(ZoneInfo(config["timezone"]))
    local = vienna(now, config)
    data_path, status_path = ROOT / "data/menus.json", ROOT / "status.json"
    read = lambda path: json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    missing = missing_menus(read(data_path), read(status_path), local, watch)
    if not (in_period(local, watch) or missing):
        print("Wächter derzeit nicht nötig.")
        return 0
    if other_watch(watch["workflow"], "", ""):
        print("Wächter läuft bereits.")
        return 0
    gh("workflow", "run", watch["workflow"], "--ref", (os.environ.get("WU_DEFAULT_BRANCH") or "master"))
    print("Wächter gestartet.")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "run":
        sys.exit(run())
    if command == "ensure":
        try:
            sys.exit(ensure())
        except Exception as error:  # Hilfsschritt darf den aufrufenden Workflow nie scheitern lassen.
            print("::warning::Wächterprüfung nicht möglich:", str(error)[:200])
            sys.exit(0)
    raise SystemExit("Unbekannter Befehl: " + command)
