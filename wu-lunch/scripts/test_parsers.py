"""Offline Regressionstests für den Datumsfilter und die Mensa-PDF-Tabellen."""
import unittest
from datetime import date, timedelta
import fitz
from update_menus import (
    period, parse_campus, parse_glashaus, parse_baschly, parse_mensa,
    blank_days, make_item, weekly_cache_valid, compare_verified_week, menu_fingerprint, candidate_quality_gate, pdf_cell_word_lines
)

MONDAY = date(2026, 11, 2)
DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]


class ParserTests(unittest.TestCase):
    def test_saturday_targets_following_menu_week(self):
        from update_menus import target_week_monday
        self.assertEqual(target_week_monday(date(2026,11,7)),date(2026,11,9))
        self.assertEqual(target_week_monday(date(2026,11,8)),date(2026,11,9))
        self.assertEqual(target_week_monday(date(2026,11,6)),MONDAY)

    def test_date_range_and_old_week(self):
        self.assertEqual(period("02.11.2026 - 06.11.2026"), (MONDAY, MONDAY+timedelta(days=4)))
        self.assertEqual(period("2. Nov. 2026 – 6. Nov. 2026"), (MONDAY, MONDAY+timedelta(days=4)))
        self.assertNotEqual(period("26.10.2026 - 30.10.2026"), (MONDAY, MONDAY+timedelta(days=4)))
        self.assertEqual(period("03.08 bis 07.08.2026"), (date(2026,8,3),date(2026,8,7)))
        self.assertEqual(period("2. Nov - 6. Nov 2026"),(MONDAY,MONDAY+timedelta(days=4)))
        self.assertEqual(period("2. Nov. 2026\n6. Nov. 2026"),(MONDAY,MONDAY+timedelta(days=4)))

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
        self.assertEqual(data["2026-11-05"][0]["included_choices"],["Suppe","Salat"])
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
        self.assertEqual(data["2026-11-05"][0]["included_soup"],"Gemüse-Cremesuppe")
        self.assertEqual(data["2026-11-05"][0]["included_choices"],["Tagessuppe","kleiner Salat"])
        self.assertTrue(all(x[0]["included_soup"] for x in data.values()))

    def test_baschly_real_source_layout_preserves_named_soup_and_choice(self):
        text='<h2>Lunch Special Veggie</h2><p>€9,50</p><h2>Das Angebot dieser Woche</h2>'
        soups=["Thai-Tomatensuppe","Fenchelsuppe","Französische Zwiebelsuppe",
               "Karotten-Orangen-Suppe","Gemüse-Cremesuppe"]
        for d,soup in zip(DAYS,soups):
            text+=f'<h3>{d}</h3><p>Tagessuppe: {soup}</p><p>Hauptgericht: Thai-Kokos-Gemüse-Curry mit Reis</p>'
        text+='<h2>Beilage</h2><p>mit kleinem Salat</p><p>mit Suppe des Tages</p>'
        data=parse_baschly(text.encode(),MONDAY)
        self.assertEqual(data["2026-11-02"][0]["included_soup"],"Thai-Tomatensuppe")
        self.assertEqual(data["2026-11-04"][0]["included_soup"],"Französische Zwiebelsuppe")
        self.assertEqual(data["2026-11-05"][0]["included_choices"],["Tagessuppe","kleiner Salat"])

    def test_baschly_missing_one_named_soup_rejected(self):
        text='<h2>Lunch Special Veggie</h2><p>€9,50</p><h3>Angebot der Woche</h3>'
        for d in DAYS:
            text+=f'<h3>{d}</h3>'
            if d!='Mittwoch': text+='<p>Tagessuppe: Gemüsesuppe</p>'
            text+='<p>Hauptgericht: Hausgemachte Falafel mit Hummus und Reis</p>'
        with self.assertRaisesRegex(ValueError,"Tagessuppen fehlen"):
            parse_baschly(text.encode(),MONDAY)

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
            p.insert_text((x,143),"Klare Gemuesesuppe",fontsize=9)
            p.insert_text((x,210),"Linsen Dal mit Reis",fontsize=9)
            p.insert_text((x,230),"€ 5,80",fontsize=9)
            p.insert_text((x,320),"Huehnerfleisch mit Reis",fontsize=9)
            p.insert_text((x,340),"€ 6,20",fontsize=9)
        raw=doc.tobytes();doc.close()
        return raw

    def test_pdf_word_cell_does_not_mix_neighboring_days(self):
        doc=fitz.open()
        page=doc.new_page(width=720,height=200)
        page.insert_text((125,82),"Klare Gemuese Suppe",fontsize=10)
        page.insert_text((325,82),"Tomatencremesuppe",fontsize=10)
        monday_cell=pdf_cell_word_lines(page,100,300,65,110)
        tuesday_cell=pdf_cell_word_lines(page,300,510,65,110)
        self.assertIn("Klare", " ".join(x[2] for x in monday_cell))
        self.assertNotIn("Tomaten", " ".join(x[2] for x in monday_cell))
        self.assertIn("Tomaten", " ".join(x[2] for x in tuesday_cell))
        doc.close()

    def test_pdf_columns_and_week_validation(self):
        data,valid=parse_mensa(self.make_pdf(),MONDAY)
        self.assertEqual(valid[0],MONDAY)
        self.assertEqual(len(data["2026-11-05"]),3)
        self.assertEqual(data["2026-11-05"][1]["category"],"Powered by plants / Veggie")
        self.assertTrue(data["2026-11-05"][0]["name"].startswith("Klare"))
        broken_start,valid = parse_mensa(self.make_pdf("02..2026 - 06.11.2026"),MONDAY)
        self.assertEqual(valid[0],MONDAY)
        self.assertGreaterEqual(sum(len(v) for v in broken_start.values()),10)
        with self.assertRaises(ValueError):
            parse_mensa(self.make_pdf("26.10.2026 - 30.10.2026"),MONDAY)

    def test_corrupt_pdf_will_not_replace_trusted_week(self):
        trusted=blank_days(MONDAY); corrupt=blank_days(MONDAY)
        for d in trusted:
            trusted[d]=[make_item("Klare Gemüsesuppe mit Einlage",None,"Tagessuppe"),
                        make_item("Spinatlasagne mit Knoblauchsauce",5.8,"Powered by plants / Veggie"),
                        make_item("Gebackenes Hühnerschnitzel mit Kartoffeln",6.4,"Meaty")]
            corrupt[d]=[make_item("esuppe Einlage Selleriecreme",None,"Tagessuppe"),
                        make_item("ne leichte Kichererbsen ahmsauce Curry",5.8,"Powered by plants / Veggie"),
                        make_item("tter Chicken Erdäpfel Würstl",6.4,"Meaty")]
        with self.assertRaises(ValueError):
            compare_verified_week(trusted,corrupt)

    def test_content_change_detection_ignores_script_attributes(self):
        x=b'<html><script>timestamp=1</script><main>Montag Gulasch mit Reis</main></html>'
        y=b'<html><script>timestamp=2</script><main>Montag Gulasch mit Reis</main></html>'
        z=b'<html><script>timestamp=2</script><main>Montag Gemuesecurry mit Reis</main></html>'
        self.assertEqual(menu_fingerprint(x),menu_fingerprint(y))
        self.assertNotEqual(menu_fingerprint(x),menu_fingerprint(z))

    def test_candidate_protects_cached_week_against_missing_dishes(self):
        good=blank_days(MONDAY)
        bad=blank_days(MONDAY)
        for d in good:
            good[d]=[make_item('Saftiges Curry mit Reis',12.9,'Fleisch'),
                     make_item('Gemueselasagne mit Sauce',12.9,'Veggie')]
        bad['2026-11-02']=[make_item('Curry mit Reis',12.9,'Fleisch')]
        with self.assertRaisesRegex(ValueError,'weniger Gerichte'):
            candidate_quality_gate('glashaus',good,bad)
        self.assertTrue(candidate_quality_gate('glashaus',good,good))

    def test_candidate_rejects_malformed_price_and_text(self):
        valid=blank_days(MONDAY)
        valid['2026-11-02']=[make_item('Erdäpfel mit Gemüse',500,'Veggie')]
        with self.assertRaisesRegex(ValueError,'Preis'):
            candidate_quality_gate('lia',blank_days(MONDAY),valid)

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
