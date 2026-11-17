#!/usr/bin/env python3
"""Mittagsmenüs für Wels – kleine Zweit-Ausgabe derselben App (Zwischenprojekt).

Warum es das gibt: Der Betreiber möchte seinem Vater in Wels dieselbe Ansicht
bieten wie WU Food. Die Oberfläche wird wiederverwendet
(wu-lunch-app/preview/wels/ lädt denselben App-Code mit einer eigenen
Datenquelle). Dieses Skript liefert nur die Daten.

Bewusst getrennt von der WU-Pipeline: eigene Ausgabedatei, eigener Workflow,
keine KI, keine Zugangsschlüssel. Ein Fehler hier kann WU Food nicht stören.

Grundsätze (wie bei WU Food):
- Nichts erfinden. Übernommen wird nur, was die Quelle für genau die gesuchte
  Woche ausweist; zeigt sie eine andere Woche, bleibt der Tag leer
  ("Noch nicht veröffentlicht").
- Ein gescheiterter Abruf überschreibt keinen guten Stand derselben Woche.
- Geschrieben wird nur bei inhaltlicher Änderung (keine leeren Commits).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "wu-lunch-app/preview/wels/menus.json"
TZ = ZoneInfo("Europe/Vienna")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
MONTHS = {name: number for number, name in enumerate(
    ("januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober",
     "november", "dezember"), start=1)}
DAY_NAMES = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag")
PRICE = r"(\d{1,2})[.,](\d{2})"

# Stammdaten laut den Webseiten der Restaurants (abgerufen am 17.11.2026);
# Koordinaten aus OpenStreetMap zur jeweiligen Adresse.
RESTAURANTS = [
    {"id": "naschmarkt", "name": "Naschmarkt Wels", "restaurantType": "Österreichisch",
     "url": "https://www.naschmarkt-wels.at/speisekarte-wels-restaurant/",
     "address": "Kaiser-Josef-Platz 21, 4600 Wels", "latitude": 48.1590092, "longitude": 14.0226595,
     "phone": "+43 7242 45 22 94 44", "email": "office@naschmarkt-wels.at",
     "hours": ["Montag bis Freitag 08:00–15:00 Uhr"], "brandColor": "#b5462f"},
    {"id": "inshaas", "name": "In's Haas", "restaurantType": "Café · Bistro",
     "url": "https://www.inshaas.at/mittagskarte/",
     "address": "Stadtplatz 34, 4600 Wels", "latitude": 48.1576037, "longitude": 14.0261885,
     "phone": "+43 7242 216520", "email": "reservierung@inshaas.at",
     "hours": ["Montag bis Samstag 09:00–02:00 Uhr", "Sonn- und Feiertags geschlossen"], "brandColor": "#3f6f5a"},
    {"id": "linde", "name": "Gasthaus zur Linde", "restaurantType": "Österreichisch",
     "url": "https://gasthaus-zur-linde.at/speisekarte",
     "address": "Ringstraße 45, 4600 Wels", "latitude": 48.159415, "longitude": 14.0272387,
     "phone": "07242 46023",
     "hours": ["Dienstag bis Freitag 10:00–14:30 und 16:30–24:00 Uhr",
               "Warme Küche 11:30–14:00 und 17:30–21:00 Uhr",
               "Samstag, Sonntag, Montag und an Feiertagen geschlossen"], "brandColor": "#4f7d3a"},
    {"id": "dokkhun", "name": "Dok Khun", "restaurantType": "Thailändisch",
     "url": "https://dok-khun.metro.biz/?lang=de",
     "address": "Maria-Theresia-Straße 16, 4600 Wels", "latitude": 48.1553411, "longitude": 14.0170914,
     "phone": "+43 7242 252670", "email": "office@dok-khun-thai.at", "brandColor": "#c0842b"},
    # Welche BILLA-PLUS-Filiale gemeint ist, ist nicht bekannt – daher ohne Adresse und Kartenpunkt.
    {"id": "billa", "name": "BILLA PLUS Marktküche", "restaurantType": "Marktküche",
     "url": "https://www.billa.at/unsere-maerkte/billa-plus/marktkueche",
     "hours": ["Mittagsmenü Montag bis Freitag 11:00–14:00 Uhr"], "brandColor": "#d8a400"},
]


class NotThisWeek(Exception):
    """Die Quelle ist erreichbar, zeigt aber (noch) nicht die gesuchte Woche."""


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def target_week(now):
    """Montag der angezeigten Woche – am Wochenende schon die kommende (wie in der App)."""
    today = now.astimezone(TZ).date()
    if today.weekday() >= 5:
        return today + timedelta(days=7 - today.weekday())
    return today - timedelta(days=today.weekday())


def week_dates(monday):
    return [monday + timedelta(days=offset) for offset in range(5)]


def clean(text):
    text = re.sub(r"[​‌‍⁠﻿]", "", str(text or ""))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace(" ", " ")).strip(" \t\n·")


def euro(whole, cents):
    return round(int(whole) + int(cents) / 100, 2)


def lines_of(text):
    return [line for line in (clean(raw) for raw in str(text).splitlines()) if line]


def html_text(raw):
    """Sichtbarer Text einer Seite, ein Blockelement je Zeile."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "template"]):
        element.decompose()
    return "\n".join(lines_of(soup.get_text("\n")))


def long_date(text):
    """'16. November 2026' → date; None, wenn nicht erkennbar."""
    match = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)\s+(\d{4})", text)
    if not match or match.group(2).lower() not in MONTHS:
        return None
    return date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))


def dish(name, price=None, **extra):
    return {"name": clean(name), "price": price, **{key: value for key, value in extra.items() if value}}


# ---------------------------------------------------------------------------
# Naschmarkt Wels: Wochenkarte als Text, Preis hinter jedem Gericht
# ---------------------------------------------------------------------------

def parse_naschmarkt(text, monday):
    flat = clean(text.replace("\n", " "))
    period = re.search(r"(\d{1,2})\.(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", flat)
    if not period:
        raise ValueError("Naschmarkt: Zeitraum der Wochenkarte nicht gefunden")
    start = date(int(period.group(5)), int(period.group(2)), int(period.group(1)))
    if start != monday:
        raise NotThisWeek(f"Naschmarkt zeigt die Woche ab {start.isoformat()}")
    body = flat[period.end():]
    body = re.split(r"Wahlweise\s*:|Alle Gerichte sind hausgemacht", body)[0]
    header = re.compile(r"\b(" + "|".join(DAY_NAMES) + r")\s+(\d{1,2})\.(\d{1,2})\.")
    marks = list(header.finditer(body))
    if not marks:
        raise ValueError("Naschmarkt: keine Tagesüberschriften gefunden")
    offers = lambda part: [dish(name, euro(a, b)) for name, a, b in re.findall(r"(.+?)\s*€\s*" + PRICE, part)]
    star = re.sub(r"^.*?Star der Woche", "", body[:marks[0].start()]) if "Star der Woche" in body[:marks[0].start()] else ""
    weekly = [{**row, "description": "Star der Woche"} for row in offers(star)]
    days = {}
    for index, mark in enumerate(marks):
        day = date(monday.year, int(mark.group(3)), int(mark.group(2)))
        if day not in week_dates(monday) or DAY_NAMES[day.weekday()] != mark.group(1):
            raise ValueError(f"Naschmarkt: Tagesangabe {mark.group(0)} passt nicht zur Woche")
        part = body[mark.end():marks[index + 1].start() if index + 1 < len(marks) else len(body)]
        rows = offers(part)
        if rows:
            days[day.isoformat()] = rows + weekly
    return days


# ---------------------------------------------------------------------------
# In's Haas: Gerichte je Tag ohne Einzelpreis, dazu ein Tarif je Speisenart
# ---------------------------------------------------------------------------

MEAT_OR_FISH = re.compile(
    r"huhn|hühn|hendl|henderl|pute|schwein|rind|kalb|lamm|wild|hirsch|reh|ente|gans|speck|schinken|wurst|würstel|"
    r"faschiert|schnitzel|geschnetzelt|gulasch vom|braten|leberkäs|lachs|kabeljau|fisch|forelle|zander|garnele|"
    r"thunfisch|beef|steak|burger", re.I)


def parse_inshaas(text, monday):
    rows = lines_of(text)
    try:
        start = next(index for index, line in enumerate(rows) if re.search(r"Mittagsmenü im Haas", line, re.I))
    except StopIteration:
        raise ValueError("In's Haas: Überschrift der Mittagskarte nicht gefunden") from None
    rows = rows[start + 1:]
    tariff = {}
    for label, key in (("Tagessuppe", "soup"), ("Vegetarische Speisen", "veggie"),
                       ("Fleisch-/Fischgerichte", "meat"), ("Salate", "salad")):
        match = re.search(re.escape(label) + r"\s*:\s*" + PRICE + r"\s*€", "\n".join(rows))
        if match:
            tariff[key] = euro(match.group(1), match.group(2))
    days, current = {}, None
    for index, line in enumerate(rows):
        if line in DAY_NAMES:
            day = long_date(rows[index + 1]) if index + 1 < len(rows) else None
            if day is None:
                raise ValueError(f"In's Haas: Datum zu {line} fehlt")
            if day not in week_dates(monday):
                raise NotThisWeek(f"In's Haas zeigt {day.isoformat()}")
            if DAY_NAMES[day.weekday()] != line:
                raise ValueError(f"In's Haas: {line} passt nicht zum Datum {day.isoformat()}")
            current = days.setdefault(day.isoformat(), [])
            continue
        if current is None or long_date(line):
            continue
        if re.match(r"(Tagessuppe|Vegetarische Speisen|Fleisch-/Fischgerichte|Salate)\s*:", line) or line == "Unser":
            current = None
            continue
        current.append(line)
    if not days:
        raise ValueError("In's Haas: keine Tage gefunden")
    result = {}
    for day, names in days.items():
        if not names:
            continue
        # Die Karte nennt Preise nur je Speisenart. Zugeordnet wird nur das bisher
        # durchgängige Muster "Fleisch/Fisch – vegetarisch – Salat"; weicht ein Tag
        # davon ab, bleiben die Einzelpreise leer und der Tarif steht als Hinweis da.
        pattern = (len(names) == 3 and {"meat", "veggie", "salad"} <= set(tariff)
                   and MEAT_OR_FISH.search(names[0]) and not MEAT_OR_FISH.search(names[1])
                   and re.search(r"salat", names[2], re.I))
        if pattern:
            entries = [dish(names[0], tariff["meat"]), dish(names[1], tariff["veggie"]),
                       dish(names[2], tariff["salad"], category="Salat")]
        else:
            note = " · ".join(f"{label} {value:.2f} €".replace(".", ",") for label, value in (
                ("Fleisch/Fisch", tariff.get("meat")), ("Vegetarisch", tariff.get("veggie")),
                ("Salat", tariff.get("salad"))) if value)
            entries = [dish(name, None, priceLabel=" ", description=note) for name in names]
        if "soup" in tariff:
            entries.append(dish("Tagessuppe", tariff["soup"], category="Suppe"))
        result[day] = entries
    return result


# ---------------------------------------------------------------------------
# Gasthaus zur Linde: Menüplan Dienstag bis Freitag, Suppe + Hauptspeise + Preis
# ---------------------------------------------------------------------------

def parse_linde(text, monday):
    rows = lines_of(text)
    try:
        start = next(index for index, line in enumerate(rows) if line == "Mittagsmenüplan")
    except StopIteration:
        raise ValueError("Zur Linde: Mittagsmenüplan nicht gefunden") from None
    period = re.match(r"(.+?)\s+bis\s+(.+)", rows[start + 1]) if start + 1 < len(rows) else None
    first, last = (long_date(period.group(1)), long_date(period.group(2))) if period else (None, None)
    if not first or not last or last < first or (last - first).days > 4:
        raise ValueError("Zur Linde: Zeitraum des Menüplans nicht lesbar")
    if first not in week_dates(monday) or last not in week_dates(monday):
        raise NotThisWeek(f"Zur Linde zeigt {first.isoformat()} bis {last.isoformat()}")
    blocks, buffer = [], []
    for line in rows[start + 2:]:
        if re.match(r"Änderungen vorbehalten", line, re.I):
            break
        if re.fullmatch(r"(Mo|Di|Mi|Do|Fr)\.", line):
            continue  # Die Seite lässt das Kürzel teils weg; gezählt wird über die Preiszeilen.
        price = re.fullmatch(r"€\s*" + PRICE, line)
        if price:
            blocks.append((buffer, euro(price.group(1), price.group(2))))
            buffer = []
        else:
            buffer.append(line)
    expected = (last - first).days + 1
    if len(blocks) != expected or any(not names for names, _ in blocks):
        raise ValueError(f"Zur Linde: {len(blocks)} Menüs für {expected} Tage – Zuordnung unsicher")
    days = {}
    for offset, (names, price) in enumerate(blocks):
        soup = names[0] if len(names) > 1 and re.search(r"suppe", names[0], re.I) else ""
        main = " ".join(names[1:] if soup else names)
        days[(first + timedelta(days=offset)).isoformat()] = [dish(main, price, included_soup=soup)]
    return days


# ---------------------------------------------------------------------------
# Dok Khun: Wochen-PDF (Text), je Tag Vorspeise + Menü 1 + Menü 2
# ---------------------------------------------------------------------------

def find_dokkhun_pdf(raw, base):
    from bs4 import BeautifulSoup
    for link in BeautifulSoup(raw, "html.parser").find_all("a", href=True):
        if link["href"].lower().endswith(".pdf") and (
                re.search(r"men[üu]\s*kw", link.get_text(" "), re.I) or re.search(r"menu-kw", link["href"], re.I)):
            return urljoin(base, link["href"])
    raise NotThisWeek("Dok Khun: kein Wochenmenü-PDF verlinkt")


def parse_dokkhun(text, monday):
    rows = lines_of(text)
    period = re.search(r"\(\s*(\d{1,2})\.\s*([A-Za-zäöü]+)\s*[–-]\s*(\d{1,2})\.\s*([A-Za-zäöü]+)\s+(\d{4})\s*\)", " ".join(rows))
    if not period or period.group(2).lower() not in MONTHS:
        raise ValueError("Dok Khun: Zeitraum des Wochenmenüs nicht gefunden")
    first = date(int(period.group(5)), MONTHS[period.group(2).lower()], int(period.group(1)))
    if first not in week_dates(monday):
        raise NotThisWeek(f"Dok Khun zeigt die Woche ab {first.isoformat()}")
    reduction = re.search(r"Nur Hauptspeise\s*:\s*-?\s*€\s*" + PRICE, " ".join(rows))
    note = (f"Nur Hauptspeise: {euro(reduction.group(1), reduction.group(2)):.2f} € günstiger".replace(".", ",")
            if reduction else "")
    # Tagesnamen stehen teils mit Tippfehler in der Karte ("Donnertag").
    prefixes = {"mon": 0, "die": 1, "mit": 2, "don": 3, "fre": 4}
    days, weekday, part, parts = {}, None, None, {}

    def finish():
        if weekday is None:
            return
        entries = []
        starter = clean(" ".join(parts.get("starter", [])))
        for key in ("menu1", "menu2"):
            body = " ".join(parts.get(key, []))
            price = re.search(r"€\s*" + PRICE, body)
            name = clean(re.sub(r"€\s*" + PRICE, " ", body))
            if name and price:
                entries.append(dish(name, euro(price.group(1), price.group(2)), included_starter=starter,
                                    description=note))
        if entries:
            days[(monday + timedelta(days=weekday)).isoformat()] = entries

    for line in rows:
        word = line.lower()
        if re.fullmatch(r"[a-zäöü]{6,10}", word) and word[:3] in prefixes and (word.endswith("tag") or word == "mittwoch"):
            finish()
            weekday, part, parts = prefixes[word[:3]], None, {}
            continue
        if weekday is None or re.match(r"Mittagsmenü|\(|Nur Hauptspeise", line):
            continue
        label = re.match(r"(Vorspeise|Menü\s*1|Menü\s*2)\b\s*(.*)", line)
        if label:
            part = {"vorspeise": "starter", "menü1": "menu1", "menü2": "menu2"}[re.sub(r"\s", "", label.group(1).lower())]
            line = label.group(2)
        if part and line:
            parts.setdefault(part, []).append(line)
    finish()
    return days


# ---------------------------------------------------------------------------
# BILLA PLUS Marktküche: Plakat-PDF, Zuordnung über die Position im Raster
# ---------------------------------------------------------------------------

def find_billa_pdf(raw, base):
    from bs4 import BeautifulSoup
    for link in BeautifulSoup(raw, "html.parser").find_all("a", href=True):
        label = (link.get("aria-label") or "") + " " + link.get_text(" ")
        if link["href"].lower().endswith(".pdf") and re.search(r"mittagsmen", label + link["href"], re.I):
            return urljoin(base, link["href"])
    raise NotThisWeek("BILLA: kein Mittagsmenü-PDF verlinkt")


def pdf_pages(raw):
    """Je Seite: Wörter und Textblöcke mit Position (x0, y0, x1, y1, Text)."""
    import pymupdf
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        return [{"words": [list(word[:5]) for word in page.get_text("words")],
                 "blocks": [list(block[:5]) for block in page.get_text("blocks") if block[6] == 0]}
                for page in document]


def pdf_text(raw):
    import pymupdf
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        return "\n".join(page.get_text() for page in document)


def join_block(text):
    """Zeilen eines Plakatblocks verbinden; Silbentrennung am Zeilenende auflösen."""
    out = ""
    for line in lines_of(text):
        out = out[:-1] + line if out.endswith("-") and line[:1].islower() else (out + " " + line).strip()
    return out


def parse_billa_page(page, monday):
    """Gerichte einer Plakatseite oder None, wenn sie eine andere Woche zeigt."""
    whole = clean(" ".join(block[4] for block in page["blocks"]))
    valid = re.search(r"Gültig von\s*(\d{1,2})\.\s*(\d{1,2})\.\s*bis\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", whole)
    if not valid:
        raise ValueError("BILLA: Gültigkeitszeitraum nicht gefunden")
    start = date(int(valid.group(5)), int(valid.group(2)), int(valid.group(1)))
    if start != monday:
        return None
    words = page["words"]
    labels = {text: (y0 + y1) / 2 for x0, y0, x1, y1, text in words if text in ("MO", "DI", "MI", "DO", "FR") and x0 < 110}
    if sorted(labels, key=labels.get) != ["MO", "DI", "MI", "DO", "FR"]:
        raise ValueError("BILLA: Tageszeilen MO–FR nicht vollständig erkannt")
    centers = [labels[key] for key in ("MO", "DI", "MI", "DO", "FR")]
    step = (centers[-1] - centers[0]) / 4
    if step <= 0 or any(abs((b - a) - step) > step * 0.35 for a, b in zip(centers, centers[1:])):
        raise ValueError("BILLA: Raster der Tageszeilen unregelmäßig")
    numbers = {words[index + 1][4]: (x0, y0) for index, (x0, y0, x1, y1, text) in enumerate(words)
               if text == "Menü" and index + 1 < len(words) and words[index + 1][4] in ("1:", "2:")}
    if set(numbers) != {"1:", "2:"}:
        raise ValueError("BILLA: Überschriften Menü 1/Menü 2 nicht erkannt")
    # Der Preis von Menü 1 steht rechts neben dessen Überschrift, also noch vor "Menü 2:".
    # Die Gerichte beginnen dagegen jeweils unter ihrer Überschrift.
    split, head_y = numbers["2:"][0], numbers["1:"][1]
    dish_split = (numbers["1:"][0] + numbers["2:"][0]) / 2
    # Preise stehen als große Zahl mit hochgestellten Cent in der Überschriftenzeile.
    digits = sorted((x0, text) for x0, y0, x1, y1, text in words
                    if re.fullmatch(r"\d{1,2}", text) and abs(y0 - head_y) < step * 0.6)
    prices = []
    for (x_whole, whole_part), (x_cents, cents) in zip(digits[::2], digits[1::2]):
        if len(cents) != 2:
            raise ValueError("BILLA: Preisangabe nicht lesbar")
        prices.append((x_whole, euro(whole_part, cents)))
    left = [value for x, value in prices if x < split]
    right = [value for x, value in prices if x >= split]
    if len(left) != 1 or len(right) != 1:
        raise ValueError("BILLA: Preise für Menü 1/Menü 2 nicht eindeutig")
    cells = {}
    for x0, y0, x1, y1, text in sorted(page["blocks"], key=lambda block: (block[1], block[0])):
        middle = (y0 + y1) / 2
        if x0 < 100 or clean(text).lower() == "veggie" or not centers[0] - step / 2 <= middle < centers[-1] + step / 2:
            continue
        row = min(range(5), key=lambda index: abs(centers[index] - middle))
        cells.setdefault((row, 0 if x0 < dish_split else 1), []).append(text)
    footnote = "Gericht kann je Filiale abweichen" if re.search(r"Gericht kann", whole) else ""
    included = "Mit Suppe oder Dessert" if re.search(r"wahlweise Suppe oder Dessert", whole) else ""
    days = {}
    for row in range(5):
        entries = []
        for column, price in ((0, left[0]), (1, right[0])):
            name = join_block("\n".join(cells.get((row, column), [])))
            if not name:
                continue
            starred = "*" in name
            entries.append(dish(name.replace("*", ""), price,
                                description=" · ".join(part for part in (included, footnote if starred else "") if part)))
        if len(entries) != 2:
            raise ValueError(f"BILLA: Zeile {row + 1} hat nicht genau zwei Menüs")
        days[(monday + timedelta(days=row)).isoformat()] = entries
    return days


def parse_billa(pages, monday):
    for page in pages:
        days = parse_billa_page(page, monday)
        if days:
            return days
    raise NotThisWeek("BILLA: kein Plakat für die gesuchte Woche")


# ---------------------------------------------------------------------------
# Abruf und Zusammenführen
# ---------------------------------------------------------------------------

def http_get(url, max_bytes=12_000_000):
    import requests
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=40)
    response.raise_for_status()
    if len(response.content) > max_bytes:
        raise ValueError("Quelle zu groß")
    return response.content


def fetch(identifier, url, monday, get=http_get):
    raw = get(url)
    if identifier == "naschmarkt":
        return parse_naschmarkt(html_text(raw), monday)
    if identifier == "inshaas":
        return parse_inshaas(html_text(raw), monday)
    if identifier == "linde":
        return parse_linde(html_text(raw), monday)
    if identifier == "dokkhun":
        return parse_dokkhun(pdf_text(get(find_dokkhun_pdf(raw, url))), monday)
    if identifier == "billa":
        return parse_billa(pdf_pages(get(find_billa_pdf(raw, url))), monday)
    raise ValueError("Unbekannte Quelle: " + identifier)


def check(days, monday):
    """Letzte Sicherung vor dem Übernehmen: nur plausible Einträge der gesuchten Woche."""
    allowed = {day.isoformat() for day in week_dates(monday)}
    if not days:
        raise ValueError("keine Gerichte erkannt")
    for day, rows in days.items():
        if day not in allowed:
            raise ValueError(f"Tag {day} liegt außerhalb der Woche")
        if not rows:
            raise ValueError(f"Tag {day} ohne Gerichte")
        for row in rows:
            if not 4 <= len(row["name"]) <= 260 or not re.search(r"[A-Za-zÄÖÜäöü]{3}", row["name"]):
                raise ValueError(f"unplausibler Gerichtname am {day}: {row['name'][:60]!r}")
            if row.get("price") is not None and not 2 <= row["price"] <= 45:
                raise ValueError(f"unplausibler Preis am {day}: {row['price']}")
    return days


def build(previous, monday, now, get=http_get):
    """Neuen Gesamtstand berechnen. `previous` ist der bisher veröffentlichte Stand."""
    same_week = (previous or {}).get("weekStart") == monday.isoformat()
    before = {row["id"]: row for row in (previous or {}).get("restaurants", [])} if same_week else {}
    restaurants = []
    for base in RESTAURANTS:
        old = before.get(base["id"], {})
        days, state, message = {}, "ok", ""
        try:
            days = check(fetch(base["id"], base["url"], monday, get), monday)
        except NotThisWeek as reason:
            state, message, days = "not_published", str(reason), old.get("days", {})
        except Exception as error:  # Abruf- oder Lesefehler: guten Stand derselben Woche behalten
            state, message, days = "error", f"{type(error).__name__}: {error}"[:240], old.get("days", {})
        complete = {day.isoformat(): days.get(day.isoformat(), []) for day in week_dates(monday)}
        restaurants.append({**base, "days": complete, "import": {"state": state, "message": message}})
        print(f"{base['name']}: {state}" + (f" – {message}" if message else "")
              + " | Gerichte je Tag: " + ", ".join(str(len(rows)) for rows in complete.values()), flush=True)
    content = {"weekStart": monday.isoformat(), "restaurants": restaurants}
    unchanged = previous and {key: previous.get(key) for key in content} == content
    return {**content, "updatedAt": previous["updatedAt"] if unchanged else now.isoformat(timespec="seconds")}


def main():
    now = datetime.now(TZ)
    previous = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else None
    result = build(previous, target_week(now), now)
    if result == previous:
        print("Wels: keine Änderung")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("Wels: Stand geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
