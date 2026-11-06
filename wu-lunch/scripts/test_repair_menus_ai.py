"""Offline regression tests for AI-assisted lunch menu auditing/repair.

These tests NEVER contact websites or use OpenAI billing.
"""
import copy
from datetime import date
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("repair_menus_ai", Path(__file__).with_name("repair_menus_ai.py"))
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

WEEK = date(2026, 11, 2)
DAY = "2026-11-06"
URL = "https://lia.coffee/"
NAME = "Lachs-Teriyaki-Bowl mit Edamame"
QUOTE = "Lachs-Teriyaki-Bowl mit Edamame 10,00 €"


def fresh_meal(price=None):
    return {"name": NAME, "price": price, "category": "Mittagsmenü",
            "included_choices": [], "included_soup": None, "description": ""}


def current_data():
    return {"weekStart": "2026-11-02",
            "restaurants": [{"id": ident, "days": {DAY: [fresh_meal()]} if ident == "lia" else {},
                             "seasonal": []} for ident in repair.IDS],
            "sources": [{"id": ident} for ident in repair.IDS]}


def candidate(price=10.0, quote=QUOTE, name=NAME, url=URL):
    return {"date": DAY, "name": name, "price_eur": price, "confidence": "high",
            "portion": None, "source_url": url, "evidence_excerpt": quote,
            "included_items": [], "extra_costs": []}


def evidence(source_text=QUOTE):
    return {URL: {"text": repair.normalized(source_text), "sha256": "a" * 64}}


def source():
    return [{"url": URL, "fetched": True, "sha256": "a" * 64, "type": "html"}]


class RepairTests(unittest.TestCase):
    def test_all_eleven_restaurants_have_coverage(self):
        self.assertEqual(len(repair.IDS), 11)
        self.assertEqual(len(set(repair.IDS)), 11)
        self.assertIn("topfdeckel", repair.IDS)
        self.assertIn("mensa", repair.IDS)

    def test_new_source_or_new_week_triggers_luna_even_if_parser_says_ok(self):
        state={"sources":{"lia":{"state":"ok","content_sha256":"new"}},
               "ai_repair":{"lia":{"action":"review_only","review_version":"complete-v4-row-evidence",
                   "review_week_start":"2026-11-02","last_checked":"2026-11-05T10:00:00",
                   "source_fingerprint":"old"}}}
        self.assertTrue(repair.needs_ai_review("lia",state,date(2026,11,6)))
        state["ai_repair"]["lia"]["source_fingerprint"]="new"
        self.assertFalse(repair.needs_ai_review("lia",state,date(2026,11,6)))
        self.assertTrue(repair.needs_ai_review("lia",state,date(2026,11,9)))

    def test_only_explicit_separately_sold_soup_can_be_added(self):
        data=current_data()
        row=candidate(price=3.50,quote="Tagessuppe mit Gemüse 3,50 €",
                      name="Tagessuppe mit Gemüse")
        row["category"]="Suppe"
        snapshot=evidence("Tagessuppe mit Gemüse 3,50 €")
        with patch.object(repair,"documented_current_week",return_value=True):
            fixes=repair.add_verified_missing_sides(
                "lia",{"items":[row]},data,source(),snapshot,WEEK,date(2026,11,6))
        self.assertEqual(len(fixes),1)
        meals=next(r for r in data["restaurants"] if r["id"]=="lia")["days"][DAY]
        self.assertEqual(meals[0]["name"],"Tagessuppe mit Gemüse")
        self.assertEqual(meals[0]["price"],3.50)
        self.assertFalse(meals[0]["included_choices"])

    def test_luna_can_publish_a_missing_source_anchored_main_dish(self):
        data=current_data()
        row=candidate(price=12.50,quote="Kartoffel-Curry mit Gemüse 12,50 €",
                      name="Kartoffel-Curry mit Gemüse")
        row["category"]="Hauptgericht"
        snapshot=evidence("Kartoffel-Curry mit Gemüse 12,50 €")
        with patch.object(repair,"documented_current_week",return_value=True):
            fixes=repair.add_verified_missing_sides(
                "lia",{"items":[row]},data,source(),snapshot,WEEK,date(2026,11,6))
        self.assertEqual(fixes,[{"date":DAY,"name":"Kartoffel-Curry mit Gemüse","price":12.5}])
        self.assertEqual(next(r for r in data["restaurants"] if r["id"]=="lia")["days"][DAY][0]["category"],"Hauptgericht")

    def test_general_luna_warning_does_not_block_individually_proven_row(self):
        result={"status":"found","warnings":["AG-Sticker-Rabatt ist kein Gerichtspreis"]}
        self.assertTrue(repair.publishable_result(result,[]))
        self.assertFalse(repair.publishable_result(result,["Eintrag 1: unbekannte Quelle"]))
        self.assertFalse(repair.publishable_result({"status":"unclear","warnings":[]},[]))

    def test_unproven_side_is_not_added(self):
        data=current_data()
        row=candidate(price=3.50,quote="Anderes Gericht 3,50 €",
                      name="Tagessuppe mit Gemüse")
        row["category"]="Suppe"
        with patch.object(repair,"documented_current_week",return_value=True):
            fixes=repair.add_verified_missing_sides(
                "lia",{"items":[row]},data,source(),
                evidence("Anderes Gericht 3,50 €"),WEEK,date(2026,11,6))
        self.assertEqual(fixes,[])

    def test_prices_must_be_explicit_not_guessed(self):
        self.assertEqual(repair.money_values(QUOTE), {repair.Decimal("10.00")})
        self.assertEqual(repair.money_values("Stand 06.11.2026"), set())

    def test_source_snapshots_are_bound_to_real_hash_and_nontruncated(self):
        inputs = [{"role": "user", "content": [
            {"type": "input_text", "text": f"ORIGINAL-HTML-QUELLE: {URL}\nSHA256: {'a'*64}\n<p>{QUOTE}</p>"}]}]
        snapshots = repair.source_snapshots(inputs, source())
        self.assertIn(URL, snapshots)
        self.assertIn(repair.normalized(QUOTE), snapshots[URL]["text"])
        bad = source()
        bad[0]["sha256"] = "b" * 64
        self.assertEqual(repair.source_snapshots(inputs, bad), {})
        bad = source()
        bad[0]["truncated"] = True
        self.assertEqual(repair.source_snapshots(inputs, bad), {})

    def test_exact_evidence_repair_price_only(self):
        data = current_data()
        orig = copy.deepcopy(data)
        with patch.object(repair, "documented_current_week", return_value=True):
            fixes = repair.apply_safe_price_fixes(
                "lia", {"items": [candidate()]}, data, source(), evidence(), WEEK,
                date(2026, 11, 6))
        meal = next(r for r in data["restaurants"] if r["id"] == "lia")["days"][DAY][0]
        self.assertEqual(len(fixes), 1)
        self.assertEqual(meal["price"], 10.0)
        self.assertEqual(meal["price_source"], URL)
        self.assertEqual(meal["price_verification"], "exact-source-quote-and-week")
        self.assertEqual(meal["name"], orig["restaurants"][repair.IDS.index("lia")]["days"][DAY][0]["name"])
        self.assertNotIn("_date", meal)

    def test_never_overwrite_confirmed_price(self):
        data = current_data()
        next(r for r in data["restaurants"] if r["id"] == "lia")["days"][DAY][0]["price"] = 11.0
        with patch.object(repair, "documented_current_week", return_value=True):
            fixes = repair.apply_safe_price_fixes("lia", {"items": [candidate()]},
                                                   data, source(), evidence(), WEEK,
                                                   date(2026, 11, 6))
        self.assertEqual(fixes, [])
        self.assertEqual(next(r for r in data["restaurants"] if r["id"] == "lia")["days"][DAY][0]["price"], 11.0)

    def test_unanchored_or_ambiguous_prices_never_publish(self):
        examples = [
            (candidate(price=12.0), evidence()),
            (candidate(quote="Lachs-Teriyaki-Bowl mit Edamame 10,00 €"), evidence("Preis ab 10,00 €")),
            (candidate(name="Anderes Gericht 10,00 €"), evidence()),
            (candidate(quote="Lachs-Teriyaki-Bowl mit Edamame 10,00 € oder 12,00 €"),
             evidence("Lachs-Teriyaki-Bowl mit Edamame 10,00 € oder 12,00 €")),
        ]
        for proposed, snap in examples:
            with self.subTest(proposed=proposed):
                data = current_data()
                with patch.object(repair, "documented_current_week", return_value=True):
                    fixed = repair.apply_safe_price_fixes("lia", {"items": [proposed]}, data,
                                                          source(), snap, WEEK, date(2026, 11, 6))
                self.assertEqual(fixed, [])
                self.assertIsNone(next(r for r in data["restaurants"] if r["id"] == "lia")["days"][DAY][0]["price"])

    def test_wrong_week_never_publish(self):
        data = current_data()
        with patch.object(repair, "documented_current_week", return_value=False):
            fixed = repair.apply_safe_price_fixes("lia", {"items": [candidate()]},
                                                  data, source(), evidence(), WEEK,
                                                  date(2026, 11, 6))
        self.assertFalse(fixed)

    def test_duplicate_same_day_menus_require_review(self):
        data = current_data()
        next(r for r in data["restaurants"] if r["id"] == "lia")["days"][DAY].append(fresh_meal())
        with patch.object(repair, "documented_current_week", return_value=True):
            fixed = repair.apply_safe_price_fixes("lia", {"items": [candidate()]}, data,
                                                  source(), evidence(), WEEK, date(2026, 11, 6))
        self.assertFalse(fixed)

    def test_no_automatic_price_write_for_other_restaurants(self):
        for ident in ("topfdeckel", "mensa", "omakueche", "losteria"):
            row = fresh_meal()
            row["_date"] = DAY
            with patch.object(repair, "documented_current_week", return_value=True):
                self.assertFalse(repair.eligible_price_fix(
                    ident, candidate(), row, source(), evidence(), WEEK, {}))

    def test_lia_problem_detected_even_if_parser_claims_success(self):
        data = current_data()
        status = {"sources": {"lia": {"state": "ok"}}}
        self.assertIn("missing_price", repair.issue_codes(
            data, status, "lia", date(2026, 11, 6)))

    def test_budget_cap_and_detected_problems_first(self):
        data = current_data()
        status = {"sources": {"campus": {"state": "error"}, "lia": {"state": "ok"}}}
        selected = repair.choose_restaurants(data, status, date(2026, 11, 6), limit=2)
        self.assertLessEqual(len(selected), 2)
        self.assertIn("campus", selected)

    def test_mensa_and_topf_use_dedicated_acquisition(self):
        data = current_data()
        status = {"sources": {}}
        for ident, expected in (("mensa", "dedicated_pdf_ai"), ("topfdeckel", "browser_import")):
            result = repair.analyze_one(ident, data, status, WEEK,
                                        date(2026, 11, 6), "", "gpt-6-luna")
            self.assertEqual(result["action"], expected)


if __name__ == "__main__":
    unittest.main()
