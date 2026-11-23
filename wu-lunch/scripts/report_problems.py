#!/usr/bin/env python3
"""Import-Störungen als GitHub-Issues melden und nach der Behebung wieder schließen.

Warum: Ein Lokal, dessen Karte sich nicht mehr lesen lässt, fiel bisher erst auf, wenn jemand in der App
nachsah (Karma Food, Dok Khun und OX am 23.11.2026). Dieses Skript läuft nach jedem Import und sorgt dafür,
dass für jede anhaltende Störung genau ein offenes Issue mit dem Etikett "import-stoerung" existiert –
GitHub benachrichtigt den Betreiber per E-Mail. Ist die Störung weg, wird das Issue geschlossen.

Aufruf:  python wu-lunch/scripts/report_problems.py --scope wu|wels [--dry-run]

Gemeldet wird:
  WU    Quelle im Zustand "error" seit mindestens 3 Abrufen in Folge (kurze Netzstörungen bleiben still).
  Wels  Leser scheitert an der Karte ("error", kein reiner Abruffehler) oder der Ersatzleser musste
        einspringen ("fallback").
  Beide: Lokal ganz ohne Karte für diese Woche – ab Dienstag 8 Uhr. "Noch nicht veröffentlicht" ist am
        Montag normal; steht am Dienstag immer noch nichts da, hat entweder das Lokal nichts veröffentlicht oder
        die Karte wird still nicht erkannt (falsche Überschrift, zurückgehaltene Freigabe). Beides soll ein
        Mensch ansehen.
  WU    Freigabe zurückgehalten ("withheld").
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
WU_STATUS = ROOT / "wu-lunch/status.json"
WU_DATA = ROOT / "wu-lunch/data/menus.json"
WELS_DATA = ROOT / "wu-lunch-app/preview/wels/menus.json"
LABEL = "import-stoerung"
OWNER = "phoenixvie"
NETWORK = ("OSError", "ConnectionError", "Timeout", "HTTPError", "ReadTimeout", "ConnectTimeout", "SSLError",
           "ChunkedEncodingError", "TooManyRedirects")


def missing_since_week_start(days, now):
    """True, wenn ab Dienstag 8 Uhr für die ganze Woche kein einziges Gericht vorliegt.

    Bewusst die ganze Woche: Tageskarten (Gasthaus Huber) füllen sich erst im Lauf jedes Vormittags.
    """
    if now.weekday() > 4 or now.weekday() == 0 or (now.weekday() == 1 and now.hour < 8):
        return False
    return bool(days) and not any(days.values())


SILENT = ("Für diese Woche steht noch keine Karte in der App. Entweder hat das Lokal noch nichts "
          "veröffentlicht, oder die Karte wird nicht erkannt.")


def wu_problems(status, data, now=None):
    names = {row.get("id"): row.get("name") for row in data.get("restaurants", [])}
    urls = {row.get("id"): row.get("url") or row.get("menuSourceUrl") for row in data.get("restaurants", [])}
    found = {}
    for key, row in sorted(status.get("sources", {}).items()):
        message = str(row.get("note") or row.get("error") or "ohne Angabe")
        if row.get("state") == "error" and int(row.get("consecutive_failures") or 0) >= 3:
            detail = (f"{row.get('consecutive_failures')} Abrufe in Folge fehlgeschlagen, "
                      f"letzter Erfolg: {row.get('last_success') or 'unbekannt'}")
        elif row.get("state") == "withheld":
            detail = "Die Freigabeprüfung hält die neue Karte zurück; der bisherige Stand bleibt online."
        else:
            continue
        found["wu:" + key] = {"name": names.get(key) or key, "place": "WU", "url": urls.get(key) or "",
                              "message": message, "detail": detail}
    attempt = status.get("topf_browser_attempt") or {}
    if int(attempt.get("failures") or 0) >= 3 and "wu:topfdeckel" not in found:
        # Die Wochenkarte von Topf & Deckel liest ein Browser; dessen Fehlversuche stehen nicht bei den Quellen.
        found["wu:topfdeckel"] = {"name": names.get("topfdeckel") or "Topf & Deckel", "place": "WU",
                                  "url": urls.get("topfdeckel") or "", "message": str(attempt.get("error") or "ohne Angabe"),
                                  "detail": f"{attempt.get('failures')} Fehlversuche des Browser-Imports; es erscheint "
                                            "höchstens die Tageskarte von heute."}
    if now is not None and data.get("weekStart") == (now.date() - timedelta(days=now.weekday())).isoformat():
        for row in data.get("restaurants", []):
            key = "wu:" + str(row.get("id"))
            # Saisonkarte (L'Osteria) und Dauerangebot (Oma Küche) haben bewusst keine Tageskarte.
            if key in found or row.get("status") in ("seasonal", "recurring"):
                continue
            if missing_since_week_start(row.get("days") or {}, now):
                source = status.get("sources", {}).get(row.get("id"), {})
                found[key] = {"name": row.get("name") or row.get("id"), "place": "WU", "url": urls.get(row.get("id")) or "",
                              "message": str(source.get("note") or source.get("error") or "keine Karte gelesen"),
                              "detail": SILENT}
    return found


def wels_problems(data, now=None):
    found = {}
    this_week = now is not None and data.get("weekStart") == (now.date() - timedelta(days=now.weekday())).isoformat()
    for row in data.get("restaurants", []):
        record = row.get("import") or {}
        state, message = record.get("state"), str(record.get("message") or "")
        if state == "fallback":
            detail = ("Eine Rückfallebene (" + (record.get("reader") or "Ersatzleser") + ") zeigt die Karte in einfacher "
                      "Form; der eigene Leser muss angepasst werden.")
        elif state == "error" and not message.startswith(NETWORK):
            detail = "Das Lokal wird ohne Karte angezeigt." if not any(row.get("days", {}).values()) else \
                     "Der zuletzt gelesene Stand dieser Woche bleibt sichtbar."
        elif this_week and missing_since_week_start(row.get("days") or {}, now):
            detail, message = SILENT, message or "keine Karte gelesen"
        else:
            continue
        found["wels:" + row["id"]] = {"name": row.get("name") or row["id"], "place": "Wels", "url": row.get("url") or "",
                                      "message": message or "ohne Angabe", "detail": detail}
    return found


def marker(key):
    return f"<!-- import-stoerung:{key} -->"


def issue_title(problem):
    return f"Import-Störung: {problem['name']} ({problem['place']})"


def issue_body(key, problem):
    return "\n".join([
        marker(key),
        f"Die Karte von **{problem['name']}** ({problem['place']}) lässt sich gerade nicht richtig lesen.",
        "",
        f"- Meldung: `{problem['message'][:300]}`",
        f"- Stand: {problem['detail']}",
        f"- Quelle: {problem['url']}" if problem["url"] else "- Quelle: siehe Importskript",
        "",
        "**Was zu tun ist:** In einer Claude-Code-Sitzung schreiben: „Import-Störung beheben“. Die Karte wird dann mit",
        "der Webseite verglichen, der Leser angepasst und der Fall als Testfall hinterlegt, damit er nicht wiederkehrt.",
        "",
        f"Dieses Issue schließt sich von selbst, sobald die Karte wieder gelesen wird. @{OWNER}",
    ])


def api(method, path, fields=None):
    """GitHub-REST-Aufruf über die gh-CLI (im Workflow mit dem Repository-Token). Gibt die JSON-Antwort zurück."""
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY") or OWNER + "/phoenixvie.github.io"
    command = ["gh", "api", "-X", method, f"repos/{repo}/{path}"]
    for key, value in (fields or {}).items():
        command += ["-f", f"{key}={value}"]
    done = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    return json.loads(done) if done.strip() else None


def sync(problems, scope, run=api, dry_run=False):
    """Offene Issues an die aktuellen Störungen angleichen. Gibt (neu gemeldet, geschlossen) zurück."""
    listed = run("GET", f"issues?labels={LABEL}&state=open&per_page=100") or []
    open_keys = {}
    for issue in listed:
        body = issue.get("body") or ""
        start = body.find("<!-- import-stoerung:")
        if start >= 0 and "pull_request" not in issue:
            open_keys[body[start + 21:body.find(" -->", start)]] = issue["number"]
    created, closed = [], []
    for key, problem in problems.items():
        if key in open_keys:
            continue
        created.append(key)
        if not dry_run:
            run("POST", "issues", {"title": issue_title(problem), "body": issue_body(key, problem), "labels[]": LABEL})
    for key, number in open_keys.items():
        if key.startswith(scope + ":") and key not in problems:
            closed.append(key)
            if not dry_run:
                run("POST", f"issues/{number}/comments", {"body": "Die Karte wird wieder gelesen – Störung behoben."})
                run("PATCH", f"issues/{number}", {"state": "closed"})
    return created, closed


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("wu", "wels"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    now = datetime.now(ZoneInfo("Europe/Vienna"))
    if args.scope == "wu":
        problems = wu_problems(json.loads(WU_STATUS.read_text(encoding="utf-8")),
                               json.loads(WU_DATA.read_text(encoding="utf-8")), now)
    else:
        problems = wels_problems(json.loads(WELS_DATA.read_text(encoding="utf-8")), now)
    print("Störungen:", ", ".join(f"{key} ({value['message'][:80]})" for key, value in problems.items()) or "keine")
    if not args.dry_run and problems:
        try:  # Etikett anlegen, falls es fehlt; ein vorhandenes ist kein Fehler
            api("POST", "labels", {"name": LABEL, "color": "D93F0B", "description": "Karte eines Lokals wird nicht gelesen"})
        except subprocess.CalledProcessError:
            pass
    created, closed = sync(problems, args.scope, dry_run=args.dry_run)
    print("Neu gemeldet:", ", ".join(created) or "nichts", "| Geschlossen:", ", ".join(closed) or "nichts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
