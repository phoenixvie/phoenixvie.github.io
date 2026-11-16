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
Rund um den Wochenstart (Standard: Sonntag 17:00 bis Montag 13:30, siehe
`watch` in update-policy.json) hält ein einzelner Wächter-Job durch: Er wartet,
löst den normalen Import-Workflow aus und übergibt vor Ablauf seiner Laufzeit
an einen Nachfolger. Solange für den aktuellen Tag noch Menüs fehlen, prüft er
vormittags alle 15 Minuten, sonst stündlich; nachts ruht er.

Selbstheilung
-------------
Der Wächter wird von jedem tatsächlich gestarteten GitHub-Zeitplan neu
angestoßen (eigener Zeitplan plus `ensure` aus anderen Workflows). Läuft schon
einer, beendet sich der neue sofort. Fällt einer aus, übernimmt der nächste.

Nur Standardbibliothek, damit `ensure` in jedem Workflow ohne Installation läuft.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_STATES = {"in_progress", "queued", "pending", "requested", "waiting"}
# Ein Job darf bei GitHub höchstens sechs Stunden laufen; rechtzeitig übergeben.
BUDGET_MINUTES = 320
STEP_SECONDS = 600
STALE_SOURCE_DAYS = 8
# Wochenkarte gilt als veröffentlicht: Ein einzelner leerer Tag ist dann Absicht
# des Restaurants (z. B. Feiertag) und kein Grund für Prüfungen im 15-Minuten-Takt.
PUBLISHED_STATES = {"verified", "ai_checked", "ai_crosschecked", "undated", "current"}


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


def in_hot(local, watch):
    hot = watch["hot"]
    return (local.isoweekday() % 7 in hot["days"]
            and _minutes(hot["from"]) <= local.hour * 60 + local.minute < _minutes(hot["to"]))


def quiet_seconds(local, watch):
    """Sekunden bis zum Ende der Nachtruhe; 0 außerhalb der Nachtruhe."""
    quiet = watch["quiet"]
    start, end = _minutes(quiet["from"]), _minutes(quiet["to"])
    minute = local.hour * 60 + local.minute
    if start > end:  # über Mitternacht
        if minute >= start:
            return (1440 - minute + end) * 60 - local.second
        if minute < end:
            return (end - minute) * 60 - local.second
        return 0
    return (end - minute) * 60 - local.second if start <= minute < end else 0


def target_day(today):
    """Tag, dessen Menü Besucher jetzt sehen: heute, am Wochenende der nächste Montag."""
    if today.weekday() >= 5:
        return today + timedelta(days=7 - today.weekday())
    return today


def missing_menus(data, status, local, watch):
    """Restaurants ohne Menü für den angezeigten Tag (Grund, weiter zu prüfen).

    Dauerangebote/Saisonkarten zählen nicht. Hat ein Restaurant seine
    Wochenkarte bereits geprüft veröffentlicht und nur dieser Tag ist leer,
    gilt das als Absicht (z. B. Feiertag). Eine Quelle, die seit über einer
    Woche nichts mehr geliefert hat, braucht einen Menschen – sie hält den
    Wächter nicht endlos im 15-Minuten-Takt.
    """
    day = target_day(local.date())
    monday = day - timedelta(days=day.weekday())
    skipped = set(watch.get("untracked", []))
    restaurants = [r for r in (data or {}).get("restaurants", []) if r.get("id") not in skipped]
    if (data or {}).get("weekStart") != monday.isoformat():
        return sorted(r["id"] for r in restaurants) or ["*"]
    missing = []
    for restaurant in restaurants:
        days = restaurant.get("days", {})
        if days.get(day.isoformat()):
            continue
        if restaurant.get("status") in PUBLISHED_STATES and any(days.values()):
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
    hot_gap = in_hot(local, watch) and bool(missing)
    if not (in_period(local, watch) or hot_gap):
        return {"action": "stop", "reason": "außerhalb des Wachzeitraums und kein Menü ausständig"}
    if (now - started_at).total_seconds() >= budget_minutes * 60:
        return {"action": "handover", "reason": "Laufzeitgrenze des Jobs erreicht"}
    resting = quiet_seconds(local, watch)
    if resting > 0:
        return {"action": "sleep", "seconds": min(resting, STEP_SECONDS), "reason": "Nachtruhe"}
    interval = watch["interval_minutes"]["hot_incomplete" if hot_gap else "default"]
    if last_import_at is None:
        return {"action": "import", "reason": "noch kein Import in diesem Wachzeitraum bekannt"}
    waited = (now - last_import_at).total_seconds()
    if waited >= interval * 60:
        return {"action": "import", "reason": f"letzter Import vor {int(waited // 60)} Minuten (Takt {interval})"}
    return {"action": "sleep", "seconds": min(interval * 60 - waited, STEP_SECONDS),
            "reason": f"nächster Import im {interval}-Minuten-Takt"}


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
        time.sleep(max(30, step["seconds"]))


def ensure():
    """Aus anderen Workflows: Wächter starten, falls er gebraucht wird und keiner läuft."""
    config = policy()
    watch = config["watch"]
    now = datetime.now(ZoneInfo(config["timezone"]))
    local = vienna(now, config)
    data_path, status_path = ROOT / "data/menus.json", ROOT / "status.json"
    read = lambda path: json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    missing = missing_menus(read(data_path), read(status_path), local, watch)
    if not (in_period(local, watch) or (in_hot(local, watch) and missing)):
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
