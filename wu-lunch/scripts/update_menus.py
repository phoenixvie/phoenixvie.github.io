#!/usr/bin/env python3
"""WU-Lunch: quellenbewusster, fehlertoleranter Wochen-Import für data.js.
Keine externen Zugangsdaten nötig. GitHub Actions führt das Skript aus.
"""
from __future__ import annotations
import argparse
from difflib import SequenceMatcher
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import fitz
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.js"
JSON_PATH = ROOT / "data" / "menus.json"
STATUS_PATH = ROOT / "status.json"
TZ = ZoneInfo("Europe/Vienna")
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag")
ALLOWED = {"shop.baschly.com", "www.wumensa.at", "wumensa.at", "www.dascampus.at",
           "dascampus.at", "www.dasglashaus.at", "dasglashaus.at", "losteria.net", "www.losteria.net"}
MONTHS = {"jan":1,"jänner":1,"feb":2,"mär":3,"maer":3,"apr":4,"mai":5,"jun":6,"jul":7,
          "aug":8,"sep":9,"okt":10,"nov":11,"dez":12}
URLS = {
    "mensa":"https://www.wumensa.at/menuplan-deutsch/",
    "campus":"https://www.dascampus.at/dc-mittagsmenues",
    "glashaus":"https://www.dasglashaus.at/menues",
    "baschly_veg":"https://shop.baschly.com/collections/lunch-special/products/lunch-special-veggie",
    "baschly_meat":"https://shop.baschly.com/collections/lunch-special/products/lunch-special-mit-fleisch",
    "losteria":"https://losteria.net/at/menue/menu-della-casa/",
}
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

def tidy(text):
    return re.sub(r"\s+", " ", str(text).replace("\xa0"," ").replace("¦"," | ")).strip(" \n\t•|-")

def euros(s):
    m = re.search(r"(?:€\s*)?(\d{1,3}[,.]\d{2})\s*€?", str(s))
    return float(m.group(1).replace(",", ".")) if m else None

def period(text):
    m = re.search(r"(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{2,4})\s*[-–—]\s*(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{2,4})", text)
    if m:
        a,b,y,c,d,z = map(int,m.groups())
        try:
            x=date(y if y>99 else y+2000,b,a); q=date(z if z>99 else z+2000,d,c)
            return (x,q) if 0 <= (q-x).days <= 14 else None
        except ValueError: pass
    m=re.search(r"(\d{1,2})\.\s*([a-zäöü]{3,})\.?\s*(\d{4})\s*[-–—]\s*(\d{1,2})\.\s*([a-zäöü]{3,})\.?\s*(\d{4})", text, re.I)
    if m:
        a,mo,y,b,mn,z=m.groups()
        try:
            x=date(int(y),MONTHS[mo.lower()[:3]],int(a))
            q=date(int(z),MONTHS[mn.lower()[:3]],int(b))
            return (x,q) if 0 <= (q-x).days <= 14 else None
        except (KeyError,ValueError): pass
    # Webseiten mit Jahreszahl nur am Ende: "03.08 bis 07.08.2026".
    m=re.search(r"(\d{1,2})\s*[./]\s*(\d{1,2})\s*(?:[-–—]|bis)\s*(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{4})",text,re.I)
    if m:
        a,b,d,e,y=map(int,m.groups())
        try:
            end=date(y,e,d); start=date(y-(1 if b>e else 0),b,a)
            return (start,end) if 0 <= (end-start).days <=14 else None
        except ValueError: pass
    # Monatsnamen mit nur einer Jahreszahl: "2. Nov - 6. Nov 2026".
    m=re.search(r"(\d{1,2})\.\s*([a-zäöü]{3,})\.?\s*(?:[-–—]|bis)\s*(\d{1,2})\.\s*([a-zäöü]{3,})\.?\s*(\d{4})",text,re.I)
    if m:
        a,ma,b,mb,y=m.groups()
        try:
            end=date(int(y),MONTHS[mb.lower()[:3]],int(b))
            start=date(int(y)-(1 if MONTHS[ma.lower()[:3]]>end.month else 0),MONTHS[ma.lower()[:3]],int(a))
            return (start,end) if 0 <= (end-start).days <=14 else None
        except (ValueError,KeyError): pass
    # Wix stellt die beiden Gültigkeitsdaten teils ohne sichtbaren Bindestrich dar.
    # Nur eng benachbarte Daten derselben Woche akzeptieren.
    dates=list(re.finditer(r"(\d{1,2})\.\s*([a-zäöü]{3,})\.?\s*(\d{4})",text,re.I))
    for i in range(len(dates)-1):
        a,b=dates[i],dates[i+1]
        if b.start()-a.end()>35:continue
        try:
            x=date(int(a.group(3)),MONTHS[a.group(2).lower()[:3]],int(a.group(1)))
            y=date(int(b.group(3)),MONTHS[b.group(2).lower()[:3]],int(b.group(1)))
            if 0 <= (y-x).days <=7:return x,y
        except (ValueError,KeyError):pass
    return None

def load_data():
    if JSON_PATH.exists():
        try: return json.loads(JSON_PATH.read_text(encoding="utf-8"))
        except (ValueError,OSError): pass
    s=DATA_PATH.read_text(encoding="utf-8").strip()
    prefix="window.CAMPUS_LUNCH_DATA ="
    if not s.startswith(prefix): raise ValueError("Unbekanntes data.js-Format; nicht überschreiben")
    return json.loads(s[len(prefix):].strip().rstrip(";"))

def load_status():
    try: return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError,ValueError): return {"sources":{}}

def safe_get(url, max_size=4_000_000):
    """Nur explizit erlaubte Hosts; Redirects, Größen, Timeouts und Versuche begrenzt."""
    session=requests.Session()
    session.headers.update({"User-Agent":"WU-Lunch-Menu-Indexer/1.1 (source-link: https://phoenixvie.github.io/wu-lunch/)",
                            "Accept":"application/pdf,text/html;q=0.9,*/*;q=0.1"})
    last_error=None
    for attempt in range(3):
        u=url
        try:
            for _ in range(4):
                p=urlparse(u)
                if p.scheme!="https" or p.hostname not in ALLOWED or p.port not in (None,443) or p.username:
                    raise ValueError("Unzulässiges Abrufziel")
                with session.get(u,timeout=(6,20),allow_redirects=False,stream=True) as r:
                    if r.is_redirect:
                        u=urljoin(u,r.headers.get("Location",""))
                        continue
                    r.raise_for_status()
                    body=bytearray()
                    for chunk in r.iter_content(chunk_size=65536):
                        body.extend(chunk)
                        if len(body)>max_size: raise ValueError("Datei über Größenlimit")
                    if not body: raise ValueError("Leere Antwort")
                    return bytes(body)
            raise ValueError("Zu viele Redirects")
        except (requests.RequestException, ValueError) as exc:
            last_error=exc
            if attempt<2: time.sleep(1+2*attempt)
    raise RuntimeError(f"Abruf fehlgeschlagen: {str(last_error)[:180]}")

def html_lines(raw):
    soup=BeautifulSoup(raw,"html.parser")
    for el in soup(["script","style","noscript","svg","footer","header","nav","template"]): el.decompose()
    return [t for v in soup.stripped_strings if (t:=tidy(v))]

def day_blocks(lines):
    out={}
    current=None
    for text in lines:
        normal=tidy(text).lower().rstrip(":")
        if normal in (x.lower() for x in WEEKDAYS):
            current=WEEKDAYS[[x.lower() for x in WEEKDAYS].index(normal)]
            out[current]=[]
        elif current is not None:
            out[current].append(text)
    return out

def weekday_dates(monday):
    return [(monday+timedelta(days=i),WEEKDAYS[i]) for i in range(5)]

def blank_days(monday):
    return {(monday+timedelta(days=i)).isoformat():[] for i in range(5)}

def make_item(name, price, category, diet="unknown", description="", allergens=None):
    return {"name":tidy(name),"price":price,"category":category,"diet":diet,
            "description":description,"allergens":allergens or []}

def parse_campus(raw,monday):
    lines=html_lines(raw)
    all_text="\n".join(lines)
    p=period(all_text)
    if not p or not (p[0]<=monday<=p[1]):
        raise ValueError(f"Campus: Plan nicht für KW {monday}: {p}")
    marker=next((i for i,s in enumerate(lines) if re.search("Mittagsmenüs",s,re.I)),0)
    blocks=day_blocks(lines[marker:])
    result=blank_days(monday)
    for d,name in weekday_dates(monday):
        if not p[0]<=d<=p[1]: continue
        picks=[]
        for ln in blocks.get(name,[]):
            lo=ln.lower()
            if lo in {"regulär","vegetarisch","vegan","fleisch","menü 1","menü 2"}:continue
            if re.fullmatch(r"[ACDEFGHLMNOPR,\s]{1,30}",ln,re.I):continue
            if len(ln)<17 or re.search(r"^([0-9., €]+|telefon|kontakt|öffnungszeiten)",lo):continue
            if ln not in picks:picks.append(ln)
        result[d.isoformat()]=[make_item(t,None,f"Menü {i+1}") for i,t in enumerate(picks[:2])]
    if sum(len(v) for v in result.values())<4:
        raise ValueError("Campus: zu wenige Speisen erkannt")
    return result,p

def parse_glashaus(raw,monday):
    lines=html_lines(raw); whole="\n".join(lines)
    p=period(whole)
    if not p or not (p[0]<=monday<=p[1]):
        raise ValueError(f"Glashaus: Plan nicht für KW {monday}: {p}; Textanfang: {whole[:230]!r}")
    blocks=day_blocks(lines)
    mt=re.search(r"Vegetarisch\s*€\s*(\d+[,\.]\d{2}).*?Fisch\s*&\s*Fleisch\s*€\s*(\d+[,\.]\d{2})",whole,re.I|re.S)
    costs=[float(c.replace(",",".")) for c in mt.groups()] if mt else [None,None]
    result=blank_days(monday)
    for d,name in weekday_dates(monday):
        if not p[0]<=d<=p[1]:continue
        picks=[]
        for ln in blocks.get(name,[]):
            if tidy(ln).lower() in {"feiertag","regulär","vegan","vegetarisch"}:continue
            if re.fullmatch(r"[ACDEFGHLMNOPR,\s]{1,30}",ln,re.I):continue
            if len(ln)<8:continue
            if ln not in picks:picks.append(ln)
        result[d.isoformat()]=[
            make_item(t,costs[i],"Vegetarisch" if i==0 else "Fisch / Fleisch",
                      "veggie" if i==0 else "meat", "Mit Suppe oder Salat") for i,t in enumerate(picks[:2])
        ]
    if sum(len(v) for v in result.values())<6:
        raise ValueError("Glashaus: zu wenige Speisen erkannt")
    return result,p

def parse_baschly(raw,monday,meat=False):
    """Auch neue Produktseiten mit 'Tagessuppe:' und 'Hauptgericht:' korrekt lesen."""
    lines=html_lines(raw); txt="\n".join(lines)
    m=re.search(r"(?:Das\s+)?Angebot (?:dieser|der) Woche",txt,re.I)
    if not m: raise ValueError("Baschly: Wochenabschnitt fehlt – möglicherweise Seitendesign geändert")
    blocks=day_blocks(txt[m.end():].splitlines())
    result=blank_days(monday)
    # Shopify-Header können mehrere Tausend Zeichen lang sein. Nicht nur den Anfang prüfen.
    cost=euros(txt)
    if cost is None: raise ValueError("Baschly: Produktpreis fehlt")
    for d,w in weekday_dates(monday):
        options=[]
        for raw_line in blocks.get(w,[]):
            line=tidy(raw_line)
            if re.search(r"^(beilage|mit kleinem salat|mit suppe|take away|in den warenkorb|ändern|zum hier)",line,re.I):
                break
            if re.fullmatch(r"[ACDEFGHLMNOPR,\s]{1,35}",line,re.I):continue
            if line.lower().startswith("tagessuppe:"):continue
            if line.lower().startswith("hauptgericht:"):
                line=tidy(line.split(":",1)[1])
                if line:options.insert(0,line)
            elif len(line)>=12 and not line.lower().startswith(("täglich neue suppe","glutenfrei","vegan")):
                options.append(line)
        if options:
            result[d.isoformat()]=[make_item(options[0],cost,"Fleisch" if meat else "Veggie",
                                             "meat" if meat else "veggie","Mit Tagessuppe oder kleinem Salat")]
    if sum(len(v) for v in result.values())<4: raise ValueError("Baschly: weniger als vier Wochentage")
    return result

def pdf_lines(page):
    lines=[]
    for b in page.get_text("dict")["blocks"]:
        if b.get("type")!=0:continue
        for line in b.get("lines",[]):
            spans=line.get("spans",[])
            if spans:
                x=min(s["bbox"][0] for s in spans); y=min(s["bbox"][1] for s in spans)
                lines.append((x,y,tidy(" ".join(s["text"] for s in spans))))
    return sorted(lines,key=lambda v:(v[1],v[0]))

def parse_mensa(raw,monday):
    if not raw.startswith(b"%PDF-"): raise ValueError("Mensa: PDF nicht gefunden")
    if len(raw)>12_000_000: raise ValueError("Mensa-PDF zu groß")
    result=blank_days(monday)
    with fitz.open(stream=raw,filetype="pdf") as doc:
        if not 1<=len(doc)<=4: raise ValueError("Mensa: unerwartete Seitenanzahl")
        text="\n".join(p.get_text("text") for p in doc)
        p=period(text)
        if p is None:
            # PDF-Schriftarten können das Startdatum als "02..2026" extrahieren.
            # Fallback nur, wenn Kalenderwoche UND vollständig lesbares Enddatum passen.
            kw=re.search(r"(?:SPEISEPLAN|MENÜPLAN)?\s*KW\s*(\d{1,2})",text,re.I)
            ends=re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b",text)
            if kw and int(kw.group(1))==monday.isocalendar().week:
                for dd,mm,yyyy in ends[:6]:
                    try:
                        end=date(int(yyyy),int(mm),int(dd))
                        if end in (monday+timedelta(days=4), monday+timedelta(days=3)):
                            p=(monday,end)
                            break
                    except ValueError:pass
        if p is None or p[0]!=monday or p[1] not in (monday+timedelta(days=4),monday+timedelta(days=3)):
            raise ValueError(f"Mensa: PDF ist nicht aus aktueller Woche: {p}; Textlänge={len(text)}, Textanfang={text[:165]!r}")
        cats=[("Tagessuppe",r"^Tagess?uppe$"),
              ("Powered by plants / Veggie",r"^Powered by plants|^100% plant based|^Veggie$"),
              ("Meaty",r"^Meaty$"),("Global & Grill",r"^Global\s*&\s*Grill$"),
              ("Soup Deal",r"^Soup Deal$"),("Pizza",r"^Pizza\s*&\s*Co$"),
              ("Bowls",r"^Bowls\s*&\s*Co$"),("Pasta",r"^Pasta\s*&\s*Co$")]
        for page in doc:
            rows=pdf_lines(page)
            headers=[]
            for b in page.get_text("dict")["blocks"]:
                if b.get("type")!=0:continue
                for line in b.get("lines",[]):
                    spans=line.get("spans",[])
                    label=tidy(" ".join(s["text"] for s in spans))
                    if not spans or label.upper() not in (w.upper() for w in WEEKDAYS):continue
                    left=min(s["bbox"][0] for s in spans)
                    right=max(s["bbox"][2] for s in spans)
                    cy=min(s["bbox"][1] for s in spans)
                    headers.append(((left+right)/2,cy,label))
            # Tabellenspalten sind um die Mitte der Überschrift zentriert.
            # Am linken Textrand zu schneiden vermischt die Nachbarspalten.
            headers.sort(key=lambda v:v[0])
            if len(headers)<5:continue
            unique=[]
            for h in headers:
                if not any(abs(h[0]-k[0])<8 for k in unique):unique.append(h)
            headers=unique[:5]
            if len(headers)<5:continue
            centers=[v[0] for v in headers]
            boundary=[]
            for x,y,t in rows:
                if x >= centers[0]-(centers[1]-centers[0])/2:continue
                for label,pat in cats:
                    if re.search(pat,t,re.I) and not any(v[1]==label for v in boundary):
                        boundary.append((y,label))
            boundary.sort()
            if not boundary:continue
            for d,w in weekday_dates(monday):
                matching=next((i for i,entry in enumerate(headers) if entry[2].upper()==w.upper()),None)
                if matching is None:continue
                left=(centers[matching-1]+centers[matching])/2 if matching else max(0,centers[0]-(centers[1]-centers[0])/2)
                right=(centers[matching]+centers[matching+1])/2 if matching<4 else min(page.rect.width,centers[4]+(centers[4]-centers[3])/2)
                for j,(sy,label) in enumerate(boundary):
                    if label not in {"Tagessuppe","Powered by plants / Veggie","Meaty","Global & Grill"}:continue
                    bottom=boundary[j+1][0] if j+1<len(boundary) else page.rect.height
                    if bottom<=sy+4:continue
                    content=page.get_text("text",clip=fitz.Rect(left,sy+2,right-1,bottom-1),sort=True)
                    cost=euros(content)
                    names=[]
                    for line in content.splitlines():
                        line=tidy(line)
                        if re.fullmatch(r"[ACDEFGHLMNOPR,\s]{1,35}",line,re.I):continue
                        line=re.sub(r"€\s*\d{1,3}[,.]\d{2}|\d{1,3}[,.]\d{2}\s*€?","",line)
                        line=tidy(line)
                        if line and line.lower() not in {"xxx","-","laut tagesaushang"}:names.append(line)
                    title=tidy(" ".join(names))
                    if len(title)<8 or len(title)>180:continue
                    diet="veggie" if label=="Powered by plants / Veggie" else "meat" if label=="Meaty" else "unknown"
                    result[d.isoformat()].append(make_item(title,cost,label,diet))
    # Qualitäts-Gate: PDF-Zell-Schnittfehler erzeugen abgeschnittene Namen
    # ("esuppe", "tter Chicken") – niemals ungeprüft als Menü veröffentlichen.
    for day_items in result.values():
        for item in day_items:
            title=item["name"]
            if not title or not title[0].isupper() or len(title)>160:
                raise ValueError(f"Mensa: verstümmelter Tabellenzelltext erkannt ({title[:55]!r})")
            if item["category"]=="Tagessuppe" and "suppe" not in title.casefold():
                raise ValueError(f"Mensa: verdächtige Suppe ({title[:55]!r})")
    coverage=sum(1 for v in result.values() if sum(x["category"]=="Meaty" for x in v)>0)
    if coverage<3: raise ValueError(f"Mensa: nur {coverage}/5 Tage Meaty erkannt; PDF-Tabelle prüfen")
    if sum(len(v) for v in result.values())<10:raise ValueError("Mensa: PDF-Extraktion unvollständig")
    return result,p

def parse_losteria(raw):
    soup=BeautifulSoup(raw,"html.parser")
    for bad in soup(["script","style","nav","footer","header"]):bad.decompose()
    items=[]
    for h in soup.find_all(["h2","h3"]):
        heading=tidy(h.get_text(" ",strip=True))
        if len(heading)<9 or not heading.isupper() or heading.lower() in {"menu della casa"}:continue
        paragraphs=[]
        for node in h.next_elements:
            if getattr(node,"name",None) in ("h1","h2","h3"):break
            if isinstance(node,str):
                s=tidy(node)
                if s:paragraphs.append(s)
            if len(" ".join(paragraphs))>450:break
        desc=tidy(" ".join(paragraphs)); cost=euros(desc)
        if cost is not None and len(desc)<450:
            items.append(make_item(heading,cost,"Saisonkarte","unknown",desc[:180]))
        if len(items)>=12:break
    if len(items)<2:raise ValueError("L'Osteria: Saisonkarte nicht lesbar")
    return items

def restaurant(data,identifier):
    return next(v for v in data["restaurants"] if v["id"]==identifier)

def source(data,identifier):
    return next(v for v in data["sources"] if v["id"]==identifier)

def weekly_cache_valid(data,identifier,monday):
    r=restaurant(data,identifier)
    if r.get("status") not in ("verified","current"):return False
    if data.get("weekStart")!=monday.isoformat():return False
    if r.get("validFrom") and not (r["validFrom"]<=monday.isoformat()<=r.get("validUntil","")):return False
    return sum(len(v) for v in r.get("days",{}).values())>= (10 if identifier=="mensa" else 6)

def compare_verified_week(old_days,new_days):
    """Schützt bereits überprüfte Wochenmenüs vor grob falsch gelesenen PDF-Spalten."""
    ratios=[]
    for day,items in new_days.items():
        previously={x.get("category"):x.get("name","") for x in old_days.get(day,[])}
        for x in items:
            name=previously.get(x["category"])
            if name:
                a=re.sub(r"\W+","",name.casefold())
                b=re.sub(r"\W+","",x["name"].casefold())
                ratios.append(SequenceMatcher(None,a,b,autojunk=False).ratio())
    if len(ratios)>=8 and sum(v<0.34 for v in ratios)>len(ratios)*0.35:
        raise ValueError("Mensa: PDF-Zellzuordnung widerspricht vorhandenen, überprüften Tagesgerichten")
    
def apply_result(data,identifier,days,status,validity=None):
    r=restaurant(data,identifier); s=source(data,identifier)
    r["days"]=days; r["status"]=status
    s["status"]=status
    if validity:
        r["validFrom"]=s["validFrom"]=validity[0].isoformat()
        r["validUntil"]=s["validUntil"]=validity[1].isoformat()
    else:
        r["validFrom"]=s["validFrom"]=None
        r["validUntil"]=s["validUntil"]=None

def reset_week(data,monday):
    if data.get("weekStart")==monday.isoformat():return
    data["weekStart"]=monday.isoformat()
    data["weekEnd"]=(monday+timedelta(days=4)).isoformat()
    for r in data["restaurants"]:
        r["days"]=blank_days(monday)
        if r["id"]!="losteria":
            r["status"]="empty";r["validFrom"]=r["validUntil"]=None
    for s in data["sources"]:
        if s["id"]!="losteria":
            s["status"]="empty";s["validFrom"]=s["validUntil"]=None

def run(today):
    now=datetime.now(TZ).isoformat(timespec="seconds")
    monday=today-timedelta(days=today.weekday())
    data=load_data()
    state=load_status()
    old_week=data.get("weekStart")
    reset_week(data,monday)
    problems=[]
    operations={}
    previous=state.get("sources",{})
    for ident in ("mensa","glashaus","campus","baschly","losteria"):
        meta=previous.get(ident,{})
        prev_success=meta.get("last_success")
        should_check=True
        if today.weekday()>=5:
            should_check=False
        elif ident in ("mensa","glashaus") and weekly_cache_valid(data,ident,monday) and prev_success and prev_success[:10]>=monday.isoformat():
            should_check=False
        elif ident=="losteria" and restaurant(data,ident).get("seasonal") and prev_success:
            try:should_check=(today-date.fromisoformat(prev_success[:10])).days>=14
            except ValueError:pass
        if not should_check:
            operations[ident]={"state":"cached","last_success":prev_success,
                               "consecutive_failures":meta.get("consecutive_failures",0)}
            continue
        try:
            if ident=="mensa":
                # Stale WordPress-PDFs können trotz HTTP 200 geliefert werden:
                # Direktlink, Cache-Busting und offizielle Homepage-Links probieren.
                candidates=[URLS["mensa"], URLS["mensa"]+"?week="+monday.isoformat()]
                try:
                    homepage=safe_get("https://www.wumensa.at/")
                    soup=BeautifulSoup(homepage,"html.parser")
                    for a in soup.find_all("a",href=True):
                        href=a.get("href","")
                        if "menuplan-deutsch" in href or href.lower().endswith(".pdf"):
                            candidates.append(urljoin("https://www.wumensa.at/",href))
                except Exception as discovery_error:
                    logging.info("Mensa PDF-Link-Discovery nicht verfügbar: %s",discovery_error)
                errors=[]
                parsed=None
                for candidate in list(dict.fromkeys(candidates))[:8]:
                    try:
                        raw=safe_get(candidate,12_000_000)
                        parsed=parse_mensa(raw,monday)
                        break
                    except (ValueError,RuntimeError,requests.RequestException) as exc:
                        errors.append(str(exc)[:130])
                if parsed is None:
                    raise ValueError("Mensa: aktuelle PDF-Woche nicht verifizierbar: "+" | ".join(errors[:3]))
                days,validity=parsed
                if data.get("weekStart")==monday.isoformat():
                    compare_verified_week(restaurant(data,"mensa").get("days",{}),days)
                apply_result(data,"mensa",days,"verified",validity)
            elif ident=="glashaus":
                days,validity=parse_glashaus(safe_get(URLS["glashaus"]),monday)
                apply_result(data,"glashaus",days,"verified",validity)
            elif ident=="campus":
                days,validity=parse_campus(safe_get(URLS["campus"]),monday)
                apply_result(data,"campus",days,"verified",validity)
            elif ident=="baschly":
                veg=parse_baschly(safe_get(URLS["baschly_veg"]),monday)
                meat=parse_baschly(safe_get(URLS["baschly_meat"]),monday,True)
                days={d:veg[d]+meat[d] for d in veg}
                apply_result(data,"baschly",days,"undated")
            else:
                items=parse_losteria(safe_get(URLS["losteria"]))
                restaurant(data,"losteria")["seasonal"]=items
                restaurant(data,"losteria")["status"]="seasonal"
                source(data,"losteria")["status"]="seasonal"
            operations[ident]={"state":"ok","last_success":now,"consecutive_failures":0}
        except Exception as exc:
            desc=f"{type(exc).__name__}: {str(exc)[:220]}"
            failures=meta.get("consecutive_failures",0)+1
            operations[ident]={"state":"error","error":desc,"last_success":prev_success,
                               "consecutive_failures":failures}
            problems.append(f"{ident}: {desc}")
            # Nie alten Wochenplan als neuen Plan ausgeben. Gültige Daten derselben Woche erhalten.
            r=restaurant(data,ident)
            if ident!="losteria" and sum(len(v) for v in r.get("days",{}).values())==0:
                r["status"]="empty";source(data,ident)["status"]="empty"
            logging.warning("%s",problems[-1])
    data["checkedAt"]=now
    status={
        "checked_at":now,
        "week_start":monday.isoformat(),
        "week_end":(monday+timedelta(days=4)).isoformat(),
        "health":"healthy" if not problems else ("failed" if len(problems)==5 else "degraded"),
        "sources":operations,
        "problems":problems,
        "next_run":"next business day ~08:15 Europe/Vienna",
        "format_version":1,
    }
    JSON_PATH.parent.mkdir(parents=True,exist_ok=True)
    JSON_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    DATA_PATH.write_text("window.CAMPUS_LUNCH_DATA = "+json.dumps(data,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
    STATUS_PATH.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"week":monday.isoformat(),"health":status["health"],
                      "operations":{k:v["state"] for k,v in operations.items()},
                      "problems":problems},ensure_ascii=False))
    return 2 if status["health"]=="failed" else 0

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",help="Europe/Vienna YYYY-MM-DD")
    parser.add_argument("--smoke-test",action="store_true",help="Statische Parser/Schema-Checks ohne Internet")
    args=parser.parse_args()
    if args.smoke_test:
        assert period("02.11.2026 - 06.11.2026")== (date(2026,11,2),date(2026,11,6))
        assert period("02. Nov. 2026 - 06. Nov. 2026")== (date(2026,11,2),date(2026,11,6))
        assert period("13.07.2026 - 17.07.2026") != (date(2026,11,2),date(2026,11,6))
        d=load_data()
        assert len(d["restaurants"])==5 and len(d["sources"])==5
        assert {x["id"] for x in d["restaurants"]}=={"mensa","campus","glashaus","baschly","losteria"}
        assert all(x.get("days") for x in d["restaurants"])
        print("Smoke tests OK")
        return 0
    today=date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    return run(today)

if __name__=="__main__":
    sys.exit(main())
