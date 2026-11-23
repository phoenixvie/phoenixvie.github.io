"""Geschlossene Tage und einzelne auffällige Gerichte sperren nicht mehr die ganze Woche (Stand 23.11.2026).

Die Regel dahinter: Der Beleg für die richtige Woche bleibt streng. Ein Feiertag, ein Gericht ohne Preis oder
ein doppelt genannter Eintrag sind aber kein Grund, eine sonst vollständige Karte nicht zu zeigen.
"""
import copy
import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
import update_menus as menus
import update_mensa_ai as mensa
import update_new_restaurants as new
import update_topf_browser as topf
import report_problems as report

FIXTURES = Path(__file__).parent / "fixtures"
MON = date(2026, 11, 2)


def finn_answer(skip=None, warnings=()):
    rows = []
    for index in range(5):
        day = date(2026, 11, 2 + index).isoformat()
        if day == skip:
            continue
        for kind in ("Vegan", "Fleisch"):
            rows.append({"date": day, "name": f"{kind} Gericht mit Kartoffeln {index}", "price_eur": 10.0, "category": kind,
                         "portion": None, "included_items": [], "extra_costs": [], "confidence": "high",
                         "source_url": "https://cdn.shopify.com/files/FINN_kw45.jpg?v=1793577600",
                         "evidence_excerpt": "Hauptgericht €10,00"})
    return {"status": "found", "items": rows, "warnings": list(warnings)}


class ClosedDayTests(unittest.TestCase):
    def test_baschly_card_without_date_counts_as_new_only_after_it_changed(self):
        shown = {"content_sha256": "abc", "shown_week": "2026-11-16"}
        self.assertTrue(menus.undated_card_is_stale(shown, "abc", date(2026, 11, 23)))      # Karte der Vorwoche
        self.assertFalse(menus.undated_card_is_stale(shown, "neu", date(2026, 11, 23)))     # geändert: neue Woche
        self.assertFalse(menus.undated_card_is_stale(shown, "abc", date(2026, 11, 16)))     # dieselbe Woche
        self.assertFalse(menus.undated_card_is_stale({"content_sha256": "abc"}, "abc", date(2026, 11, 23)))  # noch kein Vergleich
        source = (Path(menus.__file__)).read_text(encoding="utf-8")
        self.assertIn('operations[ident]["shown_week"]=monday.isoformat()', source)
        self.assertIn('"seit der vorwoche unverändert"'.replace('"', ''), source.lower())

    def test_mensa_holiday_cell_is_not_a_dish_and_soups_need_not_be_called_suppe(self):
        for text in ("Feiertag", "FEIERTAG – geschlossen", "geschlossen", "Kein Betrieb", "Betriebsurlaub"):
            self.assertTrue(menus.CLOSED_CELL.match(text), text)
        for text in ("Feiertagsbraten mit Knödel", "Geschmortes Rind"):
            self.assertFalse(menus.CLOSED_CELL.match(text), text)
        for soup in ("Minestrone", "Rindsbouillon mit Frittaten", "Kürbiscreme", "Klare Gemüsesuppe", "Linseneintopf"):
            self.assertTrue(menus.SOUP_WORD.search(soup), soup)
        self.assertFalse(menus.SOUP_WORD.search("tter Chicken"))

    def test_mensa_week_with_one_closed_day_is_accepted_only_if_the_plan_says_so(self):
        saved = json.loads((FIXTURES / "mensa-2026-11-16-monday.rejected-answer.json").read_text(encoding="utf-8"))
        monday = date(2026, 11, 16)
        result = copy.deepcopy(saved["result"])
        for item in result["items"]:
            if item["category"] == "Menüoption" and item["price_eur"] is None:
                item["price_eur"] = 7.60
        result["items"] = [item for item in result["items"] if item["date"] != "2026-11-17"]
        text = mensa.independent_period((FIXTURES / "mensa-2026-11-16-monday.pdf").read_bytes(), monday)
        with self.assertRaisesRegex(ValueError, "weniger als fünf Wochentage"):
            mensa.validate_menu(copy.deepcopy(result), text, monday, saved["source"]["url"])
        days = mensa.validate_menu(copy.deepcopy(result), text + "\nFeiertag\n", monday, saved["source"]["url"])
        self.assertEqual([bool(days[day]) for day in sorted(days)], [True, False, True, True, True])
        two_closed = copy.deepcopy(result)
        two_closed["items"] = [item for item in two_closed["items"] if item["date"] != "2026-11-18"]
        with self.assertRaisesRegex(ValueError, "weniger als fünf Wochentage"):
            mensa.validate_menu(two_closed, text + "\nFeiertag\n", monday, saved["source"]["url"])

    def test_finn_closed_day_needs_an_explicit_note_from_the_image_reading(self):
        url = "https://cdn.shopify.com/files/FINN_kw45.jpg?v=1793577600"
        note = ["Dienstag: geschlossen (Feiertag)"]
        days = new.validate_finn_pair(finn_answer("2026-11-03", note), finn_answer("2026-11-03", note), MON, url)
        self.assertEqual([len(days[day]) for day in sorted(days)], [2, 0, 2, 2, 2])
        with self.assertRaisesRegex(ValueError, "nicht alle fünf"):
            new.validate_finn_pair(finn_answer("2026-11-03"), finn_answer("2026-11-03"), MON, url)
        with self.assertRaisesRegex(ValueError, "nicht eindeutig"):
            unclear = ["Dienstag geschlossen, Preis unklar"]
            new.validate_finn_pair(finn_answer("2026-11-03", unclear), finn_answer("2026-11-03", unclear), MON, url)

    def test_finn_unknown_column_label_only_loses_the_symbol(self):
        url = "https://cdn.shopify.com/files/FINN_kw45.jpg?v=1793577600"
        first, second = finn_answer(), finn_answer()
        for answer in (first, second):
            answer["items"][0]["category"] = "Vegetarisch/Vegan"
        days = new.validate_finn_pair(first, second, MON, url)
        self.assertEqual(days["2026-11-02"][0]["diet"], "unknown")

    def test_topf_closed_day_wording_and_failed_attempts_are_reported(self):
        self.assertTrue(topf.CLOSED_DAY.search("Heute geschlossen – Feiertag"))
        self.assertFalse(topf.CLOSED_DAY.search("Suppe · Hauptgericht · Dessert"))
        source = Path(topf.__file__).read_text(encoding="utf-8")
        self.assertIn('if x.get("category")=="Special":', source)          # Special ohne kleine/große Portion
        self.assertIn("if len(mains)<2:", source)                          # Suppe und Nachspeise dürfen fehlen
        now = datetime(2026, 11, 23, 11, 0, tzinfo=ZoneInfo("Europe/Vienna"))
        quiet = {"sources": {}, "topf_browser_attempt": {"error": "Topf-Browser: Tab", "failures": 2}}
        self.assertEqual(report.wu_problems(quiet, {"restaurants": []}, now), {})
        loud = {"sources": {}, "topf_browser_attempt": {"error": "Topf-Browser: sichtbares Wochendatum fehlt", "failures": 3}}
        found = report.wu_problems(loud, {"restaurants": [{"id": "topfdeckel", "name": "Topf & Deckel"}]}, now)
        self.assertIn("Wochendatum fehlt", found["wu:topfdeckel"]["message"])

    def test_gruenehuette_week_with_two_closed_days_stays_visible(self):
        page = """<h2>TAGESTELLER / LUNCH SPECIAL 2.11.2026</h2><p>Mo-Do 13,5</p>
        <p>MO: Hühnerschnitzel mit Reis</p><p>DI: Gebratenes Rindfleisch mit Gemüse</p>
        <p>MI: Faschierter Braten mit Kartoffelpüree</p>"""
        days, _ = menus.parse_gruenehuette(page.encode(), MON)
        self.assertEqual([bool(days[day]) for day in sorted(days)], [True, True, True, False, False])
        with self.assertRaisesRegex(ValueError, "unvollständiger Wochenplan"):
            menus.parse_gruenehuette(page.replace("<p>MI: Faschierter Braten mit Kartoffelpüree</p>", "").encode(), MON)


class KarmaSingleItemTests(unittest.TestCase):
    def page(self, extra):
        parts = ["<body><p>Karma Food 02.11.-07.11.</p>",
                 '<a href="https://cdn.shopify.com/s/files/1/111/files/Karma_KW45.pdf?v=1793300000">Menü als PDF herunterladen</a>']
        for index, day in enumerate(("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag")):
            parts.append(f"<h2>{day}</h2>")
            for number in range(3):
                parts.append(f"<h3>Gericht {index} Variation {number} mit Gewürzen</h3><div>Vegan</div>")
            if index == 1:
                parts.append(extra)
        return ("".join(parts) + "</body>").encode()

    def test_too_short_or_repeated_entry_is_skipped_instead_of_blocking_the_week(self):
        rows, _ = new.parse_karma_html(self.page("<h3>Dal</h3><div>Vegan</div>"), MON)
        self.assertEqual([len(rows[day]) for day in sorted(rows)], [3, 3, 3, 3, 3])
        rows, _ = new.parse_karma_html(self.page("<h3>Gericht 1 Variation 0 mit Gewürzen</h3><div>Vegan</div>"), MON)
        self.assertEqual(len(rows["2026-11-03"]), 3)
        rows, _ = new.parse_karma_html(self.page("<h3>Ramen</h3><div>Vegan</div>"), MON)
        self.assertEqual(rows["2026-11-03"][-1]["name"], "Ramen")


if __name__ == "__main__":
    unittest.main()
