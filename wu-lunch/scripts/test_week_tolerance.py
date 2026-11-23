"""Wochenbeleg streng, Tippfehler nachsichtig (Anlass: 23.11.2026, Karma Food „23.11.-25.11.").

Das Startdatum belegt die Woche. Ein vertipptes oder unmögliches Enddatum, eine fehlende Jahreszahl oder ein
Planbeginn nach einem Feiertag dürfen keine vollständige Karte sperren – eine andere Woche aber weiterhin.
"""
import sys
import unittest
from datetime import date, timedelta

sys.dont_write_bytecode = True
import update_menus as menus
import update_new_restaurants as new
import update_topf_browser as topf
import report_problems as report

MON = date(2026, 11, 23)
CARD = """<h2>TAGESTELLER / LUNCH SPECIAL {head}</h2>
<p>Mo-Do 13,5 + Suppe 2,-</p>
<p>MO: Hühnerschnitzel mit Reis</p><p>DI: Gebratenes Rindfleisch mit Gemüse</p>
<p>MI: Faschierter Braten mit Kartoffelpüree</p><p>DO: Gebackener Fisch mit Petersilerdäpfeln</p>
<p>FR: Fischgericht mit Salat</p>"""


class WeekToleranceTests(unittest.TestCase):
    def test_start_date_decides_and_a_mistyped_end_does_not_block(self):
        for end in (date(2026, 11, 25), date(2026, 11, 28), date(2026, 11, 27)):
            self.assertTrue(menus.week_identity((MON, end), MON))
        self.assertFalse(menus.week_identity((MON - timedelta(days=7), MON - timedelta(days=3)), MON))
        self.assertFalse(menus.week_identity((MON + timedelta(days=7), MON + timedelta(days=11)), MON))
        self.assertFalse(menus.week_identity(None, MON))

    def test_plan_starting_after_a_holiday_needs_the_matching_calendar_week(self):
        tuesday = (MON + timedelta(days=1), MON + timedelta(days=4))
        self.assertTrue(menus.week_identity(tuesday, MON, "SPEISEPLAN KW 48"))
        self.assertFalse(menus.week_identity(tuesday, MON, "SPEISEPLAN KW 47"))
        self.assertFalse(menus.week_identity(tuesday, MON))

    def test_impossible_end_date_keeps_the_start(self):
        self.assertEqual(menus.period("23.11.2026 - 27.11.2026"), (MON, MON + timedelta(days=4)))
        self.assertEqual(menus.period("23.11.2026 - 26.12.2026"), (MON, MON + timedelta(days=4)))   # Monat vertippt
        self.assertEqual(menus.period("23.11.26 – 26.11.25"), (MON, MON + timedelta(days=4)))       # Jahr vertippt
        self.assertEqual(menus.period("23. Nov. 2026 – 20. Nov. 2026")[0], MON)

    def test_austrian_january_abbreviation(self):
        self.assertEqual(menus.period("4. Jän. 2027 – 8. Jän. 2027"), (date(2027, 1, 4), date(2027, 1, 8)))

    def test_gruenehuette_heading_typed_in_different_ways(self):
        for head in ("23. 11. 2026", "23.11.26", "23.11.", "vom 23. 11. 2026", ": 23.11.2026", "23. 11. – 27. 11. 2026"):
            days, _ = menus.parse_gruenehuette(CARD.format(head=head).encode(), MON)
            self.assertEqual(days["2026-11-23"][0]["name"], "Hühnerschnitzel mit Reis", head)
        for head in ("16. 11. 2026", "30.11."):
            with self.assertRaisesRegex(ValueError, "nicht von aktueller Woche"):
                menus.parse_gruenehuette(CARD.format(head=head).encode(), MON)
        january = date(2027, 1, 4)
        days, _ = menus.parse_gruenehuette(CARD.format(head="4.1.").encode(), january)
        self.assertIn("2027-01-04", days)

    def test_topf_week_header_with_mistyped_end(self):
        topf.verify_week("Wochenmenü 23. November – 27. November 2026", MON)
        topf.verify_week("Wochenmenü 23. November – 28. November 2026", MON)
        with self.assertRaisesRegex(ValueError, "nicht aktuelle Woche"):
            topf.verify_week("Wochenmenü 16. November – 20. November 2026", MON)

    def test_karma_pdf_match_threshold_for_small_cards(self):
        entries = {f"2026-11-2{day}": [{"name": f"Gericht{day}{n} Besonderheit{day}{n}"} for n in range(3)] for day in (3, 4, 5)}
        words = [item["name"] for rows in entries.values() for item in rows]
        new.validate_karma_pdf_matches(entries, " ".join(words[:7]))            # 7 von 9 genügen
        with self.assertRaisesRegex(ValueError, "weichen voneinander"):
            new.validate_karma_pdf_matches(entries, " ".join(words[:6]))

    def test_problem_report_shows_the_error_text_of_the_main_importer(self):
        status = {"sources": {"campus": {"state": "error", "consecutive_failures": 4,
                                         "error": "ValueError: Campus: Plan nicht für KW 48: None"}}}
        self.assertIn("Plan nicht für KW 48", report.wu_problems(status, {"restaurants": []})["wu:campus"]["message"])


if __name__ == "__main__":
    unittest.main()
