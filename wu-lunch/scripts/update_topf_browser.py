#!/usr/bin/env python3
"""Use a real browser to retrieve all five dated Topf & Deckel weekly tabs.

This is a source acquisition layer, not AI. The legacy parser cannot see hidden
tabs because requests fetches only the default HTML. Do not invent missing days.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from update_menus import ROOT, topf_starters,topf_main_items,topf_combo_items,html_lines,quality_warnings,validate_meal_components

URL="https://topfdeckel.at/wochenmenu"
DAY_NAMES=("Montag","Dienstag","Mittwoch","Donnerstag","Freitag")
MONTHS={"jänner":1,"januar":1,"februar":2,"märz":3,"april":4,"mai":5,"juni":6,
        "juli":7,"august":8,"september":9,"oktober":10,"november":11,"dezember":12}
DATA=ROOT/"data"/"menus.json"
FRONTEND=ROOT/"data.js"
STATUS=ROOT/"status.json"

def verify_week(text,monday):
    m=re.search(r"(\d{1,2})\.\s*(Jänner|Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*[–-]\s*(\d{1,2})\.\s*(Jänner|Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*(\d{4})",text,re.I)
    if not m:raise ValueError("Topf-Browser: sichtbares Wochendatum fehlt")
    start=date(int(m.group(5)),MONTHS[m.group(2).casefold()],int(m.group(1)))
    end=date(int(m.group(5)),MONTHS[m.group(4).casefold()],int(m.group(3)))
    if start!=monday or end!=monday+timedelta(days=4):
        raise ValueError(f"Topf-Browser: Wochenquelle {start} bis {end} ist nicht aktuelle Woche {monday}")

def collect_week(monday):
    days={}
    hashes={}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page(locale="de-AT",viewport={"width":1360,"height":900})
            page.goto(URL,wait_until="domcontentloaded",timeout=60000)
            page.wait_for_timeout(1200)
            verify_week(page.locator("main").inner_text(),monday)
            for index,day in enumerate(DAY_NAMES):
                buttons=page.locator("button").filter(has_text=re.compile(r"^\s*"+day+r"\s*$",re.I))
                if buttons.count()!=1:
                    raise ValueError(f"Topf-Browser: {day}: erwartet genau einen sichtbaren Button, gefunden {buttons.count()}")
                button=buttons.first
                if not button.is_visible():
                    raise ValueError(f"Topf-Browser: {day}: Tages-Tab nicht sichtbar")
                button.click(timeout=5000)
                page.wait_for_timeout(350)
                html=page.locator("main").inner_html()
                lines=html_lines(html.encode("utf-8"))
                verify_week(" ".join(lines),monday)
                soups=topf_starters(lines)
                mains=topf_main_items(lines)
                if not soups or len(mains)<2:
                    raise ValueError(f"Topf-Browser: {day}: Suppen/Hauptgerichte fehlen")
                items=soups+mains+topf_combo_items()
                for x in soups+mains:
                    if x.get("price_small") is None or x.get("price_large") is None:
                        raise ValueError(f"Topf-Browser: {day}: Portionspreis fehlt")
                    if not x["price_small"]<x["price_large"]:
                        raise ValueError(f"Topf-Browser: {day}: Portionenpreise widersprüchlich")
                day_key=(monday+timedelta(days=index)).isoformat()
                digest=hashlib.sha256(html.encode("utf-8")).hexdigest()
                hashes[day_key]=digest
                for item in items:
                    item["source_url"]=URL
                    item["source_day"]=day_key
                    item["source_sha256"]=digest
                days[day_key]=items
                print(f"{day}: {len(soups)} Suppe(n), {len(mains)} Hauptgerichte, {len(items)} gesamt",flush=True)
            # Guard against 5 buttons selecting one identical default panel.
            fingerprints=[tuple(x["name"] for x in v if x["category"]=="Hauptgericht") for v in days.values()]
            if len(set(fingerprints))<4:
                raise ValueError("Topf-Browser: Tab-Wechsel nicht glaubwürdig, Gerichte mehrfach identisch")
        finally:
            browser.close()
    return days,hashes

def main():
    today=datetime.now(ZoneInfo("Europe/Vienna")).date()
    monday=today-timedelta(days=today.weekday())
    days,hashes=collect_week(monday)
    data=json.loads(DATA.read_text(encoding="utf-8"))
    if data.get("weekStart")!=monday.isoformat():
        raise ValueError("Topf-Browser: Datenbank-Woche stimmt nicht überein")
    r=next(x for x in data["restaurants"] if x["id"]=="topfdeckel")
    r["days"]=days
    r["status"]="verified"
    r["validFrom"]=monday.isoformat()
    r["validUntil"]=(monday+timedelta(days=4)).isoformat()
    r["browser_verified_at"]=datetime.now(ZoneInfo("Europe/Vienna")).isoformat(timespec="seconds")
    r["note"]="Alle fünf Wochentage über echte Browser-Tabs der offiziellen Wochenmenü-Seite geprüft."
    source=next(x for x in data["sources"] if x["id"]=="topfdeckel")
    source.update({"status":"verified","validFrom":r["validFrom"],"validUntil":r["validUntil"]})
    validate_meal_components(data)
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    FRONTEND.write_text("window.CAMPUS_LUNCH_DATA = "+json.dumps(data,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
    status=json.loads(STATUS.read_text(encoding="utf-8"))
    status["sources"]["topfdeckel"]={"state":"ok_browser","last_success":r["browser_verified_at"],
        "consecutive_failures":0,"day_sha256":hashes}
    warnings=quality_warnings(data,today)
    status["quality_warnings"]=warnings
    status["quality_warning_count"]=len(warnings)
    status["health"]="degraded" if warnings or status.get("problems") else "healthy"
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Topf week published locally:",json.dumps({k:len(v) for k,v in days.items()}))

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("::error::Topf browser import failed: "+str(error)[:240],file=sys.stderr)
        raise
