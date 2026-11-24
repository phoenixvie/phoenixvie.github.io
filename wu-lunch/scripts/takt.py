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

Kurze GitHub-Störungen reißen die Kette nicht: Die Übergabe gilt erst, wenn der
Nachfolger wirklich bei GitHub geführt wird (sonst wird sie wiederholt), ein
nicht ausgelöster Import wird nach einer Minute erneut versucht, und eine
unbeantwortete Abfrage beim Start beendet die Wache nicht.

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
# Der Abstand zur Jobgrenze (350 Minuten im Workflow) lässt Zeit für einen noch
# laufenden Import (bis 25 Minuten) und mehrere Übergabeversuche.
BUDGET_MINUTES = 300
STEP_SECONDS = 600
STALE_SOURCE_DAYS = 8
# Ab dieser Stunde zählt Mo–Do bereits das Menü des nächsten Tages.
LOOK_AHEAD_HOUR = 14
# Überbrücken kurzer GitHub-Störungen (siehe "Selbstheilung" oben).
START_TRIES = 3
HANDOVER_CONFIRM_SECONDS = 180
MAX_FAILED_STARTS = 5
RETRY_SECONDS = 60


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


def missing_daily(data, local, daily):
    """Lokale mit täglich neuer Karte (Wels: Gasthaus Huber), deren Menü für den als Nächstes gebrauchten Tag fehlt.

    Solche Karten erscheinen erst am Vormittag des Tages. Fehlt sie, bleibt der Wächter wach (auch über Nacht,
    damit er am Morgen sicher läuft) und stößt zu festen Zeiten den zuständigen Import an. Freitagnachmittag
    zählt nicht mehr; ebenso wenig ein Lokal, das in dieser Woche bis zur Wochenmitte noch gar nichts gezeigt
    hat (Betriebsurlaub) – es hält den Wächter nicht die ganze Woche wach.
    """
    if not daily or not data:
        return []
    day = target_day(local)
    if day == local.date() and local.hour >= LOOK_AHEAD_HOUR:
        return []
    monday = day - timedelta(days=day.weekday())
    week_matches = data.get("weekStart") == monday.isoformat()
    missing = []
    for restaurant in data.get("restaurants", []):
        if restaurant.get("id") not in daily.get("restaurants", []):
            continue
        days = restaurant.get("days", {}) if week_matches else {}
        if days.get(day.isoformat()):
            continue
        earlier = [days.get((monday + timedelta(days=offset)).isoformat()) for offset in range(day.weekday())]
        if day.weekday() >= 2 and not any(earlier):
            continue
        missing.append(restaurant["id"])
    return sorted(missing)


def daily_due(local, daily, missing, last_trigger):
    """Ist jetzt ein fester Termin für den Tageskarten-Import fällig, der noch nicht bedient wurde?

    Nur am Tag selbst (nicht in der Nacht davor) und nur, solange die Karte fehlt.
    """
    if not daily or not missing or target_day(local) != local.date():
        return False
    due = [slot for slot in (datetime.combine(local.date(), clock_time(*map(int, text.split(":"))), tzinfo=local.tzinfo)
                             for text in daily.get("slots", [])) if slot <= local]
    return bool(due) and (last_trigger is None or last_trigger < due[-1])


def seconds_to_daily_slot(local, daily):
    """Sekunden bis zum nächsten Tageskarten-Termin heute (None, wenn heute keiner mehr kommt)."""
    coming = [slot for slot in (datetime.combine(local.date(), clock_time(*map(int, text.split(":"))), tzinfo=local.tzinfo)
                                for text in (daily or {}).get("slots", [])) if slot > local]
    return (coming[0] - local).total_seconds() if coming else None


def decide(now, *, config, missing, last_import_at, started_at, budget_minutes=BUDGET_MINUTES, keep_alive=False):
    """Nächster Schritt des Wächters als reine Entscheidung (ohne Nebenwirkungen)."""
    watch = config["watch"]
    local = vienna(now, config)
    if not (in_period(local, watch) or missing or keep_alive):
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


def first_watch_check(workflow, own_id, predecessor, sleep=None):
    """Läuft schon ein anderer Wächter? Übersteht kurze GitHub-Störungen.

    Bleibt die Abfrage mehrmals ohne Antwort, wacht dieser Lauf trotzdem. Ein
    doppelter Wächter ist harmlos (der Import überspringt zu dichte Starts, und
    bei der nächsten Übergabe weicht der jüngere); ein fehlender ist es nicht.
    """
    sleep = sleep or time.sleep
    for attempt in range(START_TRIES):
        try:
            return other_watch(workflow, own_id, predecessor)
        except Exception as error:
            print(f"::warning::Wächterabfrage fehlgeschlagen ({attempt + 1}/{START_TRIES}):",
                  str(error)[:200], flush=True)
            if attempt + 1 < START_TRIES:
                sleep(20)
    return None


def dispatched_runs(workflow):
    """Die jüngsten per Auftrag (nicht per Zeitplan) gestarteten Läufe eines Workflows."""
    return json.loads(gh("run", "list", "--workflow", workflow, "--event", "workflow_dispatch", "--limit", "10",
                         "--json", "databaseId,status,conclusion", check=False) or "[]")


def hand_over(workflow, branch, own_id, sleep=None):
    """Nachfolger starten und abwarten, bis GitHub ihn wirklich führt. True bei Erfolg.

    Ohne diese Bestätigung bliebe nach einer verschluckten Übergabe bis zum
    nächsten GitHub-Zeitplan (oft Stunden) niemand auf Wache. Als Nachfolger
    zählt nur ein Lauf, den es vor der Übergabe noch nicht gab und der wartet,
    läuft oder sich bereits regulär beendet hat – ein sofort gescheiterter nicht.
    """
    sleep = sleep or time.sleep
    own = int(own_id or 0)
    try:
        newest = max([int(row["databaseId"]) for row in dispatched_runs(workflow)] + [own])
    except Exception:
        newest = own
    try:
        gh("workflow", "run", workflow, "--ref", branch, "-f", "predecessor=" + own_id)
    except Exception as error:
        print("::warning::Übergabe nicht ausgelöst:", str(error)[:200], flush=True)
        return False
    for _ in range(HANDOVER_CONFIRM_SECONDS // 20):
        sleep(20)
        try:
            rows = dispatched_runs(workflow)
        except Exception:
            continue
        if any(int(row["databaseId"]) > newest
               and (row.get("status") in ACTIVE_STATES or row.get("conclusion") == "success") for row in rows):
            return True
    print("::warning::Nachfolger ist nach der Übergabe nicht erschienen.", flush=True)
    return False


def trigger_import(workflow, branch, wait_minutes=25, sleep=time.sleep, clock=time.time):
    """Import-Workflow auslösen und auf dessen Ende warten.

    Nur das Auslösen selbst darf scheitern (dann versucht es der Wächter gleich
    noch einmal). Eine gestörte Statusabfrage danach wird einfach wiederholt.
    """
    began = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    gh("workflow", "run", workflow, "--ref", branch)
    deadline = clock() + wait_minutes * 60
    seen = None
    while clock() < deadline:
        sleep(20)
        try:
            rows = json.loads(gh("run", "list", "--workflow", workflow, "--event", "workflow_dispatch",
                                 "--limit", "5", "--json", "databaseId,status,conclusion,createdAt", check=False) or "[]")
            fresh = [row for row in rows
                     if datetime.fromisoformat(row["createdAt"].replace("Z", "")) >= began - timedelta(seconds=30)]
        except Exception as error:
            print("Statusabfrage des Imports wird wiederholt:", str(error)[:120], flush=True)
            continue
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
    rival = first_watch_check(watch["workflow"], own_id, predecessor)
    if rival:
        print(f"Wächter {rival} ist bereits aktiv – dieser Lauf beendet sich.")
        return 0
    last_import = last_completed(published("data/update-status.json")[0] or {})
    failed_starts = 0
    daily, daily_trigger = watch.get("daily"), None
    while True:
        now = datetime.now(zone)
        menus, status = published("data/menus.json", "status.json")
        missing = missing_menus(menus, status, now, watch)
        open_daily = missing_daily(published(daily["file"])[0], now, daily) if daily else []
        step = decide(now, config=config, missing=missing, last_import_at=last_import, started_at=started,
                      keep_alive=bool(open_daily))
        print(now.isoformat(timespec="seconds"), step["action"], "–", step["reason"],
              "| ausständig:", ", ".join(missing + ["Tageskarte " + name for name in open_daily]) or "nichts", flush=True)
        # Tageskarte fehlt und ein Termin ist fällig: den zuständigen Import direkt anstoßen (kein WU-Import nötig).
        # Löst der Wächter ohnehin gerade einen WU-Import aus, startet dieser den Folgelauf selbst.
        if step["action"] == "sleep" and daily_due(now, daily, open_daily, daily_trigger):
            try:
                gh("workflow", "run", daily["workflow"], "--ref", branch)
                print("Tageskarten-Import angestoßen:", daily["workflow"], flush=True)
            except Exception as error:
                print("::warning::Tageskarten-Import konnte nicht angestoßen werden:", str(error)[:200], flush=True)
            daily_trigger = now
        if step["action"] in ("import", "sleep") and open_daily:
            wait = seconds_to_daily_slot(now, daily)
            if step["action"] == "sleep" and wait is not None:
                step["seconds"] = max(1, min(step["seconds"], wait))
            if step["action"] == "import":
                daily_trigger = now
        if step["action"] == "stop":
            return 0
        if step["action"] == "handover":
            if hand_over(watch["workflow"], branch, own_id):
                print("Übergabe an Nachfolger ausgelöst.")
                return 0
            # Weiter wachen und erneut übergeben, bis es klappt (längstens bis GitHub den Job beendet).
            time.sleep(RETRY_SECONDS)
            continue
        if step["action"] == "import":
            try:
                outcome = trigger_import(watch["import_workflow"], branch)
                print("Import:", json.dumps(outcome, ensure_ascii=False), flush=True)
                failed_starts = 0
            except Exception as error:  # Ein Fehlstart beendet die Wache nicht.
                failed_starts += 1
                print(f"::warning::Import konnte nicht ausgelöst werden ({failed_starts}/{MAX_FAILED_STARTS}):",
                      str(error)[:200], flush=True)
                if failed_starts < MAX_FAILED_STARTS:
                    time.sleep(RETRY_SECONDS)   # gleich noch einmal, statt den Termin auszulassen
                    continue
                failed_starts = 0               # aufgeben bis zum nächsten Termin bzw. Takt
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
    daily = watch.get("daily")
    open_daily = missing_daily(read((ROOT / daily["file"]).resolve()), local, daily) if daily else []
    if not (in_period(local, watch) or missing or open_daily):
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
