#!/usr/bin/env python3
"""Investigate dynamically rendered weekly menu day tabs, without publishing."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

OUT=Path("wu-lunch/ai-pilot/diagnostics/topf-tabs.json")
DAYS=("Montag","Dienstag","Mittwoch","Donnerstag","Freitag")
def main():
    result={"url":"https://topfdeckel.at/wochenmenu","days":{},"controls":[],"errors":[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(locale="de-AT",viewport={"width":1360,"height":900})
        page.goto(result["url"],wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(1600)
        result["title"]=page.title()
        result["heading"]=page.locator("h1").all_text_contents()
        for selector in ("button","[role=tab]","a","[data-day]","[data-date]"):
            try:
                for node in page.locator(selector).all()[:100]:
                    if not node.is_visible():continue
                    label=(node.inner_text(timeout=1000) or "").strip()
                    if label:
                        result["controls"].append({"type":selector,"label":label[:95],
                            "outer":node.evaluate("(el)=>el.outerHTML.slice(0,400)")})
            except Exception as e:
                result["errors"].append(f"controls {selector}: {str(e)[:120]}")
        for day in DAYS:
            record={"click":False,"content":"","error":None}
            targets=[]
            for selector in ("button","[role=tab]","a","[data-day]","[data-date]"):
                try:
                    nodes=page.locator(selector).filter(has_text=re.compile(day,re.I))
                    for i in range(min(5,nodes.count())):
                        x=nodes.nth(i)
                        if x.is_visible():targets.append(x)
                except Exception:
                    pass
            if targets:
                try:
                    targets[0].click(timeout=2500)
                    page.wait_for_timeout(600)
                    record["click"]=True
                except (PWTimeout,Exception) as exc:
                    record["error"]=str(exc)[:220]
            node=page.locator("main")
            record["content"]=(node.inner_text() if node.count() else page.locator("body").inner_text())[:12500]
            record["controls_found"]=len(targets)
            result["days"][day]=record
        browser.close()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Found controls:",len(result["controls"]))
    for day,x in result["days"].items():
        print(day,"clicked:",x["click"],"text_length:",len(x["content"]),
              "full_text:",repr(x["content"]))
if __name__=="__main__":main()
