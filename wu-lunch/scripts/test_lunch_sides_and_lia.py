"""Cross-restaurant side ordering and Lia WU price regression (offline)."""
import importlib.util
import json
from datetime import date
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
menus=load("menus_lunch",ROOT/"scripts"/"update_menus.py")
new=load("new_lunch",ROOT/"scripts"/"update_new_restaurants.py")
WEEK=date(2026,11,2)
SOURCE="https://cdn.shopify.com/files/FINN_kw45.jpg?v=1793577600"

def ai_side(name,cat,price):
    return {"date":None,"name":name,"category":cat,"price_eur":price,
            "source_url":SOURCE,"confidence":"high",
            "evidence_excerpt":name+" 3,50 €","included_items":[]}

class SideAndPriceTests(unittest.TestCase):
    def test_lia_price_after_allergens(self):
        raw=('<html><body><div>Tagesmenü Lia Coffee am WU Campus</div>'
             '<p>Donnerstag 05.11.</p>'
             '<span>Lasagne klassisch – mit Schwein & Rind (A, G)</span>'
             '<span>€ 10,00</span>'
             '<p>Tagesmenü Lia Bistro</p></body></html>').encode()
        days,_=menus.parse_lia_week(raw,WEEK)
        item=days["2026-11-05"][0]
        self.assertAlmostEqual(item["price"],10)
        self.assertIn("Lasagne klassisch",item["name"])

    def test_lia_price_at_end_of_dish(self):
        raw=('<html><body>Tagesmenü Lia Coffee am WU Campus'
             '<div>Donnerstag 05.11.</div>'
             '<p>Lasagne klassisch – mit Schwein & Rind (A,G) € 10,00</p>'
             '<div>Tagesmenü Lia Bistro</div></body></html>').encode()
        days,_=menus.parse_lia_week(raw,WEEK)
        self.assertAlmostEqual(days["2026-11-05"][0]["price"],10)

    def test_finn_verified_sides_and_combo(self):
        first={"status":"found","warnings":[],"items":[
            ai_side("Tagessuppe oder Salat","Suppe/Salat",3.5),
            ai_side("Hauptgericht mit Suppe","Menüoption",11),
        ]}
        second=json.loads(json.dumps(first))
        prices=new.verify_finn_weekly_extras(first,second,SOURCE)
        self.assertEqual(prices["Tagessuppe oder Salat"],3.5)
        self.assertEqual(prices["Hauptgericht mit Suppe"],11)
        days={"2026-11-05":[{"name":"Lasagne","category":"Fleisch","price":10}]}
        new.attach_finn_weekly_extras(days,prices,SOURCE)
        self.assertEqual(days["2026-11-05"][0]["price"],3.5)
        self.assertEqual(days["2026-11-05"][1]["menu_options"][0]["total_price"],11)

    def test_finn_mismatched_sides_never_apply(self):
        first={"status":"found","warnings":[],"items":[ai_side("Tagessuppe oder Salat","Suppe/Salat",3.5)]}
        second={"status":"found","warnings":[],"items":[ai_side("Tagessuppe oder Salat","Suppe/Salat",4)]}
        with self.assertRaisesRegex(ValueError,"widersprechen"):
            new.verify_finn_weekly_extras(first,second,SOURCE)

    def test_finn_soup_not_included_without_claim(self):
        raw=json.loads((ROOT/"data"/"menus.json").read_text())
        finn=next(r for r in raw["restaurants"] if r["id"]=="finn")
        for meals in finn["days"].values():
            self.assertEqual(meals[0]["category"],"Suppe/Salat")
            self.assertEqual(meals[0]["price"],3.5)
            for item in meals[1:]:
                self.assertFalse(item.get("included_choices"))
                self.assertEqual(item["menu_options"][0]["total_price"],11)

    def test_shared_frontend_sorting(self):
        html=(ROOT/"index.html").read_text()
        self.assertIn("function mealPosition(item)",html)
        self.assertIn("const sorted=[...raw].sort((a,b)=>mealPosition(a)-mealPosition(b));",html)
        self.assertIn("menu_options||[]",html)

if __name__=="__main__":
    unittest.main()
