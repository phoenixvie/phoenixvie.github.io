"""Mensa category regression tests independent of an API key or network."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("mensa_ai_categories",
                                               Path(__file__).with_name("update_mensa_ai.py"))
mensa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mensa)


class MensaCategoriesTests(unittest.TestCase):
    def test_visual_menu_category_normalization(self):
        expected = {
            "Global & Grill": "Global & Grill",
            "Powered by plants / Veggie": "Powered by plants / Veggie",
            "Meaty": "Meaty",
            "Tagessuppe": "Tagessuppe",
        }
        for raw, mapped in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(mensa.VALID_CATEGORIES.get(mensa.normalize(raw)), mapped)

    def test_unrecognized_categories_are_not_approved(self):
        self.assertIsNone(mensa.VALID_CATEGORIES.get(mensa.normalize("Special Bundle")))


if __name__ == "__main__":
    unittest.main()
