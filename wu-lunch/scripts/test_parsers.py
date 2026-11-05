"""Offline Regressionstests für den Datumsfilter und die Mensa-PDF-Tabellen."""
import unittest
from datetime import date, timedelta
import fitz
from update_menus import (
    period, parse_campus, parse_glashaus, parse_baschly, parse_mensa,
    blank_days, make_item, weekly_cache_valid
)

MONDAY = date(2026, 11, 2)
DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]


class ParserTests(unittest.TestCase):
    def test_date_range_and_old_week(self):
        self.assertEqual(period("02.11.2026 - 06.11.2026"), (MONDAY, MONDAY+timedelta(days=4)))
        self.assertEqual(period("2. Nov. 2026 – 6. Nov. 2026"), (MONDAY, MONDAY+timedelta(days=4)))
        self.assertNotEqual(period("26.10.2026 - 30.10.2026"), (MONDAY, MONDAY+timedelta(days=4)))
        self.assertEqual(period("03.08 bis 07.08.2026"), (date(2026,8,3),date(2026,8,7)))
        self.assertEqual(period("2. Nov - 6. Nov 2026"),(MONDAY,MONDAY+timedelta(days=4)))

    def test_campus_week(self):
        text='<h1>MITTAGSMENÜS</h1><p>02.11.2026 - 05.11.2026</p>'
        for d in DAYS[:4]:
            text += f'<h2>{d}</h2><p>Gebackenes Hühnerschnitzel mit Kartoffeln</p><p>ACGLO</p><p>Kichererbsengulasch mit Gemüse und Reis</p><p>AGLO</p>'
        data,valid = parse_campus(text.encode(), MONDAY)
        self.assertEqual(len(data["2026-11-05"]), 2)
        self.assertEqual(valid[0], MONDAY)

    def test_glashaus_week_with_soup_info(self):
        text='<h1>Mittagsmenüs</h1><p>Jeweils mit Suppe oder Salat</p><p>Vegetarisch € 14,90 / Fisch&Fleisch € 15,90</p><p>2. Nov. 2026 - 6. Nov. 2026</p>'
        for d in DAYS:
            text += f'<h2>{d}</h2><p>FEIERTAG</p><p>Gemüse-Curry mit Basmatireis</p><p>AGLO</p><p>Hühner-Piccata mit Tomatenspaghetti</p><p>ACGLO</p>'
        data,_=parse_glashaus(text.encode(),MONDAY)
        self.assertEqual(data["2026-11-05"][0]["price"],14.9)
        self.assertEqual(len(data["2026-11-03"]),2)

    def test_baschly_keeps_undated_separate(self):
        text='<h2>Lunch Special Veggie</h2><p>€ 9,50</p><h2>Das Angebot dieser Woche</h2>'
        for d in DAYS:
            text+=f'<h3>{d}</h3><p>Kichererbsen-Curry mit Basmatireis und Gemüse</p><p>A, G</p>'
        text+='<h2>Beilage</h2><p>mit kleinem Salat</p>'
        data=parse_baschly(text.encode(),MONDAY)
        self.assertEqual(len(data["2026-11-05"]),1)
        self.assertEqual(data["2026-11-02"][0]["price"],9.5)

    def test_baschly_product_new_format_soup_and_main(self):
        text='<h2>Lunch Special mit Fleisch</h2><p>€ 9,50</p><h3>Angebot der Woche</h3>'
        for d in DAYS:
            text+=f'<h3>{d}</h3><p>Tagessuppe: Gemüse-Cremesuppe</p><p>Hauptgericht: Gebratener Eierreis mit Crispy Chicken</p>'
        text+='<h3>Beilage</h3><p>mit kleinem Salat</p>'
        data=parse_baschly(text.encode(),MONDAY,meat=True)
        self.assertEqual(len(data["2026-11-05"]),1)
        self.assertEqual(data["2026-11-05"][0]["name"],"Gebratener Eierreis mit Crispy Chicken")

    @staticmethod
    def make_pdf(valid="02.11.2026 - 06.11.2026"):
        doc=fitz.open();p=doc.new_page(width=1050,height=590)
        p.insert_text((20,30),"Speiseplan KW 45",fontsize=11)
        p.insert_text((20,45),valid,fontsize=11)
        xs=[250,403,556,709,862]
        for i,name in enumerate(DAYS):
            p.insert_text((xs[i],80),name.upper(),fontsize=10)
        for label,y in [("Tagesuppe",120),("Powered by plants",185),("Meaty",295),
                        ("Global & Grill",385),("Pizza & Co",495)]:
            p.insert_text((25,y),label,fontsize=11)
        for x in xs:
            p.insert_text((x,143),"Klare Gemuesesuppe mit Einlage",fontsize=9)
            p.insert_text((x,210),"Linsen Dal mit Basmatireis",fontsize=9)
            p.insert_text((x,230),"€ 5,80",fontsize=9)
            p.insert_text((x,320),"Gebackenes Huehnerschnitzel",fontsize=9)
            p.insert_text((x,340),"€ 6,20",fontsize=9)
        raw=doc.tobytes();doc.close()
        return raw

    def test_pdf_columns_and_week_validation(self):
        data,valid=parse_mensa(self.make_pdf(),MONDAY)
        self.assertEqual(valid[0],MONDAY)
        self.assertEqual(len(data["2026-11-05"]),3)
        self.assertEqual(data["2026-11-05"][1]["category"],"Powered by plants / Veggie")
        with self.assertRaises(ValueError):
            parse_mensa(self.make_pdf("26.10.2026 - 30.10.2026"),MONDAY)

    def test_weekly_cache(self):
        dates=blank_days(MONDAY)
        for d in dates:
            dates[d]=[make_item("Gebackenes Schnitzel mit Kartoffeln",6.5,"Meaty"),
                      make_item("Gemüse Curry mit Reis",5.8,"Veggie"),
                      make_item("Gemüsesuppe mit Einlage",None,"Tagessuppe")]
        data={"weekStart":MONDAY.isoformat(),"restaurants":[{"id":"mensa","status":"verified",
             "validFrom":"2026-11-02","validUntil":"2026-11-06","days":dates}]}
        self.assertTrue(weekly_cache_valid(data,"mensa",MONDAY))
        self.assertFalse(weekly_cache_valid(data,"mensa",MONDAY+timedelta(days=7)))


if __name__=="__main__":
    unittest.main()
