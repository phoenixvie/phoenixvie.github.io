#!/usr/bin/env python3
"""Leseübung: Die allgemeinen Leser üben an Wochenkarten von Lokalen, die WU Food gar nicht zeigt.

Wozu: Jedes gelistete Lokal hat einen eigenen Leser. Ändert es die Form seiner Karte, springen zwei allgemeine
Leser ein (update_wels.generic_week – der Ersatzleser, reine Regeln – und update_wels.ai_week – der KI-Leser).
Je mehr Kartenformen diese beiden schon einmal richtig gelesen haben, desto seltener bleibt ein Lokal leer.
Dieses Programm besorgt die Übung dafür:

  1. Es holt einmal pro Woche die Karten der Übungslokale (practice/sources.json – nur deren eigene Webseiten).
  2. Beide Leser lesen dieselbe Karte unabhängig voneinander. Der KI-Leser dient als Vergleichslesung: Er darf
     nur übernehmen, was wörtlich in der Karte steht.
  3. Der Vergleich ergibt je Karte ein Urteil (einig, mehr gelesen, nur KI, uneinig, …). Karte, beide Ergebnisse und Urteil
     werden abgelegt (practice/cards, practice/results) – das ist die Übungssammlung.
  4. Die Punktetafel (practice/scoreboard.json) zeigt Woche für Woche, wie viele Karten der Ersatzleser allein
     richtig liest. Sie wird über ALLE gespeicherten Karten neu berechnet (--rescore): Nach einer Verbesserung
     des Ersatzlesers sieht man sofort, ob er mehr Karten schafft – und ob er keine verlernt hat.

Geprüfte Fälle (practice/expected/<lokal>-<montag>.json) sind feste Tests: test_practice.py verlangt, dass der
Ersatzleser sie genau so liest. So geht nichts wieder verloren, was einmal gelernt wurde.

Angezeigt wird davon nichts: Die Übungslokale erscheinen weder auf der Webseite noch in der App.
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import update_wels as wels

ROOT = Path(__file__).resolve().parents[1] / "practice"
SOURCES, CARDS, RESULTS, EXPECTED = ROOT / "sources.json", ROOT / "cards", ROOT / "results", ROOT / "expected"
SCOREBOARD = ROOT / "scoreboard.json"
KEEP_WEEKS = 12          # so viele Wochen bleiben Karten ohne geprüftes Soll liegen
MAX_CARD = 30_000        # Zeichen je gespeicherter Karte
VERDICTS = ("einig", "mehr_gelesen", "nur_ki", "nur_ersatzleser", "uneinig", "beide_gescheitert", "andere_woche", "abruf_fehlgeschlagen")


# ---------------------------------------------------------------------------
# Karte holen
# ---------------------------------------------------------------------------

def card_text(source, get=wels.http_get, monday=None):
    """Sichtbarer Text der Karte eines Übungslokals (HTML-Seite, PDF oder PDF, das auf der Seite verlinkt ist)."""
    raw = get(source["url"])
    kind = source.get("kind", "html")
    if kind == "pdf-link":
        hint = source.get("pdf_link_hint") or r"\.pdf"
        links = re.findall(r"""href=["']([^"']+)["']""", raw.decode("utf-8", "replace"))
        found = [link for link in links if re.search(hint, link, re.I) and ".pdf" in link.lower()]
        if not found:
            raise ValueError("kein PDF-Link auf der Seite gefunden")
        # Manche Seiten verlinken schon die nächste Woche zuerst: die Datei mit der gesuchten Kalenderwoche hat Vorrang.
        number = monday.isocalendar().week if monday else None
        this_week = [link for link in found if number and re.search(rf"KW\D{{0,3}}0?{number}(?!\d)", link, re.I)]
        raw, kind = get(urljoin(source["url"], (this_week or found)[0])), "pdf"
    if kind == "pdf" or raw[:5] == b"%PDF-":
        return wels.pdf_text(raw)
    return wels.html_text(raw)


def excerpt(text):
    """Nur die Kartenstelle: von kurz vor dem ersten bis kurz nach dem letzten Wochentag.

    Gespeichert wird bewusst nicht die ganze Seite (Impressum, Kontaktdaten, …), sondern das, woran geübt wird.
    Findet sich kein Wochentag, bleibt der Anfang der Seite – dann ist genau das der Übungsfall.
    """
    rows = wels.lines_of(text)
    marks = [index for index, line in enumerate(rows) if wels._day_heading(line)]
    if marks:
        rows = rows[max(0, marks[0] - 15):marks[-1] + 40]
    return "\n".join(rows)[:MAX_CARD]


# ---------------------------------------------------------------------------
# Lesen und vergleichen
# ---------------------------------------------------------------------------

def read_with(reader, *args):
    """Ein Leser, ein Ergebnis: {"ok", "days" | "error", "other_week"} – wirft nie."""
    try:
        days = wels.check(reader(*args), args[1])
        return {"ok": True, "days": days}
    except wels.NotThisWeek as error:
        return {"ok": False, "other_week": True, "error": str(error)[:200]}
    except Exception as error:  # jede Art zu scheitern ist ein Übungsergebnis, kein Programmfehler
        return {"ok": False, "other_week": False, "error": f"{type(error).__name__}: {error}"[:200]}


def agreement(first, second):
    """Anteil der Gerichte, die beide Leser am selben Tag gleich nennen (0 … 1), dazu die Unterschiede."""
    return wels.readings_agree(first, second)


def judge(generic, ai):
    """Urteil über eine Karte. ai=None: keine Vergleichslesung vorhanden (kein Schlüssel)."""
    if ai is None:
        if generic["ok"]:
            return "nur_ersatzleser", None
        return ("andere_woche" if generic.get("other_week") else "beide_gescheitert"), None
    if generic["ok"] and ai["ok"]:
        score, only_generic, only_ai = agreement(generic["days"], ai["days"])
        detail = {"agreement": score, "only_generic": only_generic, "only_ai": only_ai}
        if score >= 0.85:
            return "einig", detail
        # Alles, was die Vergleichslesung nennt, steht am selben Tag auch beim Ersatzleser – er hat nur mehr gelesen
        # (Vorspeise, Wochengericht). Das ist keine Abweichung in der Sache, aber einen Blick wert.
        return ("mehr_gelesen" if not only_ai else "uneinig"), detail
    if ai["ok"]:
        return "nur_ki", None
    if generic["ok"]:
        # Der KI-Leser prüft den Wochenbeleg streng. Sagt er "andere Woche", hat der Ersatzleser womöglich
        # eine alte Karte durchgelassen – das ist der wichtigste Fall überhaupt und zählt als uneinig.
        return ("uneinig" if ai.get("other_week") else "nur_ersatzleser"), None
    return ("andere_woche" if generic.get("other_week") or ai.get("other_week") else "beide_gescheitert"), None


def practise(source, monday, text, ai_key="", ai_post=None, stored_ai=None):
    generic = read_with(wels.generic_week, text, monday)
    ai = stored_ai
    if ai is None and ai_key:
        ai = read_with(wels.ai_week, text, monday, ai_key, ai_post)
    verdict, detail = judge(generic, ai)
    return {"id": source["id"], "week": monday.isoformat(), "verdict": verdict, "detail": detail,
            "generic": generic, "ai": ai}


# ---------------------------------------------------------------------------
# Ablage und Punktetafel
# ---------------------------------------------------------------------------

def _dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def stored_cards():
    """Alle gespeicherten Karten: (Lokal, Montag, Text)."""
    for path in sorted(CARDS.glob("*/*.txt")):
        yield path.parent.name, date.fromisoformat(path.stem), path.read_text(encoding="utf-8")


def expected_cases():
    """Geprüfte Fälle: (Lokal, Montag, Kartentext, Soll-Tage)."""
    for path in sorted(EXPECTED.glob("*.json")):
        case = _load(path, None)
        card = CARDS / case["id"] / (case["week"] + ".txt") if case else None
        if case and card.exists():
            yield case["id"], date.fromisoformat(case["week"]), card.read_text(encoding="utf-8"), case["days"]


def scoreboard(results):
    """Je Woche: wie viele Karten, welches Urteil, und der Anteil, den der Ersatzleser allein richtig las."""
    weeks = {}
    for row in results:
        week = weeks.setdefault(row["week"], {name: 0 for name in VERDICTS})
        week[row["verdict"]] += 1
    out = []
    for week, counts in sorted(weeks.items()):
        readable = sum(counts[name] for name in ("einig", "mehr_gelesen", "nur_ki", "nur_ersatzleser", "uneinig", "beide_gescheitert"))
        solved = counts["einig"] + counts["mehr_gelesen"] + counts["nur_ersatzleser"]
        out.append({"week": week, "cards": readable, "generic_solved": solved,
                    "generic_rate": round(solved / readable, 3) if readable else None, **counts})
    return out


def prune(today):
    """Alte Karten ohne geprüftes Soll entfernen – die Sammlung soll nützlich bleiben, nicht nur wachsen."""
    kept = {(case[0], case[1].isoformat()) for case in expected_cases()}
    for path in sorted(CARDS.glob("*/*.txt")):
        age = (today - date.fromisoformat(path.stem)).days
        if age > KEEP_WEEKS * 7 and (path.parent.name, path.stem) not in kept:
            path.unlink()
            (RESULTS / path.parent.name / (path.stem + ".json")).unlink(missing_ok=True)


def run(monday, sources, get=wels.http_get, ai_key="", ai_post=None, log=print):
    """Neue Karten holen, lesen, ablegen."""
    for source in sources:
        try:
            text = excerpt(card_text(source, get, monday))
            if len(text) < 80:
                raise ValueError("Seite ohne lesbaren Text")
        except Exception as error:
            result = {"id": source["id"], "week": monday.isoformat(), "verdict": "abruf_fehlgeschlagen",
                      "detail": None, "generic": None, "ai": None, "error": f"{type(error).__name__}: {error}"[:200]}
            log(f"{source['id']}: Abruf fehlgeschlagen – {result['error']}")
            _dump(RESULTS / source["id"] / (monday.isoformat() + ".json"), result)
            continue
        card = CARDS / source["id"] / (monday.isoformat() + ".txt")
        card.parent.mkdir(parents=True, exist_ok=True)
        card.write_text(text, encoding="utf-8")
        result = practise(source, monday, text, ai_key, ai_post)
        _dump(RESULTS / source["id"] / (monday.isoformat() + ".json"), result)
        log(f"{source['id']}: {result['verdict']}")


def rescore(log=print):
    """Alle gespeicherten Karten mit dem heutigen Ersatzleser neu lesen; die Vergleichslesung bleibt, wie sie war."""
    results = []
    for identifier, monday, text in stored_cards():
        path = RESULTS / identifier / (monday.isoformat() + ".json")
        before = _load(path, {})
        result = practise({"id": identifier}, monday, text, stored_ai=before.get("ai"))
        if before.get("verdict") != result["verdict"]:
            log(f"{identifier} {monday.isoformat()}: {before.get('verdict')} → {result['verdict']}")
        _dump(path, result)
        results.append(result)
    for path in sorted(RESULTS.glob("*/*.json")):   # Abruffehler haben keine Karte, zählen aber mit
        row = _load(path, {})
        if row.get("verdict") == "abruf_fehlgeschlagen":
            results.append(row)
    board = scoreboard(results)
    _dump(SCOREBOARD, board)
    return board


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rescore", action="store_true", help="nichts abrufen, nur gespeicherte Karten neu lesen")
    parser.add_argument("--only", help="nur dieses Übungslokal abrufen")
    arguments = parser.parse_args()
    now = datetime.now(wels.TZ)
    monday = wels.target_week(now)
    if not arguments.rescore:
        sources = [source for source in _load(SOURCES, []) if not arguments.only or source["id"] == arguments.only]
        run(monday, sources, ai_key=os.environ.get("OPENAI_API_KEY", "").strip())
        prune(now.date())
    board = rescore()
    for week in board[-4:]:
        print(f"Woche {week['week']}: Ersatzleser allein {week['generic_solved']} von {week['cards']} Karten "
              f"(einig {week['einig']}, mehr gelesen {week['mehr_gelesen']}, nur KI {week['nur_ki']}, uneinig {week['uneinig']}, "
              f"beide gescheitert {week['beide_gescheitert']}, andere Woche {week['andere_woche']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
