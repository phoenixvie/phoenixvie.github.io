"""Offline regression tests: never silently publish incomplete AI menus."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("publish_ai", Path(__file__).with_name("publish_ai.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def item(day, name="Curry mit Reis", price=10.0, included=None, category="Mittagsmenü"):
    return {
        "date": day, "name": name, "category": category,
        "portion": None, "price_eur": price,
        "included_items": [] if included is None else included,
        "extra_costs": [], "confidence": "high",
        "source_url": "https://example.org/wochenkarte",
        "evidence_excerpt": "Curry mit Reis: 10,00 Euro",
    }


DAYS = [f"2026-11-{d:02d}" for d in range(2, 7)]


def fixture():
    production = {
        "weekStart": "2026-11-02", "sources": [
            {"id": "lia", "status": "ok"},
            {"id": "mensa", "status": "ok"},
        ], "restaurants": [
            {"id": "lia", "status": "ok", "days": {day: [
                {"name": "Curry mit Reis", "price": 10.0, "included_choices": [],
                 "included_soup": None}
            ] for day in DAYS}, "seasonal": []},
            {"id": "mensa", "status": "ok", "days": {day: [
                {"name": "Curry mit Reis", "price": 10.0, "included_choices": [],
                 "included_soup": None}
            ] for day in DAYS}, "seasonal": []},
        ],
    }
    report = {
        "week_start": "2026-11-02", "checked_at": "2026-11-06T18:00:00+01:00",
        "model": "gpt-6-luna", "restaurants": {},
    }
    for ident in ("lia", "mensa"):
        report["restaurants"][ident] = {
            "result": {"status": "found", "items": [item(d) for d in DAYS],
                       "warnings": []},
            "validation_issues": [],
            "sources": [{"url": "https://example.org/wochenkarte", "fetched": True}],
        }
    return report, production


class PublicationSafetyTests(unittest.TestCase):
    def test_complete_batch_does_not_mutate_input(self):
        report, prod = fixture()
        original = copy.deepcopy(prod)
        candidate, audit = module.prepare(report, prod)
        self.assertEqual(prod, original)
        self.assertEqual({r["id"] for r in candidate["restaurants"]}, {"lia", "mensa"})
        self.assertEqual(len(audit["published"]), 2)
        self.assertEqual(candidate["restaurants"][0]["status"], "ai_candidate")

    def test_missing_price_blocks_whole_batch(self):
        report, prod = fixture()
        report["restaurants"]["mensa"]["result"]["items"][2]["price_eur"] = None
        with self.assertRaisesRegex(ValueError, "Preis fehlt"):
            module.prepare(report, prod)
        self.assertEqual(prod["restaurants"][0]["status"], "ok")

    def test_missing_weekday_blocks(self):
        report, prod = fixture()
        report["restaurants"]["lia"]["result"]["items"].pop()
        with self.assertRaisesRegex(ValueError, "Wochentage"):
            module.prepare(report, prod)

    def test_warning_blocks(self):
        report, prod = fixture()
        report["restaurants"]["lia"]["result"]["warnings"] = ["Woche unklar"]
        with self.assertRaisesRegex(ValueError, "KI-Bericht"):
            module.prepare(report, prod)

    def test_no_free_soup_global_grill(self):
        report, prod = fixture()
        report["restaurants"]["mensa"]["result"]["items"][0]["category"] = "Global & Grill"
        report["restaurants"]["mensa"]["result"]["items"][0]["included_items"] = ["Suppe"]
        with self.assertRaisesRegex(ValueError, "Global"):
            module.prepare(report, prod)

    def test_preserves_old_soup_or_blocks_when_omitted(self):
        report, prod = fixture()
        prod["restaurants"][0]["days"][DAYS[0]][0]["included_soup"] = "Tomatensuppe"
        with self.assertRaisesRegex(ValueError, "Tagessuppe"):
            module.prepare(report, prod)
        report["restaurants"]["lia"]["result"]["items"][0]["included_items"] = ["Suppe"]
        candidate, _ = module.prepare(report, prod)
        self.assertEqual(candidate["restaurants"][0]["days"][DAYS[0]][0]["included_soup"], "Tomatensuppe")

    def test_duplicate_or_unapproved_source_blocks(self):
        report, prod = fixture()
        report["restaurants"]["lia"]["result"]["items"].append(item(DAYS[0]))
        with self.assertRaisesRegex(ValueError, "Doppeltes"):
            module.prepare(report, prod)
        report, prod = fixture()
        report["restaurants"]["lia"]["sources"] = []
        with self.assertRaisesRegex(ValueError, "Originalquelle"):
            module.prepare(report, prod)


if __name__ == "__main__":
    unittest.main()
