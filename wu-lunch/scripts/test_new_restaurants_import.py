"""Offline verification of Karma HTML/PDF and Finn two-pass image validation."""
import importlib.util
from pathlib import Path
from datetime import date, datetime, timezone
from unittest.mock import patch
import unittest

spec=importlib.util.spec_from_file_location("new_restaurants",Path(__file__).with_name("update_new_restaurants.py"))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
MON=date(2026,11,2)
K_URL="https://cdn.shopify.com/s/files/1/111/files/Karma_Food_Mittagsmenu_KW45.pdf?v=1793300000"

def karma_fixture():
    days=["Montag","Dienstag","Mittwoch","Donnerstag","Freitag"]
    result=["<body><p>Karma Food 02.11.-07.11.</p>",
            f'<a href="{K_URL}">Menü als PDF herunterladen</a>']
    for i,day in enumerate(days):
        result.append(f"<h2>{day}</h2>")
        for j in range(3):
            dish=f"Gericht {i} Variation {j} mit Gewürzen"
            result.append(f"<h3>{dish}</h3><div>{'Special€11,50' if j == 2 else ''} Vegan Glutenfrei</div>")
    return ("".join(result)+"</body>").encode()

def finn_fixture(week=45, uploaded=date(2026,11,2), include_en=True):
    ts=int(datetime(uploaded.year,uploaded.month,uploaded.day,tzinfo=timezone.utc).timestamp())
    other=f'<img src="https://cdn.shopify.com/files/FINN_kw{week}e.jpg?v={ts}">' if include_en else ""
    return (f'<article><h1>Mittagsmenü</h1><img src="https://cdn.shopify.com/files/FINN_kw{week}.jpg?v={ts}">'
            +other+"</article>").encode()

def fin_result(price=10.0):
    rows=[]
    for i in range(5):
        d=(MON+module.timedelta(days=i)).isoformat()
        for kind in ("Vegan","Fleisch"):
            rows.append({"date":d,"name":f"{kind} Gericht mit Kartoffeln {i}",
                         "price_eur":price,"category":kind,"portion":None,
                         "included_items":[],"extra_costs":[],
                         "confidence":"high",
                         "source_url":"https://cdn.shopify.com/files/FINN_kw45.jpg?v=1793577600",
                         "evidence_excerpt":"Hauptgericht €10,00"})
    return {"status":"found","items":rows,"warnings":[]}

class NewRestaurantTests(unittest.TestCase):
    def test_karma_only_current_week_and_three_meals_per_day(self):
        rows,pdf=module.parse_karma_html(karma_fixture(),MON)
        self.assertEqual(sum(map(len,rows.values())),15)
        self.assertEqual(pdf,K_URL)
        self.assertEqual(rows["2026-11-02"][2]["category"],"Special")
        self.assertEqual(rows["2026-11-02"][1]["diet"],"vegan")
        with self.assertRaisesRegex(ValueError,"andere Woche"):
            module.parse_karma_html(karma_fixture(),date(2026,11,9))

    def test_karma_no_menu_when_pdf_missing(self):
        bad=karma_fixture().replace(b"Men\xc3\xbc als PDF herunterladen",b"Kein Preislink")
        with self.assertRaises(ValueError):
            module.parse_karma_html(bad,MON)

    def test_karma_pdf_crosschecks_dishes(self):
        days,_=module.parse_karma_html(karma_fixture(),MON)
        text=" ".join(item["name"] for day in days.values() for item in day)
        module.validate_karma_pdf_matches(days,text)
        with self.assertRaisesRegex(ValueError,"weichen voneinander"):
            module.validate_karma_pdf_matches(days,"Unrelated PDF Pasta and coffee")

    def test_finn_old_week_rejected_before_model_call(self):
        with self.assertRaisesRegex(ValueError,"noch nicht veröffentlicht"):
            module.select_finn_image(finn_fixture(44),MON)

    def test_finn_current_version_and_german_image_only(self):
        url=module.select_finn_image(finn_fixture(),MON)
        self.assertIn("FINN_kw45.jpg",url)
        self.assertNotIn("kw45e",url)
        with self.assertRaises(ValueError):
            module.select_finn_image(finn_fixture(45,date(2025,11,2)),MON)

    def test_finn_failed_same_image_not_retried_each_hour(self):
        import hashlib
        from unittest.mock import patch
        from datetime import timedelta
        today=datetime.now(module.TZ).date()
        monday=today-timedelta(days=today.weekday())
        image=b"\\xff\\xd8\\xff"+(b"X"*9000)
        previous={
            "last_attempt_at":today.isoformat()+"T07:00:00+01:00",
            "last_attempt_sha256":hashlib.sha256(image).hexdigest(),
        }
        html=finn_fixture(monday.isocalendar().week,monday)
        with patch.object(module.legacy,"safe_get",side_effect=lambda url,*args: html if url==module.FINN_URL else image):
            with self.assertRaisesRegex(ValueError,"bereits mit KI geprüft"):
                module.fetch_finn(monday,key="fake-key",previous=previous)

    def test_finn_pair_rejects_price_mismatch(self):
        first=fin_result(10.0); second=fin_result(11.0)
        with self.assertRaisesRegex(ValueError,"widersprechen"):
            module.validate_finn_pair(first,second,MON,first["items"][0]["source_url"])

    def test_finn_pair_rejects_missing_day_and_free_soup(self):
        first=fin_result();second=fin_result()
        first["items"]=first["items"][:-2]
        second["items"]=second["items"][:-2]
        with self.assertRaisesRegex(ValueError,"nicht alle fünf"):
            module.validate_finn_pair(first,second,MON,first["items"][0]["source_url"])
        first=fin_result();second=fin_result()
        first["items"][0]["included_items"]=["Suppe"]
        with self.assertRaisesRegex(ValueError,"Inklusiv"):
            module.validate_finn_pair(first,second,MON,first["items"][0]["source_url"])

    def test_finn_tiny_spelling_variant_keeps_second_model_reading(self):
        first=fin_result(); second=fin_result()
        first["items"][0]["name"]="Zanderfilet mit Salzeräpfel und Dillfisolen"
        second["items"][0]["name"]="Zanderfilet mit Salzerdäpfel und Dillfisolen"
        days=module.validate_finn_pair(first,second,MON,first["items"][0]["source_url"])
        self.assertTrue(any("Salzerdäpfel" in meal["name"] for meal in days["2026-11-02"]))

    def test_finn_different_dish_names_still_block(self):
        first=fin_result(); second=fin_result()
        first["items"][0]["name"]="Zanderfilet mit Kartoffeln"
        second["items"][0]["name"]="Schweinsbraten mit Knödel"
        with self.assertRaisesRegex(ValueError,"Gerichtnamen"):
            module.validate_finn_pair(first,second,MON,first["items"][0]["source_url"])

    def test_finn_missing_year_warning_allowed_but_incomplete_prices_blocked(self):
        first=fin_result(); second=fin_result()
        second["warnings"]=["Die Jahreszahl ist im Bild nicht angegeben."]
        days=module.validate_finn_pair(first,second,MON,first["items"][0]["source_url"])
        self.assertEqual(len(days),5)
        second["warnings"]=["Der Preis für Montag ist unklar."]
        with self.assertRaisesRegex(ValueError,"nicht eindeutig"):
            module.validate_finn_pair(first,second,MON,first["items"][0]["source_url"])

    def test_finn_pair_accepts_two_matching_models(self):
        first=fin_result();second=fin_result()
        days=module.validate_finn_pair(first,second,MON,first["items"][0]["source_url"])
        self.assertEqual(sum(len(x) for x in days.values()),10)
        self.assertEqual(days["2026-11-02"][0]["price"],10)

if __name__=="__main__":
    unittest.main()
