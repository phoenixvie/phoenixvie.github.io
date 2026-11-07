"""Frontend load order and restaurant visibility regression guards (no network)."""
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
ORDER=["mensa","baschly","finn","lia","campus","karmafood","topfdeckel",
       "omakueche","gruenehuette","glashaus","losteria"]

class FrontendLoadingTests(unittest.TestCase):
    def test_all_eleven_restaurants_are_in_current_data_and_fallback(self):
        data=json.loads((ROOT/"data"/"menus.json").read_text(encoding="utf-8"))
        js=(ROOT/"data.js").read_text(encoding="utf-8").strip()
        self.assertTrue(js.startswith("window.CAMPUS_LUNCH_DATA = "))
        fallback=json.loads(js.removeprefix("window.CAMPUS_LUNCH_DATA = ").removesuffix(";"))
        for current in (data,fallback):
            self.assertEqual([r["id"] for r in current["restaurants"]],ORDER)
            self.assertEqual({r["id"] for r in current["sources"]},set(ORDER))
            self.assertEqual(len(current["restaurants"]),11)

    def test_list_is_rendered_before_map_library_is_loaded(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        self.assertNotIn('<script src="https://unpkg.com/leaflet',html)
        self.assertIn("DATA.restaurants.sort(",html)
        self.assertIn("window.addEventListener('load',requestMapAfterPageLoad",html)
        self.assertIn("window.requestIdleCallback(loadLeafletAssets",html)
        self.assertIn("js.onload=()=>loadRealMap();",html)
        self.assertIn("update();\n    renderNextUpdate();",html)
        self.assertLess(html.index("    update();\n    renderNextUpdate();"),
                        html.index("function requestMapAfterPageLoad()"))
        self.assertIn("karmafood:'logo-karmafood'",html)
        self.assertIn("finn:'logo-finn'",html)

    def test_weekend_preview_and_mobile_swipe_are_available(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        self.assertIn("const displayMondayIso=weekend",html)
        self.assertIn("Noch nicht veröffentlicht</div>",html)
        self.assertNotIn("Vorschau auf Montag.",html)
        self.assertIn("const IMPORT_SLOTS=",html)
        self.assertIn('href="impressum.html"',html)
        self.assertIn("function moveDay(step)",html)
        self.assertIn("listView.addEventListener('pointerup'",html)
        self.assertIn("touch-action:pan-y",html)
        self.assertIn("day-slide-next",html)
        workflow=(ROOT.parent/".github"/"workflows"/"wu-lunch-menus.yml").read_text(encoding="utf-8")
        self.assertIn("'15 6-17 * * 6'",workflow)
        self.assertIn("Sat 08:15–18:15",html)

if __name__=="__main__":
    unittest.main()
