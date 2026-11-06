#!/usr/bin/env python3
"""Fail-closed, all-or-nothing publication of independently extracted AI menus.

This script is NOT invoked by the comparison-only pilot workflow. It requires an
explicit operator invocation with a reviewed report and never calls the model.
"""
import copy
import json
import math
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "ai-pilot" / "results" / "latest.json"
DATA = ROOT / "data" / "menus.json"
JS = ROOT / "data.js"
AUDIT = ROOT / "ai-pilot" / "results" / "publication-audit.json"


def _valid_price(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 < value <= 150


def _normal_name(name):
    return " ".join(name.casefold().split())


def _check_report(report, production):
    week = date.fromisoformat(report["week_start"])
    if production.get("weekStart") != week.isoformat():
        raise ValueError("KI-Woche und aktuelle Webseite haben unterschiedliche Wochen")
    if not report.get("restaurants"):
        raise ValueError("KI-Bericht enthält keine Restaurants")
    if not report.get("checked_at") or not report.get("model"):
        raise ValueError("KI-Bericht ohne Zeitstempel oder Modell")
    return week


def prepare(report, production):
    """Return candidate data and audit; throw before changing production on any error."""
    week = _check_report(report, production)
    candidate = copy.deepcopy(production)
    sources = {s["id"]: s for s in candidate["sources"]}
    restaurants = {r["id"]: r for r in candidate["restaurants"]}
    updated = []
    rejected = []
    for ident, entry in report["restaurants"].items():
        issues = list(entry.get("validation_issues") or [])
        result = entry.get("result") or {}
        rows = result.get("items") or []
        if entry.get("error") or issues or result.get("status") != "found" or not rows:
            rejected.append({"restaurant": ident, "reason": "Fehler, Qualitätswarnung oder keine Gerichte"})
            continue
        if result.get("warnings"):
            rejected.append({"restaurant": ident, "reason": "KI-Bericht enthält offene Warnungen"})
            continue
        restaurant = restaurants.get(ident)
        source = sources.get(ident)
        if restaurant is None or source is None:
            rejected.append({"restaurant": ident, "reason": "Unbekanntes Restaurant"})
            continue
        approved = {s.get("url") for s in entry.get("sources", []) if s.get("fetched") is True}
        if not approved:
            rejected.append({"restaurant": ident, "reason": "Keine abgerufene Originalquelle"})
            continue

        try:
            days = {day: [] for day in restaurant.get("days", {})}
            seasonal = []
            seen = set()
            for item in rows:
                name = item.get("name")
                if not isinstance(name, str) or len(name.strip()) < 3:
                    raise ValueError("Ungültiger Gerichtname")
                if item.get("confidence") != "high":
                    raise ValueError("KI-Gericht ist nicht hochkonfident")
                evidence = item.get("evidence_excerpt")
                if (item.get("source_url") not in approved or
                    not isinstance(evidence, str) or len(evidence.strip()) < 8):
                    raise ValueError("Quellenbeleg fehlt")
                amount = item.get("price_eur")
                if not _valid_price(amount):
                    raise ValueError("Preis fehlt oder ist ungültig")
                when = item.get("date")
                if when is None:
                    if ident != "losteria":
                        raise ValueError("Tagesgericht ohne Datum")
                else:
                    d = date.fromisoformat(when)
                    if not week <= d <= week + timedelta(days=4):
                        raise ValueError("Gericht außerhalb der Kalenderwoche")
                    if when not in days:
                        raise ValueError("Datum fehlt im Datenmodell")
                portion = item.get("portion") or ""
                key = (when, _normal_name(name), _normal_name(portion))
                if key in seen:
                    raise ValueError("Doppeltes Gericht")
                seen.add(key)
                included = item.get("included_items") or []
                extra = item.get("extra_costs") or []
                if not isinstance(included, list) or not all(isinstance(x, str) for x in included):
                    raise ValueError("Ungültige Inklusivleistungen")
                if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
                    raise ValueError("Ungültige Zusatzkosten")
                # Never silently invent a free soup or an included menu.
                if ident == "gruenehuette" and any("suppe" in x.casefold() for x in included):
                    raise ValueError("Grüne Hütte: Suppe darf nicht als gratis inkludiert gelten")
                if ident == "mensa" and "global" in (item.get("category") or "").casefold() and any(
                    "suppe" in x.casefold() for x in included
                ):
                    raise ValueError("Global & Grill: keine automatische Suppe")
                old_items = restaurant.get("seasonal", []) if when is None else restaurant["days"][when]
                old = next((x for x in old_items if _normal_name(x.get("name", "")) == _normal_name(name)), None)
                if old:
                    if old.get("included_soup") and not any("suppe" in x.casefold() for x in included):
                        raise ValueError("Bereits bestätigte Tagessuppe würde verloren gehen")
                    old_choices = old.get("included_choices") or []
                    if old_choices and not included:
                        raise ValueError("Bereits bestätigte Inklusivwahl würde verloren gehen")
                new = {
                    "name": name.strip(),
                    "price": amount,
                    "category": item.get("category") or "Mittagsmenü",
                    "diet": (old or {}).get("diet", "unknown"),
                    "description": " | ".join(x for x in [
                        ("Portion: " + portion) if portion else "",
                        ("Inklusive: " + ", ".join(included)) if included else "",
                        ("Zusatzkosten: " + ", ".join(extra)) if extra else "",
                    ] if x),
                    "allergens": (old or {}).get("allergens", []),
                    "included_soup": (old or {}).get("included_soup"),
                    "included_choices": included,
                    "source_url": item["source_url"],
                    "evidence_excerpt": evidence,
                    "ai_confidence": "high",
                }
                if when is None:
                    seasonal.append(new)
                else:
                    days[when].append(new)
            if ident == "losteria":
                if not seasonal or any(days.values()):
                    raise ValueError("Saisonkarte unvollständig oder als Tagesmenü")
            else:
                if seasonal:
                    raise ValueError("Unerwartete Saisonkarte")
                # Do not erase a previously populated weekday. Missing days require
                # manual review, not a successful partial import.
                previous_days = {day for day, items in restaurant.get("days", {}).items() if items}
                new_days = {day for day, items in days.items() if items}
                if not previous_days.issubset(new_days):
                    raise ValueError("Bestehende Wochentage fehlen im KI-Ergebnis")
                if len(new_days) < 5:
                    raise ValueError("Nicht alle fünf Wochentage belegt")
            if ident == "losteria":
                restaurant["seasonal"] = seasonal
            else:
                restaurant["days"] = days
            # "high" is a model assertion; it is not independent verification.
            restaurant["status"] = "ai_candidate"
            restaurant["note"] = "KI-extrahiert, strukturell geprüft; unabhängige Sichtprüfung bleibt erforderlich"
            source["status"] = "ai_candidate"
            if ident != "losteria":
                restaurant["validFrom"] = source["validFrom"] = week.isoformat()
                restaurant["validUntil"] = source["validUntil"] = (week + timedelta(days=4)).isoformat()
            updated.append({"restaurant": ident, "items": len(rows)})
        except (KeyError, ValueError, TypeError, OverflowError) as error:
            # Revert this restaurant's tentative changes as well.
            restaurants[ident] = copy.deepcopy(next(r for r in production["restaurants"] if r["id"] == ident))
            sources[ident] = copy.deepcopy(next(s for s in production["sources"] if s["id"] == ident))
            rejected.append({"restaurant": ident, "reason": str(error)})

    if rejected or not updated:
        raise ValueError("Keine Veröffentlichung: " + json.dumps(rejected, ensure_ascii=False))
    # Rebuild from the validated restaurant/source objects, avoiding partial mutations.
    candidate["restaurants"] = [restaurants[r["id"]] for r in production["restaurants"]]
    candidate["sources"] = [sources[s["id"]] for s in production["sources"]]
    candidate["origin"] = "KI-Direktanalyse (strukturell geprüft, manuelle Belegprüfung ausstehend)"
    candidate["checkedAt"] = report["checked_at"]
    audit = {
        "checked_at": report["checked_at"],
        "model": report["model"],
        "week_start": report["week_start"],
        "published": updated,
        "rejected": [],
        "review_status": "requires_independent_source_review",
    }
    return candidate, audit


def _stage(path, content):
    """Stage complete content in the destination directory before replacing live files."""
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                     dir=path.parent, prefix=".wu-ai-", delete=False) as f:
        f.write(content)
        return Path(f.name)


def publish():
    report = json.loads(PILOT.read_text(encoding="utf-8"))
    prod = json.loads(DATA.read_text(encoding="utf-8"))
    candidate, audit = prepare(report, prod)
    serialized = json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
    rendered = "window.CAMPUS_LUNCH_DATA = " + json.dumps(
        candidate, ensure_ascii=False, separators=(",", ":")
    ) + ";\n"
    files = [
        (DATA, serialized),
        (JS, rendered),
        (AUDIT, json.dumps(audit, ensure_ascii=False, indent=2) + "\n"),
    ]
    staged = []
    try:
        for path, content in files:
            staged.append((path, _stage(path, content)))
        # The repository commit is the publication transaction: stage all and
        # commit once. Never run this tool against live pages directly.
        for path, temp in staged:
            os.replace(temp, path)
    finally:
        for _, temp in staged:
            temp.unlink(missing_ok=True)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    publish()
