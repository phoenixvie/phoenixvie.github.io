"""Regressionstests für vier neu ergänzte Mittagsangebote (ohne externe Abrufe)."""
import unittest
from datetime import date
from update_menus import buffet_days,parse_topfdeckel,parse_gruenehuette,parse_lia_week

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

    def test_gruenehuette_spaces_in_date_and_stale_week(self):
        text="""<h2>TAGESTELLER / LUNCH SPECIAL 5.10. 2026</h2>
        <p>MO: Gulasch mit Serviettenknödel</p>
        <p>DI: Schnitzel mit Reis</p><p>MI: Huhn mit Erbsen</p>
        <p>DO: Spinatstrudel mit Sauce</p><p>FR: Fisch mit Erdäpfelsalat</p>"""
        with self.assertRaisesRegex(ValueError,"nicht von aktueller Woche"):
            parse_gruenehuette(text.encode(),MON)

    def test_gruenehuette_split_weekday_labels_and_menu_names(self):
        # Original-HTML kann Tageskürzel und Gericht in getrennten Elementen ausliefern.
        text="""<h2>TAGESTELLER / LUNCH SPECIAL 2. 11. 2026</h2>
        <p>MO:</p><p>Hühnerschnitzel mit Reis</p><b>Veggie:</b><p>Gebratene Erdäpfel mit Gemüse</p>
        <p>DI:</p><p>Faschierter Braten mit Püree</p>
        <p>MI:</p><p>Gebratene Hühnerkeule mit Gemüse</p>
        <p>DO:</p><p>Gebackener Fisch mit Salat</p>
        <p>FR:</p><p>Kabeljau mit Petersilerdäpfeln</p>"""
        data,_=parse_gruenehuette(text.encode(),MON)
        self.assertEqual(data["2026-11-02"][0]["name"],"Hühnerschnitzel mit Reis")
        self.assertEqual(data["2026-11-02"][1]["name"],"Gebratene Erdäpfel mit Gemüse")
        self.assertTrue(all(item["name"] for dishes in data.values() for item in dishes))
        self.assertEqual(len(data["2026-11-06"]),1)

    def test_lia_weekly_wu_section_dated_items_and_other_location_rejected(self):
        html="""<h2>Tagesmenü Lia Coffee am WU Campus</h2>
        <p>Hauptgericht € 10,00</p>
        <h3>Montag, 2.11.</h3><p>Gegrillte Hühnerkeule auf Couscous-Salat / Grilled chicken leg (ALO)</p>
        <p>€ 9,00 Quinoa-Salat mit Feta und Brot / Quinoa salad (AGLO) Veggie</p>
        <h3>Dienstag, 3.11.</h3>
        <p>Hühnerschnitzel mit Petersilkartoffeln / chicken schnitzel (ACGL)</p>
        <h3>Mittwoch, 4.11.</h3><p>Gebratener Reis mit Gemüse und Hühnerfleisch / rice (LO)</p>
        <h3>Donnerstag, 5.11.</h3><p>Gegrillte Hühnerbrust mit Reis / chicken with rice (L)</p>
        <h3>Freitag, 6.11.</h3><p>Gebackener Seelachs mit Erdäpfelpüree / fish (ACDGL)</p>
        <h2>Tagesmenü Lia Bistro</h2><h3>Donnerstag, 5.11.</h3>
        <p>Andere fremde Filiale mit anderem Gemüsegericht</p>"""
        days, validity=parse_lia_week(html.encode(),MON)
        self.assertEqual(validity[0],MON)
        self.assertEqual(len(days["2026-11-02"]),2)
        self.assertEqual(days["2026-11-02"][1]["price"],9.00)
        self.assertEqual(days["2026-11-05"][0]["price"],10.00)
        self.assertNotIn("fremde",str(days))

    def test_lia_bilingual_split_spans_and_separate_veg_price(self):
        html="""<h2>Tagesmenü Lia Coffee am WU Campus</h2>
        <h3>Donnerstag, 5.11.</h3>
        <p>Lasagne klassisch – mit Schwein und Rind /</p>
        <p>Lasagne classic style with beef and pork (AGLO)</p>
        <p>€ 9,00</p>
        <p>Gemüselasagne /</p>
        <p>Vegetable lasagna (AGLO) Veggie</p>
        <h2>Tagesmenü Lia Bistro</h2><p>Fremde Filiale</p>"""
        days,_=parse_lia_week(html.encode(),MON)
        items=days["2026-11-05"]
        self.assertEqual(len(items),2)
        self.assertEqual(items[0]["price"],10.00)
        self.assertEqual(items[1]["price"],9.00)
        self.assertEqual(items[1]["diet"],"veggie")
        self.assertEqual(items[1]["name"],"Gemüselasagne")

    def test_lia_stale_month_is_not_current_week(self):
        html="""<h2>Tagesmenü Lia Coffee am WU Campus</h2>
        <h3>Montag, 10.8.</h3>
        <p>Gegrillte Hühnerkeule auf Couscous-Salat / chicken (ALO)</p>
        <h2>Tagesmenü Lia Bistro</h2>
        <h3>Donnerstag, 5.11.</h3><p>Fremde Filiale</p>"""
        with self.assertRaisesRegex(ValueError,"kein gültiger Wochenplan"):
            parse_lia_week(html.encode(),MON)

if __name__=="__main__":unittest.main()
