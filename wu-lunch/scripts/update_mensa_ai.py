#!/usr/bin/env python3
"""Guarded Mensa PDF -> multimodal AI -> verified weekly menu import.

Runs *after* the existing deterministic importer. A failed AI run leaves existing
Mensa menu entries untouched, records the failure, and never guesses prices.
Requires OPENAI_API_KEY. No API call for an already successfully imported week.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import fitz

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "ai-pilot" / "results"
DATA = ROOT / "data" / "menus.json"
JS = ROOT / "data.js"
STATUS = ROOT / "status.json"
TZ = ZoneInfo("Europe/Vienna")
REVIEW_VERSION = "ai-pdf-3-diagnostics"
SOURCE_FILE = ROOT / "ai-pilot" / "ai_direct.py"

spec = importlib.util.spec_from_file_location("mensa_ai_direct", SOURCE_FILE)
ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)

spec2 = importlib.util.spec_from_file_location("mensa_legacy", ROOT / "scripts" / "update_menus.py")
legacy = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(legacy)

VALID_CATEGORIES = {
    "tagessuppe": "Tagessuppe",
    "powered by plants veggie": "Powered by plants / Veggie",
    "veggie": "Powered by plants / Veggie",
    "meaty": "Meaty",
    "global grill": "Global & Grill",
    "soup deal": "Soup Deal",
    "pizza": "Pizza",
    "pizza co": "Pizza & Co",
    "bowls": "Bowls",
    "bowls co": "Bowls & Co",
    "pasta": "Pasta",
    "pasta co": "Pasta & Co",
    "weekly special": "Weekly Special",
    "ausgabe 1 2": "Ausgabe 1+2",
    "ausgabe 3 4": "Ausgabe 3+4",
    "ausgabe 5": "Ausgabe 5",
    "ausgabe 6": "Ausgabe 6",
    "ausgabe 7": "Ausgabe 7",
    "ausgabe 8": "Ausgabe 8",
}
STOPWORDS = {"mit", "und", "oder", "euro", "menü", "menu", "der", "die", "das", "von", "den", "dem", "für", "auf", "aus", "ein", "eine"}


def normalize(value):
    return re.sub(r"[^a-z0-9äöüß]+", " ", str(value).casefold()).strip()


def days_digest(days):
    return hashlib.sha256(json.dumps(days, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def independent_period(pdf_bytes, monday):
    """Independent textual validity check; AI alone cannot confirm PDF dates."""
    if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes) > 7_000_000:
        raise ValueError("Mensa: kein zulässiges Original-PDF")
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if not 1 <= len(document) <= 4:
            raise ValueError("Mensa: unerwartete Seitenzahl")
        extracted = "\n".join(p.get_text("text") for p in document)
    found = legacy.period(extracted)
    if found is None:
        # PDF fonts sometimes garble the first date, but preserve explicit
        # ISO week and readable end date. Both must match this target week.
        match = re.search(r"\bKW\s*(\d{1,2})\b", extracted, re.I)
        dates = re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", extracted)
        if match and int(match.group(1)) == monday.isocalendar().week:
            for day, month, year in dates:
                try:
                    end = date(int(year), int(month), int(day))
                    if end in (monday + timedelta(days=4), monday + timedelta(days=3)):
                        found = (monday, end)
                        break
                except ValueError:
                    continue
    if found is None or found[0] != monday or found[1] not in (
        monday + timedelta(days=4), monday + timedelta(days=3)
    ):
        raise ValueError("Mensa: PDF-Woche nicht unabhängig verifiziert")
    return extracted


def validate_menu(result, original_text, monday, pdf_url):
    """Return all five days or raise; never trust model confidence as proof."""
    if result.get("status") != "found" or result.get("warnings"):
        raise ValueError("Mensa: KI-Status " + str(result.get("status")) + "; Warnungen: " + json.dumps(result.get("warnings"), ensure_ascii=False)[:400])
    items = result.get("items") or []
    if not 10 <= len(items) <= 80:
        raise ValueError("Mensa: ungewöhnlich wenige oder viele Gerichte")
    days = {(monday + timedelta(days=i)).isoformat(): [] for i in range(5)}
    seen = set()
    pdf_words = set(normalize(original_text).split())
    for item in items:
        day = item.get("date")
        if day not in days:
            raise ValueError("Mensa: fehlender oder falscher Wochentag")
        name = item.get("name")
        pizza_station = VALID_CATEGORIES.get(normalize(item.get("category"))) == "Ausgabe 5"
        if not isinstance(name, str) or not ((pizza_station and name.strip() == "Pizza") or 8 <= len(name.strip()) <= 160):
            raise ValueError("Mensa: beschädigter Gerichtname")
        if not re.match(r'["„“«]?[A-ZÄÖÜ]', name.strip()):
            raise ValueError("Mensa: verdächtiger Gerichtbeginn")
        category = VALID_CATEGORIES.get(normalize(item.get("category")))
        if category is None:
            raise ValueError("Mensa: unbekannte Speisenkategorie")
        if category.startswith("Ausgabe") and "ausgabe" not in original_text.casefold():
            raise ValueError("Mensa: Ausgabe-Nummer nicht im Original-PDF")
        price = item.get("price_eur")
        if price is None and category not in ("Tagessuppe", "Soup Deal", "Global & Grill", "Pizza", "Pizza & Co", "Pasta", "Pasta & Co", "Ausgabe 5"):
            raise ValueError("Mensa: fehlender Gerichtpreis")
        if price is not None and (not isinstance(price, (int, float)) or isinstance(price, bool) or
            not math.isfinite(price) or not 0 < price <= 150):
            raise ValueError("Mensa: fehlender oder ungültiger Preis")
        if item.get("source_url") != pdf_url:
            raise ValueError("Mensa: unbekannter Originalbeleg")
        evidence = item.get("evidence_excerpt")
        if not isinstance(evidence, str) or len(evidence.strip()) < 8:
            raise ValueError("Mensa: Quellenzitat fehlt")
        if item.get("confidence") != "high":
            raise ValueError("Mensa: unsichere Gerichtzuordnung")
        # This is a conservative plausibility check, not independent proof of
        # each row assignment. A full source-layout audit may still be needed.
        evidence_terms = {x for x in normalize(evidence).split() if len(x) >= 5 and x not in STOPWORDS}
        if len(evidence_terms & pdf_words) < 2:
            raise ValueError("Mensa: Quellenbeleg nicht im extrahierten PDF-Text auffindbar")
        allergens = item.get("allergens") or []
        if not isinstance(allergens, list) or any(not isinstance(x, str) or not re.fullmatch(r"[A-R]", x) for x in allergens):
            raise ValueError("Mensa: ungültige Allergene")
        if any(not re.search(r"(?<![A-Z])" + re.escape(code) + r"(?![A-Z])", evidence.upper()) for code in allergens):
            raise ValueError("Mensa: Allergen nicht im Gerichtbeleg")
        energy = item.get("energy_kcal")
        if energy is not None and (not isinstance(energy, (int, float)) or not 0 < energy < 5000):
            raise ValueError("Mensa: ungültiger Nährwert")
        if energy is not None and str(int(energy)) not in evidence:
            raise ValueError("Mensa: Nährwert nicht im Gerichtbeleg")
        included = item.get("included_items") or []
        if not isinstance(included, list) or any(not isinstance(x, str) for x in included):
            raise ValueError("Mensa: ungültige inkludierte Leistungen")
        if category == "Global & Grill" and any("suppe" in x.casefold() for x in included):
            raise ValueError("Mensa: Global & Grill darf keine inkludierte Suppe erhalten")
        if category == "Tagessuppe" and "suppe" not in name.casefold():
            raise ValueError("Mensa: Tagessuppe nicht plausibel")
        portion = item.get("portion") or ""
        key = (day, normalize(name), normalize(portion))
        if key in seen:
            raise ValueError("Mensa: doppeltes Gericht")
        seen.add(key)
        diet = ("veggie" if category == "Powered by plants / Veggie"
                else "meat" if category == "Meaty" else "unknown")
        extras = item.get("extra_costs") or []
        if not isinstance(extras, list) or any(not isinstance(x, str) for x in extras):
            raise ValueError("Mensa: ungültige Zusatzkosten")
        description = " | ".join(x for x in [
            ("Portion: " + portion) if portion else "",
            ("Inklusive: " + ", ".join(included)) if included else "",
            ("Zusatzkosten: " + ", ".join(extras)) if extras else "",
        ] if x)
        days[day].append({
            "name": name.strip(), "price": price, "category": category,
            "diet": diet, "description": description, "allergens": allergens,
            "energy_kcal": energy,
            "included_soup": None, "included_choices": included,
            "source_url": pdf_url, "evidence_excerpt": evidence.strip(),
            "ai_confidence": item.get("confidence") or "unknown",
        })
    if any(not rows for rows in days.values()):
        raise ValueError("Mensa: weniger als fünf Wochentage gefunden")
    meaty = sum(any(x["category"] == "Meaty" for x in rows) for rows in days.values())
    if meaty < 3:
        raise ValueError("Mensa: Meaty-Kategorie an zu wenigen Tagen")
    return days


def acquire_pdf(monday):
    """Discover the German menu from the homepage, then try its stable endpoint.

    Some homepage responses contain only a JS shell. Always keep the official
    German endpoint as a fallback. Fetch once; validation and AI use those bytes.
    """
    candidates = []
    try:
        home, raw = ai.safe_source_get("https://www.wumensa.at/")
        soup = ai.BeautifulSoup(raw, "html.parser")
        for a in soup.find_all("a", href=True):
            href = ai.urljoin(home, a["href"])
            if "menuplan-deutsch" in href or (".pdf" in href.lower() and "engl" not in href.lower()):
                candidates.append(href)
    except Exception as exc:
        print("Mensa Homepage-Discovery:", str(exc)[:150])
    candidates.extend(["https://www.wumensa.at/menuplan-deutsch/",
                       "https://www.wumensa.at/menuplan-deutsch/?week=" + monday.isoformat()])
    errors = []
    for candidate in list(dict.fromkeys(candidates))[:8]:
        try:
            url, raw = ai.safe_source_get(candidate)
            url, raw = ai.find_mensa_pdf(url, raw)
            text = independent_period(raw, monday)
            source = {"url": url, "sha256": hashlib.sha256(raw).hexdigest(),
                      "bytes": len(raw), "type": "pdf", "fetched": True, "truncated": False}
            return raw, text, source
        except Exception as exc:
            errors.append(str(exc)[:160])
    raise ValueError("Mensa: kein verifiziertes aktuelles Original-PDF: " + " | ".join(errors[:3]))


def extract_for_week(monday, key, model, prepared=None):
    raw, native_text, pdf_source = prepared or acquire_pdf(monday)
    pdf_url = pdf_source["url"]
    prompt = (f"Restaurant Mensa, Woche {monday} bis {monday+timedelta(days=4)}. "
              f"Originalquelle: {pdf_url}, SHA256 {pdf_source['sha256']}. "
              "Lies die vollständige PDF-Tabelle visuell, ALLE Tages- und Angebotszeilen, bis zu 80 Items. "
              "Jeder Tag und jede angebotene Variante ein Item. Kategorien wortgetreu: "
              "Tagessuppe, Soup Deal, Powered by plants / Veggie, Meaty, Pizza & Co, "
              "Weekly Special, Bowls & Co, Pasta & Co, Global & Grill. "
              "XXX bedeutet kein Angebot, niemals als Gericht erfassen. "
              "Übergreifende Angebote nur den sichtbaren Tagen zuordnen. "
              "Unbekannter Preis/laut Aushang bleibt null; keinen Nachbartagespreis übernehmen. "
              "Preise der Pizza/Pasta aus der linken Tarifspalte korrekt zuordnen. "
              "Kombinationen und Aufpreise in extra_costs angeben, keine Gratis-Suppe erfinden. "
              "evidence_excerpt zitiert Gericht UND Preis mit Tagen/Kategorie, sofern sichtbar. "
              "source_url exakt wie oben. Unsichere Zuordnung als Warnung; keine erfundenen Inhalte.")
    inputs = [{"role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_file", "filename": "wu-mensa-menu.pdf",
         "file_data": "data:application/pdf;base64," + base64.b64encode(raw).decode()},
    ]}]
    result, usage = ai.call_model(key, model, inputs, max_output_tokens=22000)
    # Retain the actual candidate and exact downloaded bytes for inspection.
    # Public restaurant content only; no credentials or request headers.
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "mensa-current.pdf").write_bytes(raw)
    (RESULTS / "mensa-current.json").write_text(json.dumps({
        "week_start": monday.isoformat(), "source": pdf_source,
        "model": model, "result": result, "usage": usage,
    }, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("Mensa-KI Analyse:", json.dumps({"status": result.get("status"),
          "warnings": result.get("warnings"), "items": len(result.get("items") or [])}, ensure_ascii=False), flush=True)
    issues = ai.validate(result, [pdf_source], monday, "mensa")
    if issues:
        raise ValueError("Mensa: KI-Validierung: " + "; ".join(issues[:4]))
    days = validate_menu(result, native_text, monday, pdf_url)
    # Independently compare the dated core table cells and prices. Parser
    # failure blocks this candidate; it never becomes permission to guess.
    core, _ = legacy.parse_mensa(raw, monday)
    from difflib import SequenceMatcher
    for day, rows in core.items():
        for expected in rows:
            matches = [i for i in days[day] if normalize(i["category"]) == normalize(expected["category"])
                       and SequenceMatcher(None, normalize(i["name"]), normalize(expected["name"])).ratio() >= .94]
            if len(matches) != 1 or matches[0]["price"] != expected["price"]:
                raise ValueError("Mensa: PDF-Zellenabgleich fehlgeschlagen: " + day + " " + expected["category"])
    return days, pdf_source, usage


def apply_candidate(data, status, days, monday, pdf_source, usage, model):
    """Only replace Mensa after full validation; preserve eight other restaurants."""
    restaurant = next(r for r in data["restaurants"] if r["id"] == "mensa")
    source = next(s for s in data["sources"] if s["id"] == "mensa")
    existing = restaurant.get("days", {})
    # Never shrink coverage when verified same-week data already exist.
    for day, old in existing.items():
        if old and len(days.get(day, [])) < len(old):
            raise ValueError("Mensa: KI würde vorhandene Tagesgerichte löschen")
    restaurant["days"] = days
    restaurant["status"] = source["status"] = "ai_checked"
    end = (monday + timedelta(days=4)).isoformat()
    restaurant["validFrom"] = source["validFrom"] = monday.isoformat()
    restaurant["validUntil"] = source["validUntil"] = end
    restaurant["note"] = "KI-PDF-Auswertung; Datums-, Text- und Schema-Prüfung bestanden"
    now = datetime.now(TZ).isoformat(timespec="seconds")
    status.setdefault("sources", {})["mensa"] = {
        "state": "ok", "last_success": now, "consecutive_failures": 0,
        "parser_version": REVIEW_VERSION,
        "content_sha256": pdf_source["sha256"],
        "model": model,
        "usage": usage,
    }
    status["problems"] = [p for p in status.get("problems", []) if not p.startswith("mensa:")]
    status["quality_warnings"] = [w for w in status.get("quality_warnings", []) if not w.startswith("mensa ")]
    status["quality_warning_count"] = len(status["quality_warnings"])
    status["health"] = ("degraded" if status["problems"] or status["quality_warning_count"] else "healthy")
    return now


def run(today, model):
    monday = legacy.target_week_monday(today)
    data = json.loads(DATA.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    if data.get("weekStart") != monday.isoformat():
        raise ValueError("Mensa: Datenwoche entspricht nicht der aktuellen Woche")
    prior = status.get("mensa_luna_audit", {})
    mensa = next(r for r in data["restaurants"] if r["id"] == "mensa")
    # Always audit the first independently verified PDF of a new week.
    # A parser reporting 'ok' does not prove that all PDF columns and
    # included side dishes were interpreted correctly.
    now = datetime.now(TZ).isoformat(timespec="seconds")
    audit = {**prior, "checked_at": now}
    try:
        prepared = acquire_pdf(monday)
        pdf_source = prepared[2]
        same = (prior.get("source_sha256") == pdf_source["sha256"] and
                prior.get("week_start") == monday.isoformat() and prior.get("version") == REVIEW_VERSION)
        if same and prior.get("state") in ("ok", "cached") and prior.get("published_days_sha256") == days_digest(mensa.get("days", {})) and all(
            mensa.get("days", {}).get((monday+timedelta(days=i)).isoformat()) for i in range(5)):
            audit["state"] = "cached"
            # Restore independently audited data status after the core parser.
            status["sources"]["mensa"].update(state="cached", parser_version=REVIEW_VERSION,
                                               content_sha256=pdf_source["sha256"])
            status["problems"] = [p for p in status.get("problems", []) if not p.startswith("mensa:")]
            status["health"] = "degraded" if status["problems"] or status.get("quality_warning_count") else "healthy"
            print("Mensa-KI: unverändertes geprüftes Original-PDF; kein API-Aufruf")
            status["mensa_luna_audit"] = audit
            STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            return False
        if same and prior.get("last_attempt_at", "")[:10] == now[:10]:
            raise ValueError("Mensa: diese PDF-Version heute bereits geprüft; erneuter Versuch bei Änderung oder morgen")
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ValueError("Mensa: OPENAI_API_KEY fehlt")
        audit.update(source_sha256=pdf_source["sha256"], source_url=pdf_source["url"],
                     week_start=monday.isoformat(), version=REVIEW_VERSION, last_attempt_at=now)
        days, pdf_source, usage = extract_for_week(monday, key, model, prepared)
        apply_candidate(data, status, days, monday, pdf_source, usage, model)
        audit.update(state="ok", last_success=now, error=None, published_days_sha256=days_digest(days))
    except Exception as exc:
        detail = str(exc)[:230]
        print("::warning::Mensa-KI nicht übernommen: " + detail)
        audit.update(state="error", error=detail)
        status["mensa_luna_audit"] = audit
        status.setdefault("sources", {}).setdefault("mensa", {}).update(state="error", error=detail)
        status["problems"] = [p for p in status.get("problems", []) if not p.startswith("mensa:")]+["mensa: "+detail]
        status["health"] = "degraded"
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        return False
    status["mensa_luna_audit"] = audit
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    JS.write_text("window.CAMPUS_LUNCH_DATA = " + json.dumps(
        data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Mensa-KI: {sum(len(v) for v in days.values())} Gerichte für {monday.isoformat()} übernommen")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Europe/Vienna YYYY-MM-DD")
    parser.add_argument("--model", default="gpt-6-luna")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    run(today, args.model)


if __name__ == "__main__":
    main()
