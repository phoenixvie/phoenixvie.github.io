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

import hashlib
import json
import re
import subprocess
import sys
import tempfile
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
    # Ergänzt am 17.11.2026 (zweite Liste des Betreibers).
    {"id": "denns", "name": "Denns BioMarkt Bistro", "restaurantType": "Bio-Bistro",
     "url": "https://www.denns-biomarkt.at/wels-malvenstr-5/mittagsgerichte/",
     "address": "Malvenstraße 5, 4600 Wels", "latitude": 48.1439914, "longitude": 13.9704601, "brandColor": "#6a9a2d"},
    {"id": "huber", "name": "Gasthaus Huber", "restaurantType": "Österreichisch",
     "url": "https://www.gasthaus-huber.at/tages-menue",
     "address": "Wiesenstraße 69, 4600 Wels", "latitude": 48.1630194, "longitude": 14.0450788,
     "phone": "+43 7242 45030",
     "hours": ["Montag bis Freitag 09:00–24:00 Uhr", "Warme Küche 11:00–14:00 und 17:00–21:00 Uhr",
               "Samstag, Sonntag und Feiertag geschlossen"], "brandColor": "#7a5a3a"},
    {"id": "goesser", "name": "Gösserbräu", "restaurantType": "Österreichisch",
     "url": "https://www.goesserbraeu.at/restaurant/mittagsmenue/",
     "address": "Kaiser-Josef-Platz 27, 4600 Wels", "latitude": 48.1586061, "longitude": 14.0212375,
     "phone": "+43 7242 60 460", "brandColor": "#1f6b3a"},
    {"id": "hannibal", "name": "Hannibal", "restaurantType": "Österreichisch",
     "url": "https://www.restaurant-hannibal.at/mittagskarte/",
     "address": "Maxlheid 9, 4600 Wels", "latitude": 48.1864802, "longitude": 14.0759777,
     "phone": "+43 7242 46716 46", "email": "hotel@maxlhaid.at",
     "hours": ["Montag bis Freitag 10:00–23:30 Uhr (außer Feiertage)", "Warme Küche 11:30–21:30 Uhr"],
     "brandColor": "#8c2f39"},
    {"id": "hayashi", "name": "Hayashi", "restaurantType": "Asiatisch",
     "url": "https://www.hayashi.at/menu4.html",
     "address": "Charwatstraße 2, 4600 Wels", "latitude": 48.1576027, "longitude": 14.016551,
     "phone": "07242 214081", "email": "welcome@hayashi.at",
     "hours": ["Montag Ruhetag", "Dienstag bis Donnerstag 11:30–15:00 und 17:00–22:00 Uhr",
               "Freitag und Samstag 11:30–22:00 Uhr", "Sonntag 11:30–21:30 Uhr",
               "Lunch Dienstag bis Freitag 11:30–14:30 Uhr"], "brandColor": "#2b2b2b"},
    {"id": "imturm", "name": "Im Turm", "restaurantType": "Messerestaurant",
     "url": "https://imturm.at/mittagsmenue-druckversion/",
     "address": "Messeplatz 1, 4600 Wels (Messezentrum Neu, 1. Stock)", "latitude": 48.1518071, "longitude": 14.0187612,
     "phone": "+43 7242 9392 5050", "email": "essen@imturm.at",
     "hours": ["Montag bis Freitag 10:00–14:30 Uhr", "Mittags-Brunch 11:30–14:00 Uhr",
               "Samstag, Sonntag und Feiertag geschlossen"], "brandColor": "#35607f"},
    {"id": "lalina", "name": "La lina", "restaurantType": "Restaurant · Bar",
     "url": "https://lalina.at/lunchevents/",
     "address": "Europastraße 45, 4600 Wels", "latitude": 48.14983, "longitude": 13.9939371,
     "phone": "+43 690 106 33 193", "email": "office@lalina.at",
     "hours": ["Lunch Dienstag bis Freitag 11:30–14:00 Uhr"], "brandColor": "#b0607a"},
    {"id": "ox", "name": "OX", "restaurantType": "Steaks & Grill",
     "url": "https://www.ox-wels.at/",
     "address": "Waidhausenstraße 26, 4600 Wels", "latitude": 48.1470255, "longitude": 13.9776431,
     "phone": "+43 7242 225777", "email": "office@ox-wels.at",
     "hours": ["Montag bis Sonntag 11:00–24:00 Uhr", "Mittagsmenü Montag bis Freitag 11:30–14:00 Uhr"],
     "brandColor": "#5b3a29"},
    {"id": "sorrymama", "name": "Sorry Mama", "restaurantType": "Kitchen & Bar",
     "url": "https://www.sorrymama.at/mittagskarte/",
     "address": "Stadtplatz 11, 4600 Wels", "latitude": 48.1570147, "longitude": 14.0259031,
     "phone": "+43 7242 911117", "email": "office@sorrymama.at",
     "hours": ["Montag bis Donnerstag 11:30–22:30 Uhr", "Freitag und Samstag 11:30–24:00 Uhr",
               "Warme Küche 11:30–14:00 und 17:00–21:30 Uhr"], "brandColor": "#d9534f"},
]
# In der Liste alphabetisch, damit man ein Restaurant schnell findet.
RESTAURANTS.sort(key=lambda row: row["name"].replace("'", "").casefold())

# Abruf-Adresse, wo sie von der für Menschen gedachten Seite (url) abweicht.
DATA_URLS = {"denns": "https://www.denns-biomarkt.at/page-data/wels-malvenstr-5/mittagsgerichte/page-data.json"}
# Tageskarte: jeder Abruf liefert nur den heutigen Tag; frühere Tage der Woche bleiben stehen.
DAILY = {"huber"}
# Karte ohne Datum: gilt erst als neue Woche, wenn sie sich gegenüber der Vorwoche geändert hat.
UNDATED = {"ox"}

# Hayashi: feste Mittagskarte als Bild (kein Wochenmenü). Der Inhalt wurde am 17.11.2026 vom Bild
# abgeschrieben und gilt genau für diese Bilddatei; ändert das Restaurant das Bild, wird nichts
# mehr angezeigt, bis die Karte hier nachgezogen ist (lieber leer als veraltet).
HAYASHI_IMAGE = "https://www.hayashi.at/images/menu2.jpg"
HAYASHI_SHA256 = "d7aa784d3d79e9dc61640c6f0805b1d506986aa30c93bfc17be52cb76f2e3375"
HAYASHI_LUNCH = [
    ("Black Pepper Chicken", "Hühnerfleisch | schwarze Pfeffersauce | Saisongemüse", 13.9),
    ("Gaeng Khiao Wan", "grünes Thaicurry | gegrillte Ente | Kokosmilch | Zitronengras", 14.9),
    ("Chili Beef", "Rinderfilet | Szechuan Chili & Pfeffer", 18.9),
    ("Bulgogi", "mariniertes Rindfleisch | koreanische Art | Bao Brötchen", 14.9),
    ("Gaeng Phed", "rotes Thaicurry | Hühnerfleisch", 13.9),
    ("Yaki Udon", "Wok Udon-Nudeln | Saisongemüse", 12.5),
    ("Wok Saisongemüse", "", 12.5),
    ("Asam Gulai", "Malaysisches Curry | Garnelen | Kokosmilch", 17.9),
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
# Im Turm: Tagesblöcke mit einem Preis für Suppe, Hauptgericht, Salatbuffet, Dessert
# ---------------------------------------------------------------------------

def parse_imturm(text, monday):
    rows = lines_of(text)
    try:
        start = next(index for index, line in enumerate(rows) if line == "Menüplan der Woche")
    except StopIteration:
        raise ValueError("Im Turm: Menüplan nicht gefunden") from None
    period = re.match(r"(\d{1,2})\.(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.", rows[start + 1]) if start + 1 < len(rows) else None
    if not period:
        raise ValueError("Im Turm: Zeitraum nicht lesbar")
    if (int(period.group(1)), int(period.group(2))) != (monday.day, monday.month):
        raise NotThisWeek(f"Im Turm zeigt die Woche ab {period.group(1)}.{period.group(2)}.")
    days, weekday, price, names = {}, None, None, []

    def finish():
        if weekday is None or not names:
            return
        soup = names[0] if re.search(r"suppe", names[0], re.I) else ""
        extras = [name for name in names if name in ("Salatbuffet", "Dessert")]
        mains = [name for name in names[1 if soup else 0:] if name not in extras]
        note = "Mit " + " und ".join(extras) if extras else ""
        days[(monday + timedelta(days=weekday)).isoformat()] = [
            dish(name, price, included_soup=soup, description=note) for name in mains]

    for line in rows[start + 2:]:
        if line in DAY_NAMES:
            finish()
            weekday, price, names = DAY_NAMES.index(line), None, []
            continue
        if weekday is None:
            continue
        if re.match(r"Imturm Messerestaurant|Mittags-Brunch nach Herzenslust", line):
            break
        cost = re.fullmatch(r"€\s*" + PRICE, line)
        if cost:
            price = euro(cost.group(1), cost.group(2))
        else:
            names.append(line)
    finish()
    return days


# ---------------------------------------------------------------------------
# Hannibal: je Tag zwei Gerichte, Preise nur als Tarif (Fleisch, vegetarisch, Burger)
# ---------------------------------------------------------------------------

def parse_hannibal(text, monday):
    rows = lines_of(text)
    span = re.search(r"(\d{1,2})\.\s*([A-Za-zäöü]+)\s+bis\s+\d{1,2}\.\s*[A-Za-zäöü]+\s+(\d{4})", "\n".join(rows))
    if not span or span.group(2).lower() not in MONTHS:
        raise ValueError("Hannibal: Zeitraum der Mittagskarte nicht gefunden")
    period = date(int(span.group(3)), MONTHS[span.group(2).lower()], int(span.group(1)))
    if period != monday:
        raise NotThisWeek(f"Hannibal zeigt die Woche ab {period.isoformat()}")
    whole = "\n".join(rows)
    tariff = {}
    for label, key in (("Fleischgericht", "meat"), ("vegetarisches Gericht", "veggie"), ("Burger", "burger")):
        match = re.search(re.escape(label) + r"\s*€\s*" + PRICE, whole, re.I)
        if match:
            tariff[key] = euro(match.group(1), match.group(2))
    days, current = {}, None
    for line in rows:
        if line in DAY_NAMES:
            current = days.setdefault((monday + timedelta(days=DAY_NAMES.index(line))).isoformat(), [])
            continue
        if current is None or line == "oder":
            continue
        if re.match(r"Vorspeisen|Desserts|Hauptspeisen", line):
            break
        current.append(line)
    result = {}
    for day, names in days.items():
        if not names:
            continue
        note = " · ".join(f"{label} {value:.2f} €".replace(".", ",") for label, value in (
            ("Fleischgericht", tariff.get("meat")), ("Vegetarisch", tariff.get("veggie")),
            ("Burger", tariff.get("burger"))) if value)
        burgers = all(re.search(r"burger", name, re.I) for name in names)
        usual = (len(names) == 2 and {"meat", "veggie"} <= set(tariff) and MEAT_OR_FISH.search(names[0])
                 and not MEAT_OR_FISH.search(names[1]) and not any(re.search(r"burger", name, re.I) for name in names))
        if burgers and "burger" in tariff:
            result[day] = [dish(name, tariff["burger"]) for name in names]
        elif usual:
            result[day] = [dish(names[0], tariff["meat"]), dish(names[1], tariff["veggie"])]
        else:  # Zuordnung nicht eindeutig: Tarif als Hinweis statt eines geratenen Preises
            result[day] = [dish(name, None, priceLabel=" ", description=note) for name in names]
    return result


# ---------------------------------------------------------------------------
# La lina: Mittagslunch Dienstag bis Freitag, ein Preis, vegetarisches Wochengericht
# ---------------------------------------------------------------------------

def parse_lalina(text, monday):
    rows = lines_of(text)
    header = re.compile(r"Mittagslunch\s+(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.\s*([A-Za-zäöü]+)\s+(\d{4})")
    marks = [index for index, line in enumerate(rows) if header.match(line)]
    if not marks:
        raise ValueError("La lina: kein Mittagslunch gefunden")
    first = header.match(rows[marks[0]])
    if first.group(3).lower() not in MONTHS:
        raise ValueError("La lina: Monat nicht lesbar")
    start = date(int(first.group(4)), MONTHS[first.group(3).lower()], int(first.group(1)))
    if start not in week_dates(monday):
        raise NotThisWeek(f"La lina zeigt die Woche ab {start.isoformat()}")
    cost = re.search(r"€\s*" + PRICE, "\n".join(rows[:marks[0]]))
    price = euro(cost.group(1), cost.group(2)) if cost else None
    block = rows[marks[0] + 1:marks[1] if len(marks) > 1 else len(rows)]
    veggie, days = "", {}
    upper = {name.upper(): index for index, name in enumerate(DAY_NAMES)}
    for index, line in enumerate(block):
        label = re.match(r"Vegetarisches Wochengericht\s*[:\-–]\s*(.*)", line)
        if label and not veggie:
            veggie = label.group(1) or (block[index + 1] if index + 1 < len(block) else "")
        if line in upper and index + 1 < len(block):
            name = re.sub(r"\s*/\s*Vegetarisches Wochengericht", "", block[index + 1])
            entries = [dish(name, price)]
            if veggie:
                entries.append(dish(veggie, price, description="Vegetarisches Wochengericht"))
            days[(monday + timedelta(days=upper[line])).isoformat()] = entries
    return days


# ---------------------------------------------------------------------------
# OX: Mittagsmenü ohne Datum (siehe UNDATED), je Tag zwei Gerichte zu einem Preis
# ---------------------------------------------------------------------------

def parse_ox(text, monday):
    rows = lines_of(text)
    try:
        start = next(index for index, line in enumerate(rows) if line == "Mittagsmenü")
    except StopIteration:
        raise ValueError("OX: Mittagsmenü nicht gefunden") from None
    days, weekday, names = {}, None, []
    for line in rows[start:]:
        if line in DAY_NAMES:
            if DAY_NAMES.index(line) in days or (weekday is not None and DAY_NAMES.index(line) <= weekday):
                break  # die Seite enthält die Karte zweimal (Handy- und Desktop-Ansicht)
            weekday, names = DAY_NAMES.index(line), []
            continue
        if weekday is None:
            continue
        cost = re.fullmatch(r"€\s*" + PRICE, line)
        if cost:
            starter = names[0] if names and re.search(r"suppe|salat", names[0], re.I) and len(names) > 1 else ""
            days[weekday] = [dish(name, euro(cost.group(1), cost.group(2)), included_starter=starter)
                             for name in names[1 if starter else 0:]]
            names = []
        else:
            names.append(line)
    if not days:
        raise ValueError("OX: keine Tage erkannt")
    return {(monday + timedelta(days=weekday)).isoformat(): rows_ for weekday, rows_ in days.items()}


# ---------------------------------------------------------------------------
# Gösserbräu: Monatsplan als PDF, je Tag zwei Menüs, keine Preise in der Quelle
# ---------------------------------------------------------------------------

def find_goesser_pdfs(raw):
    text = raw.decode("utf-8", "replace").replace("\\/", "/")
    found = sorted(set(re.findall(r"https://www\.goesserbraeu\.at/[^\"'\\&<> ]*MONATSPLAN[^\"'\\&<> ]*\.pdf", text, re.I)))
    if not found:
        raise NotThisWeek("Gösserbräu: kein Monatsplan verlinkt")
    return found


def parse_goesser(text, monday):
    marks = list(re.finditer(r"\b(\d{2})\.(\d{2})\.(\d{2})\b", text))
    days = {}
    for index, mark in enumerate(marks):
        try:
            day = date(2000 + int(mark.group(3)), int(mark.group(2)), int(mark.group(1)))
        except ValueError:
            continue
        if day not in week_dates(monday):
            continue
        chunk = text[mark.end():marks[index + 1].start() if index + 1 < len(marks) else len(text)]
        entries = []
        for line in lines_of(chunk):
            if re.fullmatch(r"(Mo|Di|Mi|Do|Fr|Sa|So)\.", line):
                continue
            veggie = bool(re.search(r"/?\s*veg\w*\s*$", line, re.I))
            name = re.sub(r"\s*/?\s*veg\w*\s*$", "", line, flags=re.I)
            # Allergen-Kennbuchstaben am Zeilenende ("ACGLM", "A,C,G,L", "A F M L") gehören nicht zum Namen.
            name = re.sub(r"(?<=[a-zäöüß.\")])\s*(?:[A-R]\s?,?\s?){2,}$", "", name)
            entries.append(dish(name, None, priceLabel=" ", description="Vegetarisch" if veggie else ""))
        if entries:
            days[day.isoformat()] = entries[:2]
    return days


# ---------------------------------------------------------------------------
# Gasthaus Huber: Tageskarte als PDF (nur der heutige Tag, siehe DAILY)
# ---------------------------------------------------------------------------

def tidy_caps(text):
    """'LEBERNETZBRATEN mit Kartoffeln' → 'Lebernetzbraten mit Kartoffeln'."""
    return " ".join(word.capitalize() if word.isupper() and len(word) > 3 else word for word in text.split())


def parse_huber(text, monday):
    rows = lines_of(text)
    head = re.search(r"Tagesmenü\s+\w+,\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", "\n".join(rows))
    if not head:
        raise ValueError("Huber: Datum der Tageskarte nicht gefunden")
    day = date(int(head.group(3)), int(head.group(2)), int(head.group(1)))
    if day not in week_dates(monday):
        raise NotThisWeek(f"Huber zeigt die Tageskarte vom {day.isoformat()}")
    entries, buffer, soup, dessert = [], [], "", False
    for line in rows[1:]:
        if re.match(r"WIR EMPFEHLEN|Gasthof Huber", line):
            break
        if line == "DESSERT":
            dessert, buffer = True, []
            continue
        cost = re.fullmatch(PRICE + r"\s*€", line)
        if cost and buffer:
            entries.append(dish(tidy_caps(" ".join(buffer)), euro(cost.group(1), cost.group(2)),
                                included_soup="" if dessert else soup, category="Nachspeise" if dessert else ""))
            buffer = []
        elif not entries and not buffer and re.fullmatch(r"Tagessuppe", line, re.I):
            soup = "Tagessuppe"
        elif not re.match(r"Tagesmenü", line):
            buffer.append(line)
    return {day.isoformat(): entries} if entries else {}


# ---------------------------------------------------------------------------
# Denns BioMarkt: strukturierte Daten der Marktseite
# ---------------------------------------------------------------------------

def parse_denns(payload, monday):
    nodes = payload["result"]["data"]["allSanityLunchOffer"]["nodes"]
    year, week, _ = monday.isocalendar()
    node = next((row for row in nodes if row.get("year") == year and row.get("week") == week), None)
    if node is None:
        raise NotThisWeek("Denns: keine Wochenkarte für die gesuchte Woche")
    allowed = [day.isoformat() for day in week_dates(monday)]
    days = {day: [] for day in allowed}
    for item in sorted(node.get("menuItems") or [], key=lambda row: row.get("index") or 0):
        title = clean(" ".join(part for part in (item.get("title"), item.get("subtitle")) if part))
        if not title or not isinstance(item.get("price"), (int, float)):
            continue
        tags = "Vegan" if item.get("vegan") else "Vegetarisch" if item.get("vegetarian") else ""
        entry = dish(title, round(float(item["price"]), 2), description=tags,
                     category="Suppe" if re.search(r"suppe", title, re.I) else "")
        for day in (allowed if item.get("allweek") else [str(item.get("day"))[:10]]):
            if day in days:
                days[day].append(entry)
    # Ein Tag nur mit der Wochensuppe hat noch kein Tagesgericht.
    return {day: rows for day, rows in days.items() if any(row.get("category") != "Suppe" for row in rows)}


# ---------------------------------------------------------------------------
# Sorry Mama: Wochenkarte nur als Bild – Texterkennung mit zwei unabhängigen Lesungen
# ---------------------------------------------------------------------------

def find_sorrymama(raw, monday):
    """(Bildadresse) der Wochenkarte; prüft den auf der Seite genannten Zeitraum."""
    page = html_text(raw)
    period = re.search(r"Mittagskarte\s+(\d{1,2})\.(\d{1,2})\.?\s*[–-]\s*(\d{1,2})\.(\d{1,2})", page)
    if not period:
        raise ValueError("Sorry Mama: Zeitraum der Mittagskarte nicht gefunden")
    if (int(period.group(1)), int(period.group(2))) != (monday.day, monday.month):
        raise NotThisWeek(f"Sorry Mama zeigt die Woche ab {period.group(1)}.{period.group(2)}.")
    images = re.findall(r"https://www\.sorrymama\.at/wp-content/uploads/[^\"' ,<>]*Mittagskarte[^\"' ,<>]*\.(?:png|jpe?g)",
                        raw.decode("utf-8", "replace"), re.I)
    if not images:
        raise ValueError("Sorry Mama: Bild der Mittagskarte nicht gefunden")
    return images[0]


def ocr(image, scale=1):
    """Text eines Bildes (tesseract); `scale` vergrößert vorher für eine zweite, unabhängige Lesung."""
    import io
    from PIL import Image
    picture = Image.open(io.BytesIO(image)).convert("L")
    if scale != 1:
        picture = picture.resize((int(picture.width * scale), int(picture.height * scale)), Image.LANCZOS)
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        picture.save(handle.name)
        done = subprocess.run(["tesseract", handle.name, "-", "-l", "deu", "--psm", "6"],
                              capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise ValueError("Texterkennung fehlgeschlagen: " + done.stderr.strip()[:120])
    return done.stdout


def parse_sorrymama(text, monday):
    """Gerichte aus dem erkannten Text: die Zeilen 'Name … Preis' direkt unter dem Zeitraum."""
    rows = lines_of(text)
    stamp = re.compile(r"(\d{1,2})\.(\d{1,2})\.?\s*[-–]\s*(\d{1,2})\.(\d{1,2})")
    try:
        start = next(index for index, line in enumerate(rows) if stamp.search(line))
    except StopIteration:
        raise ValueError("Sorry Mama: Zeitraum im Bild nicht erkannt") from None
    period = stamp.search(rows[start])
    if (int(period.group(1)), int(period.group(2))) != (monday.day, monday.month):
        raise NotThisWeek("Sorry Mama: Bild zeigt eine andere Woche")
    entries = []
    for line in rows[start + 1:]:
        match = re.fullmatch(r"(.+?)\s+" + PRICE + r"\.?", line)
        if not match:
            if entries:
                break
            continue
        name = clean(re.sub(r"\s*[\]\[|]\s*", " | ", match.group(1)).replace(" - ", " – "))
        entries.append(dish(name, euro(match.group(2), match.group(3)),
                            category="Suppe" if re.match(r"Suppe\b", name) else ""))
    if len(entries) < 2:
        raise ValueError("Sorry Mama: Gerichte im Bild nicht sicher erkannt")
    return {day.isoformat(): [dict(row) for row in entries] for day in week_dates(monday)}


def read_sorrymama(image, monday, read=ocr):
    first, second = parse_sorrymama(read(image, 1), monday), parse_sorrymama(read(image, 2), monday)
    if first != second:
        raise ValueError("Sorry Mama: zwei Lesungen des Bildes stimmen nicht überein")
    return first


# ---------------------------------------------------------------------------
# Hayashi: feste Mittagskarte (Dienstag bis Freitag), an die Bilddatei gebunden
# ---------------------------------------------------------------------------

def hayashi_days(image, monday):
    if hashlib.sha256(image).hexdigest() != HAYASHI_SHA256:
        raise ValueError("Hayashi: Die Mittagskarte (Bild) wurde geändert – bitte neu abschreiben")
    rows = [dish(name, price, description=detail) for name, detail, price in HAYASHI_LUNCH]
    rows.append(dish("Alle Gerichte mit Reis und Misoshiru oder Salat", None, priceLabel=" "))
    return {(monday + timedelta(days=offset)).isoformat(): [dict(row) for row in rows] for offset in range(1, 5)}


def fingerprint(days):
    """Inhalt einer Karte unabhängig vom Datum (für Karten ohne Wochenangabe)."""
    content = [[row["name"] for row in rows] for _, rows in sorted(days.items())]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


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
    raw = get(DATA_URLS.get(identifier, url))
    if identifier == "imturm":
        return parse_imturm(html_text(raw), monday)
    if identifier == "hannibal":
        return parse_hannibal(html_text(raw), monday)
    if identifier == "lalina":
        return parse_lalina(html_text(raw), monday)
    if identifier == "ox":
        return parse_ox(html_text(raw), monday)
    if identifier == "goesser":
        days = {}
        for link in find_goesser_pdfs(raw):
            days.update(parse_goesser(pdf_text(get(link)), monday))
        if not days:
            raise NotThisWeek("Gösserbräu: Monatsplan enthält die gesuchte Woche nicht")
        return days
    if identifier == "huber":
        viewer = re.search(r"https?://www\.gasthaus-huber\.at/[^\"'&<> ]+\.pdf|https%3A%2F%2Fwww\.gasthaus-huber\.at[^\"'&<> ]+\.pdf",
                           raw.decode("utf-8", "replace"))
        if not viewer:
            raise NotThisWeek("Huber: keine Tageskarte verlinkt")
        from urllib.parse import unquote
        return parse_huber(pdf_text(get(unquote(viewer.group(0)))), monday)
    if identifier == "denns":
        return parse_denns(json.loads(raw.decode("utf-8")), monday)
    if identifier == "sorrymama":
        return read_sorrymama(get(find_sorrymama(raw, monday)), monday)
    if identifier == "hayashi":
        return hayashi_days(get(HAYASHI_IMAGE), monday)
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
    earlier = {row["id"]: row for row in (previous or {}).get("restaurants", [])}
    restaurants = []
    for base in RESTAURANTS:
        old = earlier.get(base["id"], {}) if same_week else {}
        days, state, message, marks = {}, "ok", "", {}
        try:
            days = check(fetch(base["id"], base["url"], monday, get), monday)
            if base["id"] in UNDATED:
                # Maßstab ist die Karte der Vorwoche: in derselben Woche die gemerkte, sonst die zuletzt gezeigte.
                record = (earlier.get(base["id"], {}).get("import") or {})
                stale = record.get("stale") if same_week else record.get("fingerprint")
                marks = {"fingerprint": fingerprint(days), **({"stale": stale} if stale else {})}
                if stale and stale == marks["fingerprint"]:
                    marks = {"stale": stale}
                    raise NotThisWeek(base["name"] + " zeigt noch die Karte der Vorwoche")
            if base["id"] in DAILY:
                days = {**{day: rows for day, rows in old.get("days", {}).items() if rows}, **days}
        except NotThisWeek as reason:
            state, message, days = "not_published", str(reason), old.get("days", {})
        except Exception as error:  # Abruf- oder Lesefehler: guten Stand derselben Woche behalten
            state, message, days = "error", f"{type(error).__name__}: {error}"[:240], old.get("days", {})
            marks = {key: value for key, value in (old.get("import") or {}).items() if key in ("fingerprint", "stale")}
        complete = {day.isoformat(): days.get(day.isoformat(), []) for day in week_dates(monday)}
        restaurants.append({**base, "days": complete, "import": {"state": state, "message": message, **marks}})
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
