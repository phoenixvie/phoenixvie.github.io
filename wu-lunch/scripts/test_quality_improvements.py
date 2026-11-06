"""Regression tests for price integrity and weekly-source fallback."""
import unittest
from datetime import date
from update_menus import parse_topfdeckel_week, parse_lia_week

class PriceAndFallbackTests(unittest.TestCase):
    def test_topf_weekly_monday_has_distinct_portions(self):
        raw="""<html><body><main><h1>Wochenmenü</h1>
        <p>9. November – 13. November 2026</p>
        <h2>Vorspeisen</h2><p>Klein €3.90 / Gross €5.90</p>
        <h3>Gemüsecremesuppe</h3><h3>Haussalat</h3>
        <h2>Hauptspeisen</h2>
        <h3>Süßkartoffel-Risotto mit Pilzen und Parmesan</h3>
        <p>Veggie</p><h3>Curry mit Kichererbsen und Reis</h3>
        <p>Allergene: A, G</p><h2>Dessert</h2></main></body></html>""".encode()
        with self.assertRaisesRegex(ValueError,"aktiver Wochentag nicht verifizierbar"):
            parse_topfdeckel_week(raw,date(2026,11,10),date(2026,11,9))
        with self.assertRaises(ValueError):
            parse_topfdeckel_week(raw,date(2026,11,9),date(2026,11,16))

    def test_lia_no_imaginary_default_price(self):
        html="""<html><body><h2>Tagesmenü Lia Coffee am WU Campus</h2>
        <h4>Montag, 9.11.</h4><p>Ofengemüse mit Salzkartoffeln und Sauce</p>
        <h4>Dienstag, 10.11.</h4><p>Rotes Curry mit Gemüse und Basmatireis</p>
        <h2>Tagesmenü Lia Bistro</h2></body></html>""".encode()
        days,_=parse_lia_week(html,date(2026,11,9))
        self.assertIsNone(days["2026-11-09"][0]["price"])
        self.assertIsNone(days["2026-11-10"][0]["price"])

if __name__=="__main__":
    unittest.main()
