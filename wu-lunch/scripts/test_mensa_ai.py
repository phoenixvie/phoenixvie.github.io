"""Offline tests for multimodal Mensa PDF safeguards, no API calls."""
import importlib.util
from pathlib import Path
import unittest
from datetime import date

path = Path(__file__).with_name("update_mensa_ai.py")
spec = importlib.util.spec_from_file_location("mensa_ai", path)
mensa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mensa)

MONDAY = date(2026, 11, 2)
PDF_URL = "https://www.wumensa.at/menuplan-deutsch/"


def fixture():
    meals = []
    for d in range(2, 7):
        for category, name in [
            ("Meaty", "Hendlfilet mit Kartoffeln"),
            ("Powered by plants / Veggie", "Gemüse Curry mit Reis"),
        ]:
            meals.append({
                "date": f"2026-11-{d:02d}", "name": name, "category": category,
                "price_eur": 9.9, "portion": None,
                "included_items": [], "extra_costs": [],
                "source_url": PDF_URL,
                "evidence_excerpt": f"{name} 9,90",
                "confidence": "high",
            })
    return {"status": "found", "warnings": [], "items": meals}


class MensaTests(unittest.TestCase):
    def setUp(self):
        self.pdf_text = ("Hendlfilet mit Kartoffeln Gemüse Curry mit Reis 9,90 " * 20)

    def test_weekly_complete(self):
        days = mensa.validate_menu(fixture(), self.pdf_text, MONDAY, PDF_URL)
        self.assertEqual(len(days), 5)
        self.assertEqual(sum(map(len, days.values())), 10)
        self.assertEqual(days["2026-11-02"][0]["price"], 9.9)

    def test_missing_price_fails_closed(self):
        result = fixture()
        result["items"][0]["price_eur"] = None
        with self.assertRaisesRegex(ValueError, "Preis"):
            mensa.validate_menu(result, self.pdf_text, MONDAY, PDF_URL)

    def test_missing_day_fails_closed(self):
        result = fixture()
        result["items"] = [r for r in result["items"] if r["date"] != "2026-11-06"]
        with self.assertRaises(ValueError):
            mensa.validate_menu(result, self.pdf_text, MONDAY, PDF_URL)

    def test_invalid_pdf_provenance_fails(self):
        result = fixture()
        result["items"][0]["source_url"] = "https://example.com/"
        with self.assertRaisesRegex(ValueError, "Originalbeleg"):
            mensa.validate_menu(result, self.pdf_text, MONDAY, PDF_URL)

    def test_evidence_not_in_source_fails(self):
        result = fixture()
        result["items"][0]["evidence_excerpt"] = "Unbekannte Fantasiespeise"
        with self.assertRaisesRegex(ValueError, "Quellenbeleg"):
            mensa.validate_menu(result, self.pdf_text, MONDAY, PDF_URL)

    def test_no_global_grill_soup(self):
        result = fixture()
        result["items"][0]["category"] = "Global & Grill"
        result["items"][0]["included_items"] = ["Suppe"]
        with self.assertRaisesRegex(ValueError, "Global"):
            mensa.validate_menu(result, self.pdf_text, MONDAY, PDF_URL)

    def test_ai_failure_does_not_modify_production(self):
        data = {"restaurants": [{"id": "mensa", "days": {
            f"2026-11-{i:02d}": [{"name": "Altes Menü"}] for i in range(2, 7)
        }}], "sources": [{"id": "mensa"}]}
        status = {"sources": {}, "problems": ["mensa: parser error"]}
        candidate = mensa.validate_menu(fixture(), self.pdf_text, MONDAY, PDF_URL)
        candidate["2026-11-06"] = []
        with self.assertRaisesRegex(ValueError, "löschen"):
            mensa.apply_candidate(data, status, candidate, MONDAY, {
                "sha256": "abc"}, {}, "gpt-6-luna")
        self.assertEqual(data["restaurants"][0]["days"]["2026-11-02"][0]["name"], "Altes Menü")


if __name__ == "__main__":
    unittest.main()
