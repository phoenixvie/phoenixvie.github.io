#!/usr/bin/env python3
"""Import Karma Food HTML+PDF and Finn image-based weekly menus.

Original source evidence is mandatory. A week mismatch or incomplete extraction
never replaces good menu data. Runs after the conventional WU Lunch importer.
"""
from __future__ import annotations
import argparse
import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo

import fitz
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import update_menus as legacy

DATA = ROOT / "data" / "menus.json"
FRONT = ROOT / "data.js"
STATUS = ROOT / "status.json"
TZ = ZoneInfo("Europe/Vienna")
KARMA_URL = "https://karmafood.at/pages/wochenmenu-karma-food-wien"
FINN_URL = "https://finn.wien/blogs/news/mittagsmenu"
DAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag")
FINN_IMG = re.compile(r"FINN_kw(\d{1,2})(e)?(?:_\d+x\d+)?\.jpe?g$", re.I)


def normal(value):
    return re.sub(r"\s+", " ", str(value).casefold()).strip()


def data_days(monday):
    return {(monday + timedelta(days=i)).isoformat(): [] for i in range(5)}


def period_karma(html, monday):
    soup = BeautifulSoup(html, "html.parser")
    # The page uses "Karma Food 02.11.-07.11." (no year); the explicit
    # month/day interval must agree with the requested calendar week.
    headings = " ".join(soup.stripped_strings)
    m = re.search(r"Karma\s+Food\s+(\d{1,2})\.(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.", headings, re.I)
    if not m:
        raise ValueError("Karma Food: datierter Wochenkopf fehlt")
    d, mo, end_d, end_mo = (int(x) for x in m.groups())
    if (d, mo) != (monday.day, monday.month):
        raise ValueError("Karma Food: nur ein Plan für eine andere Woche veröffentlicht")
    end = monday + timedelta(days=5)
    if (end_d, end_mo) not in ((end.day, end.month),
                              ((monday + timedelta(days=4)).day, (monday + timedelta(days=4)).month)):
        raise ValueError("Karma Food: ungewöhnliches Enddatum")
    return soup


def karma_pdf_prices(pdf_bytes):
    if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes) > 6_000_000:
        raise ValueError("Karma Food: kein gültiges Original-PDF")
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if not 1 <= len(doc) <= 3:
            raise ValueError("Karma Food: ungewöhnliche PDF-Länge")
        text = "\n".join(page.get_text("text") for page in doc)
    a = re.search(r"Main\s*Dish\s*€\s*(\d{1,2}[,.]\d{2})", text, re.I)
    b = re.search(r"Special\s*€\s*(\d{1,2}[,.]\d{2})", text, re.I)
    if not a or not b:
        raise ValueError("Karma Food: Standard- oder Special-Preis im PDF nicht belegbar")
    regular = float(a.group(1).replace(",", "."))
    special = float(b.group(1).replace(",", "."))
    if not 5 <= regular < special <= 25:
        raise ValueError("Karma Food: PDF-Tarife unplausibel")
    return regular, special, text


def parse_karma_html(raw, monday):
    soup = period_karma(raw, monday)
    day_index = {name.casefold(): idx for idx, name in enumerate(DAYS)}
    result = data_days(monday)
    current = None
    pdf_link = None
    for anchor in soup.find_all("a", href=True):
        if "menü als pdf" in normal(anchor.get_text(" ", strip=True)) or "menu als pdf" in normal(anchor.get_text(" ", strip=True)):
            target = urljoin(KARMA_URL, anchor["href"])
            if urlparse(target).hostname == "cdn.shopify.com" and urlparse(target).path.lower().endswith(".pdf"):
                pdf_link = target
                break
    if not pdf_link:
        raise ValueError("Karma Food: offizieller PDF-Link nicht gefunden")
    tags = soup.find_all(["h2", "h3"])
    specials = set()
    for heading in tags:
        name = heading.get_text(" ", strip=True)
        if heading.name == "h2":
            current = day_index.get(normal(name))
            continue
        if current is None or heading.name != "h3":
            continue
        name = legacy.tidy(name)
        if not 5 <= len(name) <= 160:
            raise ValueError("Karma Food: ungültiger Gerichtname")
        fragment = []
        for el in heading.next_elements:
            if getattr(el, "name", None) in ("h2", "h3"):
                break
            if isinstance(el, str):
                fragment.append(el)
        info = " ".join(fragment)
        is_special = bool(re.search(r"\bSpecial\s*€\s*\d", info, re.I))
        is_vegan = bool(re.search(r"\bVegan\b", info, re.I))
        is_vegetarian = bool(re.search(r"\bVegetarisch\b", info, re.I))
        if not (is_vegan or is_vegetarian):
            raise ValueError("Karma Food: Ernährungskennzeichnung fehlt")
        day = (monday + timedelta(days=current)).isoformat()
        if any(normal(x["name"]) == normal(name) for x in result[day]):
            raise ValueError("Karma Food: doppeltes Tagesgericht")
        result[day].append({
            "name": name, "price": None, "category": "Special" if is_special else "Hauptgericht",
            "diet": "vegan" if is_vegan else "veggie", "description": "",
            "allergens": [], "included_soup": None, "included_choices": [],
            "source_url": KARMA_URL, "is_special": is_special,
        })
        if is_special:
            specials.add((day, normal(name)))
    if len(specials) > 5 or any(not 2 <= len(items) <= 4 for items in result.values()):
        raise ValueError("Karma Food: Wochenmenü unvollständig")
    return result, pdf_link


def validate_karma_pdf_matches(days, pdf_text):
    # PDF sometimes lays out days column-wise; check dish tokens rather than
    # relying on linear text ordering.
    tokens = set(re.findall(r"\w+", normal(pdf_text), re.UNICODE))
    matches = 0
    entries = [item for day in days.values() for item in day]
    for item in entries:
        words = [w for w in re.findall(r"\w+", normal(item["name"]), re.UNICODE)
                 if len(w) >= 5 and w not in {"curry", "veggie", "linsen", "mit", "salat"}]
        if words and len(set(words) & tokens) >= min(2, len(words)):
            matches += 1
    if matches < max(9, int(len(entries) * 0.7)):
        raise ValueError(f"Karma Food: PDF und HTML weichen voneinander ab ({matches}/{len(entries)} Treffer)")


def fetch_karma(monday):
    raw = legacy.safe_get(KARMA_URL)
    days, pdf_url = parse_karma_html(raw, monday)
    pdf = legacy.safe_get(pdf_url, 6_000_000)
    regular, special, pdf_text = karma_pdf_prices(pdf)
    validate_karma_pdf_matches(days, pdf_text)
    for items in days.values():
        for item in items:
            item["price"] = special if item.pop("is_special") else regular
            item["price_source"] = pdf_url
            item["source_sha256"] = hashlib.sha256(raw + pdf).hexdigest()
            item["description"] = "Preis laut offizieller Wochenmenü-PDF; Lunch-Combo mit Lassi separat erhältlich."
    return days, hashlib.sha256(raw + pdf).hexdigest(), pdf_url


def select_finn_image(html, monday):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for img in soup.find_all("img"):
        urls = [img.get("src", "")]
        for attr in ("data-src", "srcset"):
            if img.get(attr):
                urls.extend(v.strip().split(" ")[0] for v in img[attr].split(","))
        for candidate in urls:
            target = urljoin(FINN_URL, candidate)
            parsed = urlparse(target)
            if parsed.scheme != "https" or parsed.hostname != "cdn.shopify.com":
                continue
            found = FINN_IMG.search(Path(parsed.path).name)
            if not found or found.group(2):
                continue  # Prefer original German menu, not the English duplicate.
            week = int(found.group(1))
            if week != monday.isocalendar().week:
                continue
            versions = parse_qs(parsed.query).get("v", [])
            if len(versions) != 1 or not versions[0].isdigit():
                continue
            uploaded = datetime.fromtimestamp(int(versions[0]), timezone.utc).date()
            # Prevent reusing a same-numbered week from a previous year.
            if not monday - timedelta(days=15) <= uploaded <= monday + timedelta(days=7):
                continue
            candidates.append(target)
    # One unambiguous official German image is required.
    unique = list(dict.fromkeys(candidates))
    if not unique:
        raise ValueError("Finn: aktuelle deutschsprachige Wochenkarte noch nicht veröffentlicht")
    # Shopify may expose srcset variants; choose the original link with v=.
    originals = [u for u in unique if not re.search(r"_\d+x\d+\.jpe?g", urlparse(u).path, re.I)]
    if len(originals) != 1:
        raise ValueError("Finn: Bildquelle mehrdeutig; nicht automatisch veröffentlichen")
    return originals[0]


def _norm_item(item):
    return (item.get("date"), normal(item.get("name")),
            normal(item.get("category")), normal(item.get("portion")),
            item.get("price_eur"))


def validate_finn_pair(first, second, monday, img_url):
    """Two independent model reads must agree completely on all five days."""
    results = [first, second]
    for result in results:
        if result.get("status") != "found" or result.get("warnings") or not result.get("items"):
            raise ValueError("Finn: Bildanalyse unvollständig oder nicht eindeutig")
        if len(result["items"]) > 20:
            raise ValueError("Finn: zu viele Einträge")
    x = sorted((_norm_item(i) for i in first["items"]), key=str)
    y = sorted((_norm_item(i) for i in second["items"]), key=str)
    if x != y:
        print("Finn comparison Luna:", json.dumps(x, ensure_ascii=False), flush=True)
        print("Finn comparison Terra:", json.dumps(y, ensure_ascii=False), flush=True)
        raise ValueError("Finn: Zwei KI-Bildanalysen widersprechen sich")
    days = data_days(monday)
    for item in first["items"]:
        d = item.get("date")
        if d not in days:
            raise ValueError("Finn: Gerichte außerhalb der aktuellen Woche")
        name = item.get("name", "")
        price = item.get("price_eur")
        if not isinstance(name, str) or not 5 <= len(name) <= 160:
            raise ValueError("Finn: ungewöhnlicher Gerichtname")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not 2 <= price <= 30:
            raise ValueError("Finn: Hauptgerichtpreis fehlt/ungültig")
        if item.get("confidence") != "high" or item.get("source_url") != img_url:
            raise ValueError("Finn: Originalquelle oder Konfidenz unklar")
        if item.get("included_items"):
            raise ValueError("Finn: Inklusivleistung nicht unabhängig belegt")
        cat = normal(item.get("category"))
        if cat not in ("veggie", "vegan", "vegetarisch", "fleisch", "meat", "fisch", "fish"):
            raise ValueError("Finn: unbekannte Hauptgerichtkategorie")
        if any(normal(old["name"]) == normal(name) for old in days[d]):
            raise ValueError("Finn: doppeltes Gericht")
        diet = "vegan" if cat == "vegan" else "veggie" if cat in ("veggie", "vegetarisch") else "meat" if cat in ("fleisch", "meat", "fisch", "fish") else "unknown"
        days[d].append({
            "name": name.strip(), "price": price, "category": item["category"],
            "diet": diet, "description": "Optionales Suppen-/Salat-Menü laut Originalbild (Aufpreis separat).",
            "allergens": [], "included_soup": None, "included_choices": [],
            "source_url": img_url, "evidence_excerpt": item.get("evidence_excerpt", ""),
            "ai_confidence": "two-model-agreement",
        })
    if not all(2 <= len(v) <= 4 for v in days.values()):
        raise ValueError("Finn: nicht alle fünf Tage mit zwei Hauptgerichten vorhanden")
    return days


def fetch_finn(monday, *, key, previous):
    raw = legacy.safe_get(FINN_URL)
    image_url = select_finn_image(raw, monday)
    # Avoid repeated API calls when the verified current image has not changed.
    if (previous.get("source_image") == image_url and
        previous.get("state") in ("ok", "cached") and previous.get("last_success", "")[:10] >= monday.isoformat()):
        return None, previous.get("content_sha256"), image_url
    if not key:
        raise ValueError("Finn: OPENAI_API_KEY fehlt für Originalbild-Analyse")
    image = legacy.safe_get(image_url, 5_000_000)
    if not image.startswith(b"\xff\xd8\xff") or len(image) < 8_000:
        raise ValueError("Finn: ungültige oder zu kleine Speisekarten-JPEG")
    sha = hashlib.sha256(image).hexdigest()
    if previous.get("content_sha256") == sha and previous.get("state") in ("ok", "cached"):
        return None, sha, image_url
    now = datetime.now(TZ).isoformat(timespec="seconds")
    if (previous.get("last_attempt_sha256") == sha and
        previous.get("last_attempt_at", "")[:10] == now[:10]):
        raise ValueError("Finn: diese Bildversion heute bereits mit KI geprüft; neuer Versuch erst bei Änderung oder morgen")
    # Mark an attempt BEFORE the paid model call. The caller retains this
    # record even if the models disagree or the API returns an error.
    previous.update({"last_attempt_sha256": sha, "last_attempt_at": now,
                     "source_image": image_url})
    spec = importlib.util.spec_from_file_location("finn_visual_ai", ROOT / "ai-pilot" / "ai_direct.py")
    ai = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ai)
    prompt = (
        f"Extrahiere ausschließlich die HAUPTGERICHTE des offiziellen Finn-Wochenbilds "
        f"für {monday.isoformat()} bis {(monday+timedelta(days=4)).isoformat()}. "
        "Lies sichtbare Wochentage und Tagesdaten im Bild. Übernimm die Gerichtsnamen wortgetreu, " 
        "nicht paraphrasieren oder übersetzen. Zwei Hauptgerichte je Tag, "
        "keine Tagessuppe, keine Getränke, keine Werbung, kein Menü-Upgrade als eigenes Gericht. "
        "Setze price_eur nur auf den regulären ausdrücklich im Bild gedruckten Preis "
        "HAUPTGERICHT, NICHT den Kombipreis mit Suppe. "
        "category aus der Bildspalte: Veggie, Vegan, Fleisch oder Fisch. "
        "included_items ist leer (Suppe ist nicht kostenlos). "
        f"source_url muss exakt {image_url} sein. "
        "Fehlt ein Wochentag, ein Preis oder ist die Woche unklar: status=unclear; keine erfundenen Inhalte. "
        "Verwende das Bild selbst, nicht Metadaten als Beweis für Gerichtnamen."
    )
    payload = [{"role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": "data:image/jpeg;base64,"+base64.b64encode(image).decode()},
    ]}]
    first, _ = ai.call_model(key, "gpt-6-luna", payload)
    second, _ = ai.call_model(key, "gpt-6.1-terra", payload)
    for label, res in (("Luna", first), ("Terra", second)):
        print("Finn analysis", label, "status", res.get("status"),
              "items", len(res.get("items") or []),
              "warnings", (res.get("warnings") or [])[:4],
              "notes", (res.get("notes") or "")[:170], flush=True)
    for res in (first, second):
        issues = ai.validate(res, [{"url": image_url, "fetched": True}], monday, "finn")
        if issues:
            raise ValueError("Finn: KI-Validierung: "+"; ".join(issues[:3]))
    days = validate_finn_pair(first, second, monday, image_url)
    return days, sha, image_url


def run(today, *, karma_only=False):
    monday = today - timedelta(days=today.weekday())
    data = json.loads(DATA.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    if data.get("weekStart") != monday.isoformat():
        raise ValueError("Neue Restaurants: Datenbank enthält andere Woche")
    now = datetime.now(TZ).isoformat(timespec="seconds")
    key = __import__("os").environ.get("OPENAI_API_KEY", "").strip()
    source_states = status.setdefault("sources", {})
    previous_problems = [p for p in status.get("problems", [])
                         if not p.startswith(("karmafood:", "finn:"))]
    errors = []
    for ident in (("karmafood",) if karma_only else ("karmafood", "finn")):
        previous = source_states.get(ident, {})
        restaurant = legacy.restaurant(data, ident)
        try:
            if ident == "karmafood":
                days, digest, source_url = fetch_karma(monday)
            else:
                days, digest, source_url = fetch_finn(monday, key=key, previous=previous)
            if days is None:
                source_states[ident] = {**previous, "state": "cached", "checked_at": now}
                continue
            legacy.candidate_quality_gate(ident, restaurant.get("days", {}), days)
            restaurant["days"] = days
            restaurant["status"] = "verified" if ident == "karmafood" else "ai_crosschecked"
            restaurant["validFrom"] = monday.isoformat()
            restaurant["validUntil"] = (monday+timedelta(days=4)).isoformat()
            restaurant["note"] = ("HTML-Tageskarte + unabhängiger Original-PDF-Tarifabgleich"
                                  if ident == "karmafood" else
                                  "Wochenbild, Wochenkennzeichnung und zwei KI-Modellprüfungen")
            src = legacy.source(data, ident)
            src["status"] = restaurant["status"]
            src["validFrom"] = restaurant["validFrom"]
            src["validUntil"] = restaurant["validUntil"]
            source_states[ident] = {
                "state": "ok", "last_success": now, "checked_at": now,
                "consecutive_failures": 0, "content_sha256": digest,
                "source_image": source_url if ident == "finn" else None,
                "source_pdf": source_url if ident == "karmafood" else None,
            }
        except Exception as exc:
            msg = str(exc)[:220]
            waiting = ("andere Woche" in msg or "noch nicht veröffentlicht" in msg)
            if ident == "finn" and "Bildquelle mehrdeutig" in msg:
                waiting = False
            source_states[ident] = {
                **previous, "state": "not_published" if waiting else "error",
                "checked_at": now,
                "last_success": previous.get("last_success"),
                "consecutive_failures": 0 if waiting else previous.get("consecutive_failures", 0)+1,
                "note": msg,
            }
            if not waiting:
                errors.append(f"{ident}: {type(exc).__name__}: {msg}")
            if not sum(len(x) for x in restaurant.get("days", {}).values()):
                restaurant["status"] = "not_published" if waiting else "empty"
            print(f"::warning::{ident}: {msg}", flush=True)
    legacy.validate_meal_components(data)
    status["problems"] = previous_problems + errors
    status["quality_warnings"] = legacy.quality_warnings(data, today)
    status["quality_warning_count"] = len(status["quality_warnings"])
    status["health"] = ("degraded" if status["problems"] or status["quality_warning_count"]
                        else "healthy")
    status["next_run"] = ("Mo 06:15–18:15 stündlich, Di–Fr 08:15–12:15 "
                          "(Europe/Vienna, GitHub Actions: zeitliche Abweichung möglich)")
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    FRONT.write_text("window.CAMPUS_LUNCH_DATA = "+
                     json.dumps(data, ensure_ascii=False, separators=(",", ":"))+";\n", encoding="utf-8")
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return len(errors)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD")
    ap.add_argument("--karma-only", action="store_true", help="No image-model calls on code pushes")
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    return run(today, karma_only=args.karma_only)


if __name__ == "__main__":
    sys.exit(main())
