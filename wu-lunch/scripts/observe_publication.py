#!/usr/bin/env python3
"""Vierwöchige, ressourcenschonende Messung von Publikationsänderungen.

Nur Metadaten, normierte Inhaltshashes und Zeitpunkte werden gespeichert.
Ändert keine Menüdatei und ist unabhängig vom veröffentlichten Lunch-Frontend.
"""
from __future__ import annotations
import sys
import hashlib
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from update_menus import URLS, html_lines, period, safe_get

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "publication-observations.json"
TZ = ZoneInfo("Europe/Vienna")
UNTIL = date(2026, 12, 4)
SOURCES = {
    "mensa": URLS["mensa"],
    "campus": URLS["campus"],
    "glashaus": URLS["glashaus"],
    "baschly-veggie": URLS["baschly_veg"],
    "baschly-fleisch": URLS["baschly_meat"],
    "losteria": URLS["losteria"],
    "topfdeckel": URLS["topfdeckel"],
    "gruenehuette": URLS["gruenehuette"],
    "lia": URLS["lia"],
    "finn": "https://finn.wien/blogs/news/mittagsmenu",
    "karmafood": "https://karmafood.at/pages/wochenmenu-karma-food-wien",
    "omakueche": "https://www.xn--omakche-q2a.at/",
}
def read_state():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"started_at": None, "ends_after": UNTIL.isoformat(), "sources": {}}

def scheduled_names(now):
    # Cron steuert die Uhrzeit; verspätete Starts nicht als erfolgreichen Leerjob verwerfen.
    # Hauptmessfenster Freitag bis Dienstag; Mittwoch/Donnerstag nur Baschly.
    day = now.weekday()
    if now.date() >= UNTIL: return []
    if day in (4, 5, 6, 0, 1):
        return list(SOURCES)
    if day in (2, 3):
        return ["baschly-veggie", "baschly-fleisch"]
    return []

def normalize(raw, name):
    if raw.startswith(b"%PDF-"):
        # Rohhash ist bei PDF-Anbietern robuster als unzuverlässiges Tabellentextlayout.
        return hashlib.sha256(raw).hexdigest(), "pdf", None
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()
    content = " ".join(soup.stripped_strings)
    # Möglichst inhaltsbezogene Bereiche, nicht das wechselnde HTML-Layout prüfen.
    anchors = {
        "campus": ["Mittagsmenüs", "Montag"],
        "glashaus": ["Mittagsmenüs", "Montag"],
        "baschly-veggie": ["Angebot der Woche", "Das Angebot dieser Woche"],
        "baschly-fleisch": ["Angebot der Woche", "Das Angebot dieser Woche"],
        "losteria": ["Menu della Casa", "MENU DELLA CASA"],
        "topfdeckel": ["Was heute", "Main Dish"],
        "gruenehuette": ["TAGESTELLER / LUNCH SPECIAL"],
        "lia": ["Tagesmenü Lia Coffee am WU Campus"],
    }
    for anchor in anchors.get(name, []):
        idx=content.casefold().find(anchor.casefold())
        if idx>=0:
            content=content[idx:idx+12500]
            break
    content=" ".join(content.split())
    valid=period(content)
    hashval=hashlib.sha256(content.encode("utf-8")).hexdigest()
    return hashval, "html", ([valid[0].isoformat(), valid[1].isoformat()] if valid else None)

def check_mensa(url):
    first=safe_get(url, 12_000_000)
    if first.startswith(b"%PDF-"):return first
    soup=BeautifulSoup(first, "html.parser")
    candidates=[]
    for link in soup.find_all("a",href=True):
        href=link["href"]
        if "menuplan" in href.lower() or href.lower().split("?")[0].endswith(".pdf"):
            candidates.append(urljoin(url, href))
    for target in candidates[:6]:
        try:
            raw=safe_get(target,12_000_000)
            if raw.startswith(b"%PDF-"):return raw
        except Exception:
            continue
    raise RuntimeError("Mensa-PDF nicht erreichbar oder nicht verlinkt")

def main(now=None):
    now=now or datetime.now(TZ)
    state=read_state()
    state["started_at"]=state.get("started_at") or now.isoformat(timespec="seconds")
    state["ends_after"]=None if "--import-scan" in sys.argv else UNTIL.isoformat()
    names=list(SOURCES) if "--import-scan" in sys.argv else scheduled_names(now)
    if not names:
        print("Außerhalb des Messfensters – keine Abrufe.")
        return 0
    state.setdefault("sources", {})
    for name in names:
        entry=state["sources"].setdefault(name, {"observations":[],"changes":[]})
        try:
            raw=check_mensa(SOURCES[name]) if name=="mensa" else safe_get(SOURCES[name],12_000_000)
            digest,kind,valid=normalize(raw,name)
            if name=="finn":
                soup=BeautifulSoup(raw,"html.parser")
                images=[urljoin(SOURCES[name],img.get("src", "")) for img in (soup.select("article img") or soup.select("main img") or soup.find_all("img"))]
                image_hashes=[hashlib.sha256(safe_get(url,12_000_000)).hexdigest() for url in images[:3] if url.startswith("https://")]
                if image_hashes:digest=hashlib.sha256((digest+"".join(image_hashes)).encode()).hexdigest()
            observations=entry["observations"]
            previous=next((x for x in reversed(observations) if x.get("sha256")),None)
            changed=bool(previous and previous["sha256"]!=digest)
            sample={"at":now.isoformat(timespec="seconds"),"sha256":digest,
                    "format":kind,"validity":valid,"changed":changed,"source_url":SOURCES[name],"publication_time_confirmed":False}
            if changed:
                entry["changes"].append({"first_seen_at":sample["at"],
                    "previous_seen_at":previous["at"],"validity":valid})
            observations.append(sample)
            print(f"{name}: "+("ÄNDERUNG" if changed else "unverändert"))
        except Exception as exc:
            entry["observations"].append({"at":now.isoformat(timespec="seconds"),
                                           "error":str(exc)[:180]})
            print(f"{name}: Fehler: {str(exc)[:150]}")
        # 4 Wochen * max 4x * 5 Quellen: kurze, begrenzte Verlaufsliste.
        entry["observations"]=entry["observations"][-150:]
        entry["changes"]=entry["changes"][-50:]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
