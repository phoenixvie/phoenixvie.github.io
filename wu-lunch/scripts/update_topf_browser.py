#!/usr/bin/env python3
"""Use a real browser to retrieve all five dated Topf & Deckel weekly tabs.

This is a source acquisition layer, not AI. The legacy parser cannot see hidden
tabs because requests fetches only the default HTML. Do not invent missing days.
"""
from __future__ import annotations
import hashlib
import importlib.util
import os
import json
import re
import sys
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from source_archive import capture
from update_menus import ROOT, target_week_monday, topf_starters, topf_main_items, topf_desserts, topf_combo_items, html_lines, quality_warnings, validate_meal_components

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

def collect_week(monday, *, with_snapshots=False):
    days={}
    hashes={}
    snapshots={}
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
                capture(URL,page.content().encode('utf-8'),'topfdeckel',context=day)
                capture(URL,page.screenshot(full_page=True),'topfdeckel',kind='png',context=day)
                lines=html_lines(html.encode("utf-8"))
                verify_week(" ".join(lines),monday)
                starters=topf_starters(lines)
                mains=topf_main_items(lines)
                desserts=topf_desserts(lines)
                if (not starters or not any(x["category"]=="Suppe" for x in starters)
                        or len(mains)<2 or not desserts):
                    raise ValueError(f"Topf-Browser: {day}: Suppen/Salate/Nachspeisen/Hauptgerichte fehlen")
                items=starters+mains+desserts+topf_combo_items()
                for x in starters+mains:
                    if x.get("price_small") is None or x.get("price_large") is None:
                        raise ValueError(f"Topf-Browser: {day}: Portionspreis fehlt")
                    if not x["price_small"]<x["price_large"]:
                        raise ValueError(f"Topf-Browser: {day}: Portionenpreise widersprüchlich")
                day_key=(monday+timedelta(days=index)).isoformat()
                digest=hashlib.sha256(html.encode("utf-8")).hexdigest()
                hashes[day_key]=digest
                snapshots[day_key]=html
                for item in items:
                    item["source_url"]=URL
                    item["source_day"]=day_key
                    item["source_sha256"]=digest
                days[day_key]=items
                print(f"{day}: {len(starters)} Vorspeise(n), {len(mains)} Hauptgerichte, {len(items)} gesamt",flush=True)
            # Guard against 5 buttons selecting one identical default panel.
            fingerprints=[tuple(x["name"] for x in v if x["category"]=="Hauptgericht") for v in days.values()]
            if len(set(fingerprints))<4:
                raise ValueError("Topf-Browser: Tab-Wechsel nicht glaubwürdig, Gerichte mehrfach identisch")
        finally:
            browser.close()
    return (days,hashes,snapshots) if with_snapshots else (days,hashes)

def audit_with_luna(monday, days, hashes, snapshots, prior, key):
    """Check all five actual browser tabs using Luna, not static initial HTML.

    AI is a second reader: uncertain/missing menu rows are logged for
    investigation; it cannot silently overwrite proven browser tab prices.
    """
    digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    if prior.get("fingerprint")==digest and prior.get("model")=="gpt-6-luna":
        return prior
    if not key:
        return {"state":"skipped_no_key","fingerprint":digest,
                "note":"OPENAI_API_KEY fehlt"}
    spec=importlib.util.spec_from_file_location("topf_luna",ROOT/"ai-pilot"/"ai_direct.py")
    ai=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ai)
    content=[{"type":"input_text","text":(
        "Prüfe diese fünf browsergerenderten Tages-Tabs. Erfasse ALLE Suppen, "
        "Hauptgerichte, klein/groß-Preise und Menükombinationen. "
        "Die Tabdaten sind bereits auf die Woche verifiziert. "
        f"Quelle für jedes Item: {URL}. Keine kostenlosen Suppen erfinden. "
        f"Kalenderwoche: {monday.isoformat()} bis {(monday+timedelta(days=4)).isoformat()}. "
        "Melde Unklarheiten in warnings, nicht als erfundenen Inhalt.")}]
    for day,html in sorted(snapshots.items()):
        content.append({"type":"input_text","text":f"DATUM {day} (sichtbarer Browser-Tab):\\n{html[:45000]}"})
    result,usage=ai.call_model(key,"gpt-6-luna",[{"role":"user","content":content}])
    issues=ai.validate(result,[{"url":URL,"fetched":True}],monday,"topfdeckel")
    parser_names={day:{re.sub(r"\\W+"," ",x["name"].casefold()).strip() for x in items}
                  for day,items in days.items()}
    ai_names={day:set() for day in days}
    for item in result.get("items",[]):
        if item.get("date") in ai_names:
            ai_names[item["date"]].add(re.sub(r"\\W+"," ",item.get("name","").casefold()).strip())
    missing={}
    for day in days:
        if ai_names[day]:
            absent=[n for n in ai_names[day] if n not in parser_names[day]]
            if absent:
                missing[day]=absent[:5]
    return {"state":"review_needed" if issues or missing or result.get("warnings") else "ok",
            "model":"gpt-6-luna","fingerprint":digest,
            "checked_at":datetime.now(ZoneInfo("Europe/Vienna")).isoformat(timespec="seconds"),
            "validation_issues":issues[:5],"ai_only_examples":missing,
            "warnings":(result.get("warnings") or [])[:5],"usage":usage}


def main():
    today=datetime.now(ZoneInfo("Europe/Vienna")).date()
    monday=target_week_monday(today)
    days,hashes,snapshots=collect_week(monday,with_snapshots=True)
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
    try:
        status["topf_luna_audit"]=audit_with_luna(
            monday,days,hashes,snapshots,status.get("topf_luna_audit",{}),
            os.environ.get("OPENAI_API_KEY","").strip())
    except Exception as error:
        status["topf_luna_audit"]={"state":"error","note":str(error)[:220]}
        print("::warning::Topf Luna Kontrollanalyse nicht verfügbar:",str(error)[:180],flush=True)
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
