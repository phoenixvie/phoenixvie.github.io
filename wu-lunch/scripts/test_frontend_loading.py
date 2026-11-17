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

    def test_background_refresh_never_exposes_raw_import_data(self):
        # 17.11.2026: Alle 3 Sekunden wurde DATA zuerst mit den rohen Importdaten überschrieben und
        # erst nach dem Abruf der Admin-Einstellungen korrigiert. Ein Klick auf einen Tag in diesem
        # Moment zeigte Standardnamen ("Lia Coffee WU") und das deaktivierte L'Osteria – dauerhaft
        # bis zur nächsten Bedienung. Jetzt wird ein eigener Stand aufgebaut und in einem Schritt übernommen.
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        refresh=html[html.index("async function refreshLiveData()"):html.index("window.setInterval(refreshLiveData")]
        self.assertNotIn("Object.assign(DATA,incoming)",refresh)
        self.assertIn("const next={...DATA,...incoming};",refresh)
        self.assertIn("applyRestaurantOverrides(next)",refresh)
        self.assertIn("applyManualMenus(next)",refresh)
        self.assertLess(refresh.index("if(!profileFetchSucceeded||!manualFetchSucceeded)return;"),
                        refresh.index("Object.assign(DATA,next);"))
        overrides=html[html.index("async function applyRestaurantOverrides(target=DATA)"):html.index("let manualFetchSucceeded=false;")]
        self.assertNotIn("DATA.restaurants",overrides)
        manual=html[html.index("async function applyManualMenus(target=DATA)"):html.index("const RESTAURANT_ORDER")]
        self.assertNotIn("DATA.restaurants",manual)

    def test_weekend_preview_and_mobile_swipe_are_available(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        self.assertIn("const displayMondayIso=weekend",html)
        self.assertIn("Noch nicht veröffentlicht</div>",html)
        self.assertNotIn("Vorschau auf Montag.",html)
        self.assertIn("WULunchUpdateInfo",html)
        self.assertIn('href="impressum.html"',html)
        self.assertIn('href="admin.html"',html)
        self.assertIn('await Promise.all([applyRestaurantOverrides(),loadAnnouncement(),applyManualMenus()]);',html)
        self.assertIn("restaurant_overrides?select=*",html)
        self.assertIn("menu_day_overrides?week_start=eq.",html)
        self.assertIn("restaurant.manualDays?.[selectedDate]",html)
        self.assertIn("Angaben ohne Gewähr",html)
        self.assertIn("Diese Website verwendet keine Cookies.",html)
        self.assertIn('id="lunchAnnouncement"',html)
        self.assertIn('width:fit-content',html)
        self.assertIn('text-align:center',html)
        self.assertIn("function loadAnnouncement()",html)
        self.assertIn("lunch_announcement?id=eq.true",html)
        self.assertIn("'X €'",html)
        self.assertIn("grid-template-areas:'logo title' 'menu menu' 'links links'",html)
        self.assertNotIn("Preis nicht bestätigt",html)
        self.assertTrue((ROOT/"admin.html").is_file())
        admin=(ROOT/"admin.html").read_text(encoding="utf-8")
        self.assertIn("/auth/v1/token?grant_type=password",admin)
        self.assertIn("/rest/v1/menu_history",admin)
        self.assertIn("backfillHistory",admin)
        self.assertIn('id="desktopAnnouncement"',admin)
        self.assertIn('id="mobileAnnouncement"',admin)
        self.assertIn("function saveAnnouncement()",admin)
        self.assertIn("function saveProfile()",admin)
        self.assertIn("function saveMenu()",admin)
        self.assertIn("function resetMenu()",admin)
        self.assertIn("/storage/v1/object/lunch-logos/",admin)
        self.assertIn("menu_day_overrides?week_start=eq.",admin)
        self.assertIn("Automatische Menüprüfung",admin)
        self.assertNotIn('value="marco@startit.at"',admin)
        self.assertIn("function moveDay(step)",html)
        self.assertIn("listView.addEventListener('pointerup'",html)
        self.assertIn("touch-action:pan-y",html)
        self.assertIn("day-slide-next",html)
        self.assertIn('id="swipeDots"',html)
        self.assertIn("function renderSwipeDots()",html)
        self.assertIn("map-loader-spinner",html)
        workflow=(ROOT.parent/".github"/"workflows"/"wu-lunch-menus.yml").read_text(encoding="utf-8")
        # Ein täglicher Stundenplan deckt Wochenendvorschau und Werktage ab;
        # pünktlich zum Wochenstart sorgt zusätzlich der Taktgeber.
        self.assertIn("'15 3-21 * * *'",workflow)
        self.assertIn("takt.py ensure",workflow)
        self.assertIn('id="updateProcess"',admin)
        self.assertIn("update-info.js",html)
        self.assertIn("Geprüfte Wochenkarte ins Admin-Archiv sichern",workflow)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY",workflow)

if __name__=="__main__":
    unittest.main()
