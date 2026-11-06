#!/usr/bin/env python3
"""Publish independently extracted AI menus, only when independently validated.

Triggered only from an explicitly requested GitHub Action. Backups of existing
production menus remain available in Git history. No restaurant parser is used.
"""
import json
from datetime import date,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PILOT=ROOT/"ai-pilot"/"results"/"latest.json"
DATA=ROOT/"data"/"menus.json"
JS=ROOT/"data.js"
STATUS=ROOT/"status.json"

def publish():
    report=json.loads(PILOT.read_text(encoding="utf-8"))
    prod=json.loads(DATA.read_text(encoding="utf-8"))
    week=date.fromisoformat(report["week_start"])
    if prod.get("weekStart")!=week.isoformat():
        raise ValueError("KI-Woche und aktuelle Webseite haben unterschiedliche Wochen")
    updated=[]
    rejected=[]
    source_lookup={s["id"]:s for s in prod["sources"]}
    for ident,entry in report.get("restaurants",{}).items():
        model_data=entry.get("result") or {}
        rows=model_data.get("items") or []
        issues=entry.get("validation_issues",[])
        if entry.get("error") or issues or model_data.get("status")!="found" or not rows:
            rejected.append({"restaurant":ident,"reason":"KI-Ergebnis fehlend, fehlerhaft, unklar oder ohne Gerichte"})
            continue
        if any(item.get("confidence")!="high" for item in rows):
            rejected.append({"restaurant":ident,"reason":"Nicht alle KI-Gerichte haben hohe Konfidenz"})
            continue
        # No silent mixing of evidence from unapproved URLs.
        approved={s["url"] for s in entry.get("sources",[]) if s.get("fetched")}
        if any(item.get("source_url") not in approved or len(item.get("evidence_excerpt",""))<8 for item in rows):
            rejected.append({"restaurant":ident,"reason":"Originalquellenbeleg fehlt"})
            continue
        restaurant=next((r for r in prod["restaurants"] if r["id"]==ident),None)
        if not restaurant:
            rejected.append({"restaurant":ident,"reason":"Restaurant nicht vorhanden"})
            continue
        new_days={k:[] for k in restaurant["days"]}
        new_seasonal=[]
        try:
            for item in rows:
                amount=item.get("price_eur")
                if amount is not None and (not isinstance(amount,(int,float)) or amount<=0 or amount>150):
                    raise ValueError("Preis außerhalb der zulässigen Grenzen")
                date_str=item.get("date")
                if not date_str and ident!="losteria":
                    raise ValueError("Gericht ohne Tagesdatum")
                if date_str:
                    d=date.fromisoformat(date_str)
                    if d<week or d>week+timedelta(days=4):
                        raise ValueError("Gericht außerhalb der Kalenderwoche")
                new={
                    "name":item["name"].strip(),
                    "price":amount,
                    "category":item.get("category") or "Mittagsmenü",
                    "diet":"unknown",
                    "description":" | ".join(x for x in [
                        ("Portion: "+item["portion"]) if item.get("portion") else "",
                        ("Inklusive: "+", ".join(item.get("included_items",[]))) if item.get("included_items") else "",
                        ("Zusatzkosten: "+", ".join(item.get("extra_costs",[]))) if item.get("extra_costs") else "",
                    ] if x),
                    "allergens":[],
                    "included_soup":None,
                    "included_choices":[],
                    "source_url":item["source_url"],
                    "evidence_excerpt":item["evidence_excerpt"],
                    "ai_confidence":item["confidence"],
                }
                if date_str:new_days[date_str].append(new)
                else:new_seasonal.append(new)
            # Only replace touched days; never delete other valid days inadvertently.
            for day,items in new_days.items():
                if items:restaurant["days"][day]=items
            if ident=="losteria":
                if new_seasonal:restaurant["seasonal"]=new_seasonal
                else:raise ValueError("Saisonkarte ohne datumslose Positionen")
            restaurant["status"]="ai_verified"
            restaurant["note"]="Direkt-KI-Import aus Originalseiten; Originalbeleg je Gericht dokumentiert"
            source_lookup[ident]["status"]="ai_verified"
            restaurant["validFrom"]=source_lookup[ident]["validFrom"]=week.isoformat() if ident!="losteria" else None
            restaurant["validUntil"]=source_lookup[ident]["validUntil"]=(week+timedelta(days=4)).isoformat() if ident!="losteria" else None
            updated.append({"restaurant":ident,"items":len(rows)})
        except (KeyError,ValueError,TypeError) as err:
            rejected.append({"restaurant":ident,"reason":str(err)})
            continue
    if not updated:
        raise RuntimeError("Kein KI-Menü besteht die Publikationsprüfung – produktive Daten bleiben unverändert")
    # Keep comparison audit record.
    audit={"checked_at":report["checked_at"],"model":report["model"],"week_start":report["week_start"],"published":updated,"rejected":rejected}
    (ROOT/"ai-pilot"/"results"/"publication-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    prod["origin"]="KI-Direktanalyse aus verlinkten Restaurantquellen (kontrollierter Test)"
    prod["checkedAt"]=report["checked_at"]
    DATA.write_text(json.dumps(prod,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    JS.write_text("window.CAMPUS_LUNCH_DATA = "+json.dumps(prod,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
    # Keep conventional importer status untouched so it can still report its real errors.
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=="__main__":
    publish()
