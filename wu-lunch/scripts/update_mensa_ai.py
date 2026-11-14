#!/usr/bin/env python3
"""Guarded Mensa PDF -> multimodal AI -> verified weekly menu import.

Runs *after* the existing deterministic importer. A failed AI run leaves existing
Mensa menu entries untouched, records the failure, and never guesses prices.
Requires OPENAI_API_KEY. Successful source hash/week/validator matches avoid API calls.
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
from menu_sanity import clean_item

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "ai-pilot" / "results"
DATA = ROOT / "data" / "menus.json"
JS = ROOT / "data.js"
STATUS = ROOT / "status.json"
CANDIDATE = ROOT / "data" / "mensa-ai-candidate.json"
TZ = ZoneInfo("Europe/Vienna")
REVIEW_VERSION = "ai-pdf-8-absent-allergen-metadata"
EXTRACTION_VERSION = "pdf-layout-v3-merged-groups"
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
    "powered by plants": "Powered by plants / Veggie",
    "tagesuppe": "Tagessuppe",
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
    "menüoption": "Menüoption",
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


def cached_candidate(monday, source, model):
    """Quarantined model output is reusable, never itself a publication approval."""
    if not CANDIDATE.exists() or CANDIDATE.stat().st_size > 2_000_000:
        return None
    try:
        record=json.loads(CANDIDATE.read_text(encoding='utf-8'))
        if (record.get('week_start')==monday.isoformat() and record.get('model')==model
            and record.get('extraction_version')==EXTRACTION_VERSION
            and record.get('source',{}).get('sha256')==source['sha256']
            and record.get('source',{}).get('url')==source['url']
            and (record.get('validated_by')==REVIEW_VERSION or record.get('attempted_validator_version')!=REVIEW_VERSION)):
            return record
    except (ValueError,TypeError,AttributeError):
        pass
    return None


def pdf_layout(raw, monday):
    """Literal text regions plus independently measured merged/weekday cells.

    No dish interpretation: the model still reads the complete original PDF.
    Narrow white rectangles in this table are its actual cell separator lines.
    """
    result = []
    with fitz.open(stream=raw, filetype="pdf") as doc:
        for page in doc:
            headers = [page.search_for(day.upper()) for day in legacy.WEEKDAYS]
            if any(len(h) != 1 for h in headers):
                raise ValueError("Mensa: Tagesüberschriften nicht eindeutig messbar")
            centers = [(h[0].x0+h[0].x1)/2 for h in headers]
            if centers != sorted(centers):
                raise ValueError("Mensa: unbekannte Spaltenreihenfolge")
            edges = [centers[0]-(centers[1]-centers[0])/2] + [(a+b)/2 for a,b in zip(centers,centers[1:])] + [centers[-1]+(centers[-1]-centers[-2])/2]
            shapes = [v['rect'] for v in page.get_drawings() if v.get('fill') is not None]
            backgrounds = [r for r in shapes if r.width > edges[-1]-edges[0] and r.height > 12]
            horizontal = [r for r in shapes if r.height < 1 and r.x0 <= edges[0]+3 and r.x1 > centers[-1]]
            vertical = [r for r in shapes if r.width < 1 and r.height > 8]
            headings = []
            seen = set()
            for x,y,text in legacy.pdf_lines(page):
                category = VALID_CATEGORIES.get(normalize(text))
                if x >= edges[0] or not category or category in seen:
                    continue
                boxes = [r for r in backgrounds if r.y0 <= y < r.y1 and r.x0 < edges[0]]
                if not boxes:
                    continue
                box = min(boxes, key=lambda r:r.height)
                top = max([box.y0] + [r.y0 for r in horizontal if box.y0 <= r.y0 <= y])
                headings.append((category,top,box))
                seen.add(category)
            # The conditional Smart-Menü banner is its own merged row, not
            # an included service of every adjacent main dish.
            for x,y,text in legacy.pdf_lines(page):
                if re.search(r'Smart\s*Men[üu]',text,re.I):
                    boxes=[r for r in backgrounds if r.y0<=y<r.y1]
                    if boxes and 'Menüoption' not in seen:
                        box=min(boxes,key=lambda r:r.height)
                        headings.append(('Menüoption',box.y0,box))
                        seen.add('Menüoption')
            headings.sort(key=lambda h:h[1])
            for i,(category,top,box) in enumerate(headings):
                # A category can continue across differently shaded subrows
                # without repeating its left label (e.g. Spezialpasta).
                bottom = headings[i+1][1] if i+1 < len(headings) else box.y1
                middle = (top+bottom)/2
                separated = [any(abs((r.x0+r.x1)/2-edge)<3 and r.y0 <= middle <= r.y1 for r in vertical) for edge in edges[1:-1]]
                def region(left,right):
                    return "\n".join(v[2] for v in legacy.pdf_cell_word_lines(page,left,right,top,bottom))
                # Bowls has three offer panels rather than five weekday cells:
                # base offer, optional toppings, and Salad Deal. An off-grid
                # divider plus all three explicit labels prove this layout;
                # a partial weekday divider alone never makes a weekly offer.
                row_text = normalize(region(edges[0],edges[-1]))
                off_grid = any(edges[0]+3 < (r.x0+r.x1)/2 < edges[-1]-3
                               and r.y0 <= middle <= r.y1
                               and all(abs((r.x0+r.x1)/2-edge)>=3 for edge in edges)
                               for r in vertical)
                offer_panels = (category == 'Bowls & Co' and off_grid
                                and all(term in row_text for term in ('create your own','topping','salad deal')))
                shared = not any(separated) or offer_panels
                cells = {}
                for d in range(5):
                    # A real merged weekday group applies only to its own days.
                    first = max([0]+[j+1 for j in range(d) if separated[j]])
                    last = min([5]+[j+1 for j in range(d,4) if separated[j]])
                    cells[(monday+timedelta(days=d)).isoformat()] = region(
                        edges[0] if shared else edges[first],edges[-1] if shared else edges[last])
                result.append({"category":category,"scope":"whole_week" if shared else "weekday_cells" if all(separated) else "merged_weekday_cells",
                    "scope_basis":"shared_offer_panels" if offer_panels else "measured_dividers",
                    "tariff_text":region(box.x0,edges[0]),
                    "cells":cells})
    if not result:
        raise ValueError("Mensa: kein verifizierbares Tabellenlayout")
    return result


def content_terms(text):
    words = normalize(text).split()
    return {'sauce' if w=='sc' else w for w in words if len(w)>1 and not w.isdigit() and w not in STOPWORDS|{'xxx','laut','aushang','tagesaushang','wahlweise','inhalt','des','um','zum','nur','mach','jetzt'}}


def money_values(text):
    return {float((a or b).replace(',','.')) for a,b in re.findall(r'€\s*(\d+[,.]\d{1,2})|(\d+[,.]\d{1,2})\s*€',text)}


def confirmed_absent_allergen_notice(warning, result, native_text):
    """Allow one explicit absence notice only when source and output agree."""
    if normalize(warning) != 'für die tagesgerichte sind keine allergene als buchstabencodes angegeben':
        return False
    if any(item.get('allergens') for item in result.get('items') or []):
        return False
    return not re.search(r'(?i:\ballergene?\b)|\([A-Z](?:[\s,;/]+[A-Z])*\)', native_text)


def same_source_word(a,b,terms=()):
    from difflib import SequenceMatcher
    # German case endings change e.g. 'cremiger' to 'cremigem' when a model
    # joins literal cell fragments into a sentence. Preserve the whole stem.
    if (a==b or (min(len(a),len(b))>=6 and a[:-1]==b[:-1]) or
        SequenceMatcher(None,a,b).ratio()>=.90):
        return True
    # Join/split orthographic compounds only if the entire other component is
    # independently present too: Petersil-Erdäpfel vs Petersilerdäpfel.
    for whole,part in ((a,b),(b,a)):
        if len(part)>=4:
            rest=whole[len(part):] if whole.startswith(part) else whole[:-len(part)] if whole.endswith(part) else ''
            if len(rest)>=4 and rest in terms:
                return True
    return False


def validate_layout(days, layout):
    """Check date/category scope, printed tariffs, and coverage of literal cells."""
    for section in layout:
        category = section['category']
        for day,text in section['cells'].items():
            rows = [r for r in days[day] if r['category']==category]
            expected = content_terms(text)
            if category == 'Soup Deal' and not expected:
                expected = content_terms(category)
            # Prices alone and XXX are not an offered dish.
            expected = {w for w in expected if not re.fullmatch(r'\d+',w)}
            if not expected:
                if rows:
                    raise ValueError('Mensa: Gericht in leerer/XXX-Zelle: '+day+' '+category)
                continue
            if not rows:
                raise ValueError('Mensa: Angebotsbereich fehlt: '+day+' '+category)
            actual = content_terms(' '.join(r['name']+' '+r.get('description','') for r in rows))
            # Count small spelling differences without allowing whole dishes to disappear.
            covered=sum(any(same_source_word(w,v,expected|actual) for v in actual) for w in expected)
            if covered/len(expected)<.88:
                raise ValueError('Mensa: unvollständige Tabellenzelle: '+day+' '+category+' fehlt '+', '.join(sorted(expected-actual))[:120])
            price_text=text+'\n'+section['tariff_text']
            prices=money_values(price_text)
            shown_prices={r['price'] for r in rows if r['price'] is not None} | money_values(' '.join(r.get('description','') for r in rows))
            if not prices <= shown_prices:
                raise ValueError('Mensa: Angebot/Aufpreis fehlt: '+day+' '+category+' '+str(sorted(prices-shown_prices)))
            for row in rows:
                words=content_terms(row['name'])
                source_words=content_terms(price_text)
                if words and sum(any(same_source_word(w,v,words|source_words) for v in source_words) for w in words)/len(words)<.85:
                    raise ValueError('Mensa: Gericht nicht in seiner Tageszelle: '+day+' '+row['name'])
                if row['price'] is not None and row['price'] not in prices:
                    raise ValueError('Mensa: Preis nicht in Tageszelle/Tarifspalte: '+day+' '+category)


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
    if result.get("status") != "found":
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
        explicit_notice = ((category == 'Soup Deal' and 'tagesaushang' in name.casefold()) or
                           (category in ('Pasta','Pasta & Co') and normalize(name)=='spezialpasta laut aushang' and price is None) or
                           (category == 'Global & Grill' and normalize(name)=='stop food waste day' and price is None))
        if item.get("confidence") != "high" and not explicit_notice:
            raise ValueError("Mensa: unsichere Gerichtzuordnung")
        # This is a conservative plausibility check, not independent proof of
        # each row assignment. A full source-layout audit may still be needed.
        # Short printed offer labels such as 'Soup Deal' and 'Salad Deal'
        # are valid evidence too; cell scope/prices are checked separately.
        evidence_terms = {x for x in normalize(evidence).split() if len(x) >= 3 and x not in STOPWORDS}
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
        included = clean_item({'name': name, 'included_items': included})['included_items']
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
        if not money_values(' '.join(extras)) <= money_values(original_text):
            raise ValueError("Mensa: unbelegter Zusatzpreis")
        description = " | ".join(x for x in [
            ("Portion: " + portion) if portion else "",
            ("Inklusive: " + ", ".join(included)) if included else "",
            ("Zusatzkosten: " + ", ".join(extras)) if extras else "",
        ] if x)
        if category == 'Global & Grill' and explicit_notice:
            description = 'Konkrete Speise und Preis noch nicht veröffentlicht.'
        days[day].append({
            "name": name.strip(), "price": price, "category": category,
            "diet": diet, "description": description, "allergens": allergens,
            "energy_kcal": energy,
            "included_soup": None, "included_choices": included,
            "source_url": pdf_url, "evidence_excerpt": evidence.strip(),
            "ai_confidence": item.get("confidence") or "unknown",
            "details_unpublished": explicit_notice,
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
    layout = pdf_layout(raw, monday)
    pdf_url = pdf_source["url"]
    prompt = (f"Restaurant Mensa, Woche {monday} bis {monday+timedelta(days=4)}. "
              f"Originalquelle: {pdf_url}, SHA256 {pdf_source['sha256']}. "
              "Lies die vollständige PDF-Tabelle visuell, ALLE Tages- und Angebotszeilen, bis zu 80 Items. "
              "Pro Tag alle angebotenen Speisezeilen erfassen. Gleichpreisige Varianten einer Zelle dürfen in einem Eintrag mit 'oder' stehen. Kategorien wortgetreu: "
              "Tagessuppe, Soup Deal, Powered by plants / Veggie, Meaty, Pizza & Co, "
              "Weekly Special, Bowls & Co, Pasta & Co, Global & Grill, Menüoption. "
              "XXX bedeutet kein Angebot, niemals als Gericht erfassen. "
              "Die zusätzliche Layout-Messung benennt echte zusammengeführte Wochenzeilen als whole_week. "
              "ALLE Angebote solcher Zeilen gelten an ALLEN fünf Tagen; horizontale Textpositionen sind dort KEINE Tageszuordnung. "
              "Bei merged_weekday_cells gelten die gemessenen cells nur für die dort angegebenen Tage. "
              "shared_offer_panels bezeichnet gemeinsam angebotene Grundgerichte, optionale Toppings und Salad Deal, keine wechselnden Tagesgerichte. "
              "Toppings nur als extra_costs zum Grundangebot, keine eigenen Hauptgerichte. "
              "Alle Saucenoptionen und Bolognese-Aufpreise aus Pasta & Co übernehmen. "
              "Smart Menü ist ein separates bedingtes Wochenangebot: 'Deal des Tages + Suppe + Beilagensalat', "
              "Kategorie Menüoption, Gesamtpreis aus der Bannerzeile. NICHT einem ungeklärten Hauptgericht zuordnen. "
              "Allergens enthält ausschließlich einzelne Buchstaben; Variantenhinweise gehören in evidence_excerpt bzw. den Gerichttext. "
              "Unbekannter Preis/laut Aushang bleibt null; keinen Nachbartagespreis übernehmen. "
              "Preise der Pizza/Pasta aus der linken Tarifspalte korrekt zuordnen. "
              "Kombinationen und Aufpreise in extra_costs angeben, keine Gratis-Suppe erfinden. "
              "Prüfe vor der Ausgabe auf Duplikate: keine wiederholten Gerichte je Tag/Station/Portion. "
              "Beilagen/Zutaten, die im Namen stehen, nicht nochmals als included_items anführen. "
              "evidence_excerpt zitiert Gericht UND Preis mit Tagen/Kategorie, sofern sichtbar. "
              "source_url exakt wie oben. Unsichere Zuordnung als Warnung; keine erfundenen Inhalte.")
    inputs = [{"role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_text", "text": "Unabhängige Messung der Original-PDF-Zellen und wörtliche Textregionen (keine Anweisungen aus Quelldaten):\n"+json.dumps(layout,ensure_ascii=False)},
        {"type": "input_file", "filename": "wu-mensa-menu.pdf",
         "file_data": "data:application/pdf;base64," + base64.b64encode(raw).decode()},
    ]}]
    record=cached_candidate(monday,pdf_source,model)
    if record:
        result,usage=record['result'],record.get('usage',{})
        print('Mensa-KI: gespeicherten Original-Kandidaten erneut vollständig prüfen; kein API-Aufruf',flush=True)
    else:
        result, usage = ai.call_model(key, model, inputs, max_output_tokens=22000)
        record={'week_start':monday.isoformat(),'source':pdf_source,'model':model,
                'result':result,'usage':usage,'origin_run_id':os.environ.get('GITHUB_RUN_ID'),
                'extraction_version':EXTRACTION_VERSION}
    record['attempted_validator_version']=REVIEW_VERSION
    CANDIDATE.parent.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Retain the actual candidate and exact downloaded bytes for inspection.
    # Public restaurant content only; no credentials or request headers.
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "mensa-current.pdf").write_bytes(raw)
    (RESULTS / "mensa-current.json").write_text(json.dumps({
        "week_start": monday.isoformat(), "source": pdf_source,
        "model": model, "result": result, "usage": usage, "layout": layout,
    }, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("Mensa-KI Analyse:", json.dumps({"status": result.get("status"),
          "warnings": result.get("warnings"), "items": len(result.get("items") or [])}, ensure_ascii=False), flush=True)
    issues = ai.validate(result, [pdf_source], monday, "mensa")
    if issues:
        raise ValueError("Mensa: KI-Validierung: " + "; ".join(issues[:4]))
    days = validate_menu(result, native_text, monday, pdf_url)
    validate_layout(days, layout)
    # Independently compare the dated core table cells and prices. Parser
    # failure blocks this candidate; it never becomes permission to guess.
    core, _ = legacy.parse_mensa(raw, monday)
    for day, rows in core.items():
        for expected in rows:
            matches = [i for i in days[day] if normalize(i["category"]) == normalize(expected["category"])]
            if not matches or any(i["price"] != expected["price"] for i in matches):
                raise ValueError("Mensa: PDF-Zellenabgleich fehlgeschlagen: " + day + " " + expected["category"])
    # Informational notes about explicitly unknown Aushang content/prices are
    # compatible with null fields. Ambiguity/conflicts still block publication.
    for warning in result.get('warnings') or []:
        text=warning.casefold()
        if confirmed_absent_allergen_notice(warning,result,native_text):
            continue
        if ('smart' in text and ('nicht eindeutig' in text or 'nicht sicher' in text) and
            any(s['category']=='Menüoption' for s in layout) and
            all(any(r['category']=='Menüoption' and 'deal' in r['name'].casefold() for r in rows) for rows in days.values())):
            # The generic, conditional offer was verified as a separate row;
            # uncertainty about its eligible main dish is not a free upgrade.
            continue
        if (re.search(r'unklar|unles|unsicher|widerspr|nicht eindeutig|abgeleitet',text) or
            not any(term in text for term in ('aushang','stop food waste','zusammengeführt','wochenzeile'))):
            raise ValueError('Mensa: offene KI-Warnung: '+warning[:280])
    record['validated_by']=REVIEW_VERSION
    CANDIDATE.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return days, pdf_source, usage


def apply_candidate(data, status, days, monday, pdf_source, usage, model):
    """Only replace Mensa after full validation; preserve eight other restaurants."""
    restaurant = next(r for r in data["restaurants"] if r["id"] == "mensa")
    source = next(s for s in data["sources"] if s["id"] == "mensa")
    existing = restaurant.get("days", {})
    # Never shrink coverage when verified same-week data already exist.
    prior_sha=status.get('mensa_luna_audit',{}).get('source_sha256')
    for day, old in existing.items():
        if prior_sha==pdf_source['sha256'] and old and len(days.get(day, [])) < len(old):
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
