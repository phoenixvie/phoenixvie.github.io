"""Real KW47 PDF and synthetic merged-weekday regression guards, no API calls."""
import copy
import hashlib
import unittest
from datetime import date, timedelta
from pathlib import Path
import fitz
import update_mensa_ai as mensa

MON = date(2026, 11, 16)


class MensaMergedLayoutTests(unittest.TestCase):
    def test_absent_allergen_metadata_is_distinct_from_uncertain_or_omitted_codes(self):
        notice = 'Für die Tagesgerichte sind keine Allergene als Buchstabencodes angegeben.'
        result = {'items':[{'allergens':[]}]}
        self.assertTrue(mensa.confirmed_absent_allergen_notice(notice,result,'Klare Gemüsesuppe'))
        self.assertFalse(mensa.confirmed_absent_allergen_notice('Allergene nicht eindeutig angegeben',result,'Klare Gemüsesuppe'))
        self.assertFalse(mensa.confirmed_absent_allergen_notice(notice,result,'Klare Gemüsesuppe (A,C)'))
        self.assertFalse(mensa.confirmed_absent_allergen_notice(notice,{'items':[{'allergens':['A']}]},'Klare Gemüsesuppe'))
        self.assertFalse(mensa.confirmed_absent_allergen_notice(notice,result,'Allergene: A, C'))

    def test_actual_kw47_pdf_retains_weekday_dishes_and_shared_offer_panels(self):
        raw = (Path(__file__).parent/'fixtures/mensa-2026-11-16.pdf').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '1f8db507732cd8b3c15b4ff50234e7dc79181b107e7bda24b893bd4be3f7c061')
        mensa.independent_period(raw, MON)
        layout = mensa.pdf_layout(raw, MON)
        soup = next(row for row in layout if row['category'] == 'Tagessuppe')
        self.assertIn('Zwiebelcremesuppe', soup['cells']['2026-11-17'])
        self.assertNotIn('Zwiebelcremesuppe', soup['cells']['2026-11-16'])
        bowls = next(row for row in layout if row['category'] == 'Bowls & Co')
        self.assertEqual(bowls['scope'], 'whole_week')
        self.assertEqual(bowls['scope_basis'], 'shared_offer_panels')
        self.assertEqual(len(set(bowls['cells'].values())), 1)
        self.assertEqual(mensa.money_values(bowls['cells'][str(MON)]), {7.9, 2, 2.5, 4.25})
        pizza = next(row for row in layout if row['category'] == 'Pizza & Co')
        self.assertEqual(mensa.content_terms(pizza['cells']['2026-11-18']), set())
        core, _ = mensa.legacy.parse_mensa(raw, MON)
        self.assertEqual(len(core), 5)
        self.assertTrue(any('Honig' in row['name'] for row in core['2026-11-17']))

    def test_merged_weekday_groups_never_become_a_whole_week_offer(self):
        doc = fitz.open()
        p = doc.new_page(width=1050, height=590)
        for i, day in enumerate(mensa.legacy.WEEKDAYS):
            p.insert_text((250+i*153, 80), day.upper(), fontsize=10)
        centers = [(p.search_for(day.upper())[0].x0+p.search_for(day.upper())[0].x1)/2
                   for day in mensa.legacy.WEEKDAYS]
        edges = [centers[0]-(centers[1]-centers[0])/2] + [(a+b)/2 for a,b in zip(centers,centers[1:])] + [centers[-1]+(centers[-1]-centers[-2])/2]
        p.draw_rect(fitz.Rect(20, 100, 1030, 180), fill=(.8,.8,.8), color=None)
        p.insert_text((25, 140), 'Meaty', fontsize=10)
        for boundary in (2,4):
            x=edges[boundary]
            p.draw_rect(fitz.Rect(x-.1, 100, x+.1, 180), fill=(1,1,1), color=None)
        for start,name in [(0,'Gericht Alpha'),(2,'Gericht Beta'),(4,'Gericht Gamma')]:
            p.insert_text((edges[start]+5, 140), name, fontsize=9)
        layout = mensa.pdf_layout(doc.tobytes(), MON)
        doc.close()
        row = layout[0]
        self.assertEqual(row['scope'], 'merged_weekday_cells')
        self.assertEqual(list(row['cells'].values()), ['Gericht Alpha','Gericht Alpha','Gericht Beta','Gericht Beta','Gericht Gamma'])
        days = {day:[{'category':'Meaty','name':name,'description':'','price':None}]
                for day,name in row['cells'].items()}
        mensa.validate_layout(days, layout)
        wrong = copy.deepcopy(days)
        wrong['2026-11-19'] = wrong['2026-11-16']
        with self.assertRaisesRegex(ValueError, 'unvollständige Tabellenzelle'):
            mensa.validate_layout(wrong, layout)

