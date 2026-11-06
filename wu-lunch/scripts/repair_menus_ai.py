#!/usr/bin/env python3
"""WU Lunch: Luna extraction with evidence-anchored live-data repair.

Luna never edits code and never publishes an unverified menu.  A newly found
item is added to live data only when its original source, week, exact quoted
dish words and any displayed price are independently verified in this module.
"""
from __future__ import annotations

import argparse
import copy
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import update_menus as legacy

spec = importlib.util.spec_from_file_location("wu_lunch_ai_direct", ROOT / "ai-pilot" / "ai_direct.py")
ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)

DATA = ROOT / "data" / "menus.json"
FRONTEND = ROOT / "data.js"
STATUS = ROOT / "status.json"
REPORT = ROOT / "data" / "repair-report.json"
TZ = ZoneInfo("Europe/Vienna")
IDS = tuple(ai.SOURCES)
# No silent model replacement of dynamically selected tabs, seasonal boards,
# photo-based pricing or PDF cells: those require their own acquisition checks.
AUTO_PRICE_IDS = {"lia", "campus", "glashaus", "gruenehuette", "baschly"}
# Sources with dated HTML menus.  Luna is the complete second extractor for
# these sources; it may add an independently proven item that the parser did
# not recognise, rather than only reporting it as ``review_only``.
AUTO_FULL_MENU_IDS = {"lia", "campus", "glashaus", "gruenehuette", "baschly", "karmafood"}
URGENT = ("campus", "lia", "mensa", "topfdeckel", "gruenehuette", "glashaus", "baschly", "losteria", "omakueche", "karmafood", "finn")


def normalized(text):
    return re.sub(r"[^\w]+", " ", str(text or "").casefold(), flags=re.UNICODE).strip()


def money_values(quote):
    """Read explicit EUR prices, not dates, years or bare quantities."""
    patterns = (
        r"(?:€|EUR)\s*(\d{1,3}(?:[.,]\d{2})?)",
        r"(\d{1,3}(?:[.,]\d{2})?)\s*(?:€|EUR)\b",
        r"(?<![\d./])(\d{1,3}[.,]\d{2})(?![\d./])",
    )
    values = set()
    for pattern in patterns:
        for value in re.findall(pattern, quote, re.I):
            try:
                amount = Decimal(value.replace(",", "."))
                if Decimal("0") < amount <= Decimal("150"):
                    values.add(amount)
            except InvalidOperation:
                pass
    return values


def issue_codes(data, status, ident, today):
    """Diagnose both importer failures and silent data quality regressions."""
    r = next(x for x in data["restaurants"] if x["id"] == ident)
    codes = set()
    source_state = status.get("sources", {}).get(ident, {}).get("state", "")
    if source_state in ("error", "failed", "not_published"):
        codes.add("source_" + source_state)
    if ident in ("losteria", "omakueche"):
        if not r.get("seasonal") and ident == "losteria":
            codes.add("missing_seasonal")
        return sorted(codes)
    for day, items in r.get("days", {}).items():
        if day > today.isoformat():
            continue
        if not items:
            codes.add("missing_day")
        for item in items:
            if item.get("price") is None and item.get("category", "").casefold() not in ("tagessuppe",):
                codes.add("missing_price")
            if ident == "topfdeckel" and item.get("category", "").casefold() in ("hauptgericht", "suppe"):
                if item.get("price_small") is None or item.get("price_large") is None:
                    codes.add("missing_portion")
            if ident == "mensa" and item.get("category", "").casefold() == "global & grill":
                if item.get("included_soup") or any("suppe" in x.casefold() for x in (item.get("included_choices") or [])):
                    codes.add("incorrect_included_soup")
    return sorted(codes)


def choose_restaurants(data, status, today, limit=6, all_restaurants=False):
    if all_restaurants:
        return list(IDS)[:limit]
    findings = {ident: issue_codes(data, status, ident, today) for ident in IDS}
    # Dedicated PDF/browser/photo paths do not consume Luna HTML-call budget.
    specialized = [ident for ident in ("mensa", "topfdeckel", "omakueche", "karmafood", "finn") if findings[ident]]
    flagged = [ident for ident in URGENT if findings[ident] and ident not in specialized]
    # Rotate persistent failures: no single broken restaurant can starve the rest.
    checked = status.get("ai_repair", {})
    flagged.sort(key=lambda ident: (checked.get(ident, {}).get("last_checked", ""), URGENT.index(ident)))
    rotation = [ident for ident in IDS if ident not in flagged and ident not in specialized]
    reserve = 1 if rotation and limit > 1 else 0
    selected = flagged[:limit - reserve]
    if reserve:
        selected.append(rotation[today.toordinal() % len(rotation)])
    if len(selected) < limit:
        selected.extend(ident for ident in flagged if ident not in selected)
        selected = selected[:limit]
    return list(dict.fromkeys(selected + specialized))


def needs_ai_review(ident, status, today):
    """Use Luna on every newly published or changed HTML source, not only errors."""
    prior=(status.get("ai_repair") or {}).get(ident,{})
    current=(status.get("sources") or {}).get(ident,{})
    digest=current.get("content_sha256")
    if prior.get("action") in ("failed_no_changes","skipped_no_key","budget_exhausted"):
        return prior.get("last_checked","")[:10] != today.isoformat()
    # Only skip an unchanged, already audited version of the ORIGINAL source.
    # Model prompt/parser revisions invalidate a previous review.
    if prior.get("review_version") != "complete-v4-row-evidence":
        return True
    current_week=legacy.target_week_monday(today).isoformat()
    if prior.get("review_week_start") != current_week:
        return True
    if digest and prior.get("source_fingerprint") == digest and prior.get("last_checked"):
        return False
    if not digest and prior.get("last_checked","")[:10] == today.isoformat():
        return False
    return True


def source_snapshots(inputs, sources):
    """Bind model excerpts to the *same original fetch* supplied to the API."""
    html_inputs = {}
    for block in inputs:
        for part in block.get("content", []):
            if part.get("type") != "input_text":
                continue
            value = part.get("text", "")
            if not value.startswith("ORIGINAL-HTML-QUELLE: "):
                continue
            header = value.split("\n", 2)
            if len(header) < 3:
                continue
            url = header[0].partition(": ")[2]
            sha = header[1].partition("SHA256: ")[2]
            html = header[2]
            html_inputs[url] = {"text": normalized(BeautifulSoup(html, "html.parser").get_text(" ", strip=True)),
                                "sha256": sha}
    approved = {s["url"]: s for s in sources if s.get("fetched") and not s.get("truncated") and s.get("type") == "html"}
    return {url: item for url, item in html_inputs.items()
            if url in approved and item["sha256"] == approved[url].get("sha256")}


def documented_current_week(source, ident, monday, cache):
    """Check freshness with real retrieved HTML, never the model's period claim."""
    url, source_info = source
    if url in cache:
        return cache[url]
    try:
        final, raw = ai.safe_source_get(url)
        if final != url or hashlib.sha256(raw).hexdigest() != source_info["sha256"]:
            cache[url] = False
            return False
        text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
        dates = legacy.period(text)
        if dates is not None:
            cache[url] = dates[0] == monday and dates[1] in (
                monday + timedelta(days=3), monday + timedelta(days=4))
            return cache[url]
        # Some sites omit a complete ISO year in their visible heading;
        # only trust a source-specific deterministic parser which independently
        # verifies the requested week.
        parsers = {
            "lia": legacy.parse_lia_week,
            "campus": legacy.parse_campus,
            "glashaus": legacy.parse_glashaus,
            "gruenehuette": legacy.parse_gruenehuette,
        }
        parser = parsers.get(ident)
        if parser is None:
            cache[url] = False
        else:
            _, validity = parser(raw, monday)
            cache[url] = validity is not None and validity[0] == monday
    except Exception:  # Source or parser failure makes the evidence unusable.
        cache[url] = False
    return cache[url]


def eligible_price_fix(ident, candidate, current, sources, snapshots, monday, freshness):
    """Fail closed if price, quote, date, source or dish anchor is ambiguous."""
    if ident not in AUTO_PRICE_IDS or current.get("price") is not None:
        return False
    if candidate.get("confidence") != "high" or candidate.get("date") != current.get("_date"):
        return False
    if normalized(candidate.get("name")) != normalized(current.get("name")):
        return False
    if candidate.get("portion"):  # requires separate portion-price mapping
        return False
    url = candidate.get("source_url")
    fetched = next((s for s in sources if s.get("url") == url and s.get("fetched")), None)
    snap = snapshots.get(url)
    if not fetched or not snap:
        return False
    quote = candidate.get("evidence_excerpt") or ""
    nq = normalized(quote)
    if len(nq) < 12 or nq not in snap["text"]:
        return False
    # More than a general tariff: quoted text must describe this particular dish.
    dish_tokens = [t for t in normalized(current.get("name")).split() if len(t) >= 4]
    if len(dish_tokens) < 2 or sum(token in nq.split() for token in dish_tokens) < max(
        2, int(len(dish_tokens) * 0.7 + 0.999)):
        return False
    try:
        amount = Decimal(str(candidate.get("price_eur")))
        if not (Decimal("0") < amount <= Decimal("150")) or money_values(quote) != {amount}:
            return False
    except (TypeError, InvalidOperation):
        return False
    if not documented_current_week((url, fetched), ident, monday, freshness):
        return False
    return True


def apply_safe_price_fixes(ident, model_result, data, sources, snapshots, monday, today):
    restaurant = next(r for r in data["restaurants"] if r["id"] == ident)
    by_key = {}
    for day, meals in restaurant.get("days", {}).items():
        for meal in meals:
            by_key.setdefault((day, normalized(meal.get("name"))), []).append(meal)
    repaired = []
    source_cache = {}
    for row in model_result.get("items", []):
        day = row.get("date")
        if not isinstance(day, str) or day > today.isoformat():
            continue
        matches = by_key.get((day, normalized(row.get("name"))), [])
        if len(matches) != 1:
            continue
        item = matches[0]
        item["_date"] = day  # temporary validation hint, never store it
        try:
            approved = eligible_price_fix(ident, row, item, sources, snapshots, monday, source_cache)
        finally:
            del item["_date"]
        if not approved:
            continue
        # Do not modify any originally confirmed price or optional side.
        item["price"] = float(row["price_eur"])
        item["price_source"] = row["source_url"]
        item["price_evidence"] = row["evidence_excerpt"]
        item["price_source_sha256"] = snapshots[row["source_url"]]["sha256"]
        item["price_verification"] = "exact-source-quote-and-week"
        repaired.append({"date": day, "name": item["name"], "price": item["price"]})
    return repaired


def add_verified_missing_sides(ident, result, data, sources, snapshots, monday, today):
    """Publish independently proven, standalone Luna discoveries.

    The historical name is kept for callers/tests.  This now covers every
    category, so a complete Luna extraction can fix a missed main dish as
    well as soup, salad and dessert.  It deliberately does *not* infer menu
    inclusions: entries carrying included_items remain diagnostics until a
    restaurant-specific importer can prove the relationship.
    """
    if ident not in AUTO_FULL_MENU_IDS:
        return []
    restaurant=next(r for r in data["restaurants"] if r["id"]==ident)
    cache={}
    added=[]
    for row in result.get("items",[]):
        day=row.get("date")
        category=(row.get("category") or "").strip()
        if not category or len(category)>60 or day not in restaurant.get("days",{}) or day>today.isoformat():
            continue
        name=row.get("name") or ""
        if not 5 <= len(name) <= 150 or row.get("confidence")!="high" or row.get("included_items"):
            continue
        if any(normalized(x.get("name"))==normalized(name) for x in restaurant["days"][day]):
            continue
        url=row.get("source_url")
        source=next((s for s in sources if s.get("url")==url and s.get("fetched")),None)
        snap=snapshots.get(url)
        if not source or not snap:
            continue
        quote=row.get("evidence_excerpt") or ""
        nq=normalized(quote)
        words=[w for w in normalized(name).split() if len(w)>=4]
        if len(nq)<12 or nq not in snap["text"] or not words or not all(w in nq.split() for w in words):
            continue
        amount=None
        if row.get("price_eur") is not None:
            try:
                amount=Decimal(str(row["price_eur"]))
                if not (Decimal("0")<amount<=Decimal("150")) or money_values(quote)!={amount}:
                    continue
            except (InvalidOperation, TypeError):
                continue
        elif money_values(quote):
            # A quote containing a price while the model emits null is
            # ambiguous; do not publish it as an unpriced dish.
            continue
        if not documented_current_week((url,source),ident,monday,cache):
            continue
        if "suppe" in normalized(category) and "suppe" not in normalized(name):
            continue
        restaurant["days"][day].insert(0,{
            "name":name.strip(),"price":float(amount) if amount is not None else None,
            "category":category,"diet":"unknown",
            "description":"Luna-Vollabgleich; separat belegt, nicht als Inklusivleistung interpretiert.",
            "allergens":[],"included_soup":None,"included_choices":[],
            "source_url":url,"price_evidence":quote,
            "price_source_sha256":snap["sha256"],
            "price_verification":"ai-exact-source-quote-and-independent-week",
        })
        added.append({"date":day,"name":name,"price":float(amount) if amount is not None else None})
    return added


def publishable_result(result, validation):
    """Warnings are diagnostic; unverified rows still never reach live data."""
    return result.get("status") == "found" and not validation


def analyze_one(ident, data, status, monday, today, key, model):
    issues = issue_codes(data, status, ident, today)
    # Interactive browser and PDF are handled by their dedicated import paths.
    if ident == "topfdeckel":
        return {"restaurant": ident, "issues": issues, "action": "browser_import", "repairs": []}
    if ident == "mensa":
        return {"restaurant": ident, "issues": issues, "action": "dedicated_pdf_ai", "repairs": []}
    if ident == "omakueche":
        return {"restaurant": ident, "issues": issues, "action": "check_price_photo_manually", "repairs": []}
    if ident == "finn":
        return {"restaurant": ident, "issues": issues, "action": "dedicated_image_ai", "repairs": []}
    now = datetime.now(TZ)
    inputs, sources = ai.build_inputs(ident, now, monday)
    result, usage = ai.call_model(key, model, inputs)
    validation = ai.validate(result, sources, monday, ident)
    snapshots = source_snapshots(inputs, sources)
    result_issues = list(validation) + list(result.get("warnings") or [])
    if result.get("status") != "found":
        result_issues.append("Keine eindeutig veröffentlichte aktuelle Karte")
    # A dated AI entry without an independently checked source is not proof.
    draft = copy.deepcopy(data)
    repaired = []
    if publishable_result(result, validation) and ident in AUTO_PRICE_IDS:
        repaired = apply_safe_price_fixes(ident, result, draft, sources, snapshots, monday, today)
        repaired.extend(add_verified_missing_sides(ident, result, draft, sources, snapshots, monday, today))
        if repaired:
            legacy.validate_meal_components(draft)
            data.clear()
            data.update(draft)
    restaurant = next(r for r in data["restaurants"] if r["id"] == ident)
    existing = {((day, normalized(i.get("name")))) for day, rows in restaurant.get("days", {}).items() for i in rows}
    ai_keys = {(i.get("date"), normalized(i.get("name"))) for i in result.get("items", [])}
    missing = list(ai_keys - existing)
    absent = list(existing - ai_keys)
    return {
        "restaurant": ident, "issues": issues, "action": "live_repaired" if repaired else "review_only",
        "repairs": repaired, "validation_issues": result_issues[:20],
        "ai_only_items": len(missing), "parser_only_items": len(absent),
        "ai_only_examples": [f"{day}: {name}" for day, name in sorted(missing)[:5]],
        "parser_only_examples": [f"{day}: {name}" for day, name in sorted(absent)[:5]],
        "source_hashes": {s["url"]: s.get("sha256") for s in sources if s.get("fetched")},
        "usage": usage,
    }


def run(today, *, model="gpt-6-luna", max_calls=2, selected=None):
    monday = legacy.target_week_monday(today)
    data = json.loads(DATA.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    if data.get("weekStart") != monday.isoformat():
        raise ValueError("Datenbankwoche stimmt nicht mit der aktuellen Woche überein")
    if model not in ai.ALLOWED_MODELS:
        raise ValueError("Nicht freigegebenes KI-Modell")
    # Always audit all six supported text/HTML sources whenever their
    # original menu fingerprint changes. Dedicated image/PDF/browser paths
    # already check the remaining five restaurants.
    targets = list(IDS) if selected == "all" else (
        [selected] if selected else [
            ident for ident in ("lia","campus","glashaus","gruenehuette","baschly","losteria",
                               "karmafood","mensa","topfdeckel","finn","omakueche")
            if needs_ai_review(ident,status,today)
        ])
    if any(x not in IDS for x in targets):
        raise ValueError("Unbekanntes Restaurant")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    report = {"checked_at": datetime.now(TZ).isoformat(timespec="seconds"),
              "week_start": monday.isoformat(), "model": model,
              "api_calls": 0, "results": []}
    remaining = max_calls
    for ident in targets:
        if ident in ("topfdeckel", "mensa", "omakueche", "finn"):
            report["results"].append(analyze_one(ident, data, status, monday, today, "", model))
            continue
        if not key:
            report["results"].append({"restaurant": ident, "action": "skipped_no_key",
                                      "issues": issue_codes(data, status, ident, today), "repairs": []})
            continue
        if remaining <= 0:
            report["results"].append({"restaurant": ident, "action": "budget_exhausted", "repairs": []})
            continue
        # At most one paid call per restaurant/day, regardless of repeated Actions runs.
        prior = (status.get("ai_repair", {}) or {}).get(ident, {})
        if not needs_ai_review(ident,status,today) and selected is None:
            report["results"].append({"restaurant": ident, "action": "already_checked_today", "repairs": []})
            continue
        remaining -= 1
        report["api_calls"] += 1
        try:
            entry = analyze_one(ident, data, status, monday, today, key, model)
        except Exception as error:
            entry = {"restaurant": ident, "action": "failed_no_changes", "repairs": [],
                     "error": str(error)[:240]}
        report["results"].append(entry)
        status.setdefault("ai_repair", {})[ident] = {
            "last_checked": report["checked_at"],
            "review_version":"complete-v4-row-evidence",
            "review_week_start":monday.isoformat(),
            "source_fingerprint":status.get("sources",{}).get(ident,{}).get("content_sha256"),
            "model": model,
            "action": entry["action"],
            "repairs": len(entry["repairs"]),
            "error": entry.get("error"),
        }
    # Recalculate from actual current meals. The existing parser-status and
    # source failure history are never altered by an AI observation.
    status["quality_warnings"] = legacy.quality_warnings(data, today)
    status["quality_warning_count"] = len(status["quality_warnings"])
    if status.get("health") == "failed":
        pass  # Never downgrade a severe importer incident to merely degraded.
    elif status.get("problems") or status["quality_warning_count"]:
        status["health"] = "degraded"
    else:
        status["health"] = "healthy"
    legacy.validate_meal_components(data)
    if any(row["repairs"] for row in report["results"]):
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        FRONTEND.write_text("window.CAMPUS_LUNCH_DATA = " +
                            json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"api_calls": report["api_calls"], "results": [
        {"restaurant": x["restaurant"], "action": x["action"], "repairs": len(x["repairs"])}
        for x in report["results"]]}, ensure_ascii=False))
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="YYYY-MM-DD Europe/Vienna")
    p.add_argument("--restaurant", choices=["all", *IDS])
    p.add_argument("--model", choices=sorted(ai.ALLOWED_MODELS), default="gpt-6-luna")
    p.add_argument("--max-calls", type=int, default=7)
    args = p.parse_args()
    if not 0 <= args.max_calls <= 11:
        p.error("--max-calls muss zwischen 0 und 11 liegen")
    today = date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    run(today, model=args.model, max_calls=args.max_calls, selected=args.restaurant)


if __name__ == "__main__":
    main()
