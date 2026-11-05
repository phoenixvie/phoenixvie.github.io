"""Regressionstests für vier neu ergänzte Mittagsangebote (ohne externe Abrufe)."""
import unittest
from datetime import date
from update_menus import buffet_days,parse_topfdeckel,parse_gruenehuette,parse_lia

MON=date(2026,11,2)
THU=date(2026,11,5)

class NewRestaurantTests(unittest.TestCase):
    def test_oma_adult_buffet_and_friday_only_chinese(self):
        days=buffet_days(MON)
        self.assertEqual(len(days),5)
        self.assertEqual(days["2026-11-02"][0]["price"],10.90)
        self.assertNotIn("Chinesisch",days["2026-11-02"][0]["name"])
        self.assertIn("Chinesisch",days["2026-11-06"][0]["name"])

    def test_topf_dated_daily_menu(self):
        html="""<main><h2>Was heute auf den Teller kommt</h2>
        <p>Donnerstag, 5. November 2026</p><h2>Main Dish</h2>
        <p>€ 7,50</p><h3>Garnelen Zitronen Pasta mit Zucchini</h3>
        <h3>Ofenfrische Burritos mit Chili con Carne</h3>
        <h3>Cremiges Brokkoli Kokoscurry mit Erdnüssen</h3>
        <h2>Dessert</h2></main>"""
        items=parse_topfdeckel(html.encode(),THU,MON)
        self.assertEqual(len(items),5)
        self.assertEqual(items[0]["price"],7.50)
        self.assertEqual(items[-2]["price"],9.50)
        self.assertEqual(items[-1]["price"],13.90)
        with self.assertRaises(ValueError):
            parse_topfdeckel(html.encode(),date(2026,11,6),MON)

    def test_gruenehuette_week_and_optional_paid_soup(self):
        text="""<h2>TAGESTELLER / LUNCH SPECIAL 2.11.2026</h2>
        <p>Mo-Do 13,5 + Suppe 2,-</p>
        <p>MO: Hühnerschnitzel mit Reis</p><p>Veggie: Gemüse Curry mit Reis</p>
        <p>DI: Gebratenes Rindfleisch mit Gemüse</p>
        <p>MI: Faschierter Braten mit Kartoffelpüree</p>
        <p>DO: Gebackener Fisch mit Petersilerdäpfeln</p>
        <p>FR: Fischgericht mit Salat</p>"""
        days,_=parse_gruenehuette(text.encode(),MON)
        self.assertEqual(days["2026-11-02"][0]["price"],13.5)
        self.assertEqual(days["2026-11-06"][0]["price"],14.5)
        self.assertIn("Suppe optional +2",days["2026-11-02"][0]["description"])
        self.assertEqual(len(days["2026-11-02"]),2)
        with self.assertRaises(ValueError):
            parse_gruenehuette(text.encode(),date(2026,11,9))

    def test_lia_uses_only_wu_section_and_refuses_old_dates(self):
        html="""<h2>Tagesmenü Lia Coffee am WU Campus</h2>
        <p>Hauptgericht € 10,00</p><h3>Donnerstag, 5.11.</h3>
        <p>Gegrillte Hühnerkeule mit Tomaten-Paprika-Sauce und Reis / English translation</p>
        <p>Verfügbar von 11:30 bis 14:00 Uhr</p>
        <h2>Tagesmenü Lia Bistro</h2><h3>Donnerstag, 5.11.</h3>
        <p>Andere fremde Filiale mit anderem Gemüsegericht</p>"""
        items=parse_lia(html.encode(),THU)
        self.assertEqual(len(items),1)
        self.assertNotIn("fremde",items[0]["name"])
        with self.assertRaises(ValueError):
            parse_lia(html.encode(),date(2026,11,6))

if __name__=="__main__":unittest.main()
