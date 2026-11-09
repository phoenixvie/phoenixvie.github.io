"""Regression guards for the November 9 source-import failures; no API calls."""
import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import fitz
import update_menus as legacy
import update_mensa_ai as mensa
import update_new_restaurants as finn

MON = date(2026, 11, 9)


class RefreshTests(unittest.TestCase):
    def test_notice_confidence_never_allows_an_uncertain_real_dish(self):
        url='https://www.wumensa.at/menuplan-deutsch/'
        rows=[]
        for i in range(5):
            day=(MON+timedelta(days=i)).isoformat()
            for name,category,price,confidence in [('Faschierter Braten mit Reis','Meaty',6.4,'high'),('Soup Deal laut Tagesaushang','Soup Deal',4.25,'medium')]:
                rows.append({'date':day,'name':name,'category':category,'price_eur':price,'confidence':confidence,
                             'source_url':url,'evidence_excerpt':name,'allergens':[],'extra_costs':[]})
        result={'status':'found','warnings':[],'items':rows}
        text='Faschierter Braten mit Reis € 6,40 Soup Deal laut Tagesaushang € 4,25'
        days=mensa.validate_menu(result,text,MON,url)
        self.assertTrue(days[str(MON)][1]['details_unpublished'])
        self.assertEqual(days[str(MON)][1]['ai_confidence'],'medium')
        rows[0]['confidence']='medium'
        with self.assertRaisesRegex(ValueError,'unsichere Gerichtzuordnung'):
            mensa.validate_menu(result,text,MON,url)

    def test_quarantined_candidate_must_match_week_bytes_model_and_prompt(self):
        source={'url':'https://www.wumensa.at/menuplan-deutsch/','sha256':'verified-bytes'}
        record={'week_start':str(MON),'source':source,'model':'gpt-6-luna','extraction_version':mensa.EXTRACTION_VERSION,
                'result':{},'validated_by':mensa.REVIEW_VERSION}
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'candidate.json';path.write_text(json.dumps(record),encoding='utf-8')
            with patch.object(mensa,'CANDIDATE',path):
                self.assertIsNotNone(mensa.cached_candidate(MON,source,'gpt-6-luna'))
                self.assertIsNone(mensa.cached_candidate(MON,{**source,'sha256':'changed'},'gpt-6-luna'))
                self.assertIsNone(mensa.cached_candidate(MON+timedelta(days=7),source,'gpt-6-luna'))
                self.assertIsNone(mensa.cached_candidate(MON,source,'other-model'))

    def test_compound_spelling_needs_an_attested_other_component(self):
        self.assertTrue(mensa.same_source_word('erdäpfel','petersilerdäpfel',{'petersil','erdäpfel'}))
        self.assertFalse(mensa.same_source_word('erdäpfel','karottenerdäpfel',{'erdäpfel'}))
        self.assertTrue(mensa.same_source_word('cremiger','cremigem'))
        self.assertFalse(mensa.same_source_word('schweinsbraten','rindsbraten'))

    def test_changed_verified_pdf_can_remove_offers_but_same_pdf_cannot_shrink(self):
        days={(MON+timedelta(days=i)).isoformat():[{'name':'Verified new dish'}] for i in range(5)}
        old={day:rows+[{'name':'Removed in the new original PDF'}] for day,rows in days.items()}
        data={'restaurants':[{'id':'mensa','days':old}],'sources':[{'id':'mensa'}]}
        status={'mensa_luna_audit':{'source_sha256':'old'}}
        mensa.apply_candidate(copy.deepcopy(data),copy.deepcopy(status),days,MON,{'sha256':'new'}, {},'gpt-6-luna')
        with self.assertRaisesRegex(ValueError,'löschen'):
            mensa.apply_candidate(copy.deepcopy(data),copy.deepcopy(status),days,MON,{'sha256':'old'}, {},'gpt-6-luna')

    def test_pdf_category_continues_into_an_unlabelled_subrow(self):
        doc=fitz.open();p=doc.new_page(width=1050,height=590)
        for i,day in enumerate(legacy.WEEKDAYS):
            p.insert_text((250+i*153,80),day.upper(),fontsize=10)
        p.draw_rect(fitz.Rect(20,100,1030,180),fill=(.8,.8,.8),color=None)
        p.draw_rect(fitz.Rect(180,180,1030,210),fill=(.6,.6,.6),color=None)
        p.draw_rect(fitz.Rect(20,210,1030,300),fill=(.8,.8,.8),color=None)
        p.insert_text((25,140),'Pasta & Co',fontsize=10)
        p.insert_text((25,250),'Global & Grill',fontsize=10)
        centers=[(p.search_for(day.upper())[0].x0+p.search_for(day.upper())[0].x1)/2 for day in legacy.WEEKDAYS]
        for a,b in zip(centers,centers[1:]):
            x=(a+b)/2
            p.draw_rect(fitz.Rect(x-.1,100,x+.1,300),fill=(1,1,1),color=None)
        for i in range(5):
            p.insert_text((250+i*153,160),'Hausgemachte Pasta',fontsize=9)
            p.insert_text((250+i*153,200),'Spezialpasta laut Aushang',fontsize=9)
        layout=mensa.pdf_layout(doc.tobytes(),MON)
        doc.close()
        pasta=next(s for s in layout if s['category']=='Pasta & Co')
        self.assertEqual(pasta['scope'],'weekday_cells')
        self.assertTrue(all('Spezialpasta' in text for text in pasta['cells'].values()))

    def test_merged_weekly_row_requires_all_offers_and_prices_each_day(self):
        days={(MON+timedelta(days=i)).isoformat():[
            {'category':'Bowls & Co','name':'Bowl Wrap Salad','price':7.9,'description':'Special Topping +2,00 €; Fleisch Topping +2,50 €'},
            {'category':'Bowls & Co','name':'Salad Deal','price':4.25,'description':''}] for i in range(5)}
        layout=[{'category':'Bowls & Co','scope':'whole_week','tariff_text':'',
                 'cells':{day:'Bowl Wrap Salad € 7,90 Special Topping € 2,00 Fleisch Topping € 2,50 Salad Deal € 4,25' for day in days}}]
        mensa.validate_layout(days,layout)
        bad=copy.deepcopy(days)
        bad['2026-11-11'].pop()
        with self.assertRaisesRegex(ValueError,'fehlt'):
            mensa.validate_layout(bad,layout)
        bad=copy.deepcopy(days)
        bad['2026-11-10'][0]['price']=8.2
        with self.assertRaises(ValueError):
            mensa.validate_layout(bad,layout)
        soup={day:[{'category':'Soup Deal','name':'Soup Deal – Inhalt laut Tagesaushang','price':4.25,'description':''}] for day in days}
        mensa.validate_layout(soup,[{'category':'Soup Deal','scope':'whole_week','tariff_text':'Soup Deal € 4,25',
                                    'cells':{day:'laut Tagesaushang' for day in days}}])

    def test_campus_explicit_owner_tariffs_and_unknown_category(self):
        days = {str(MON): [legacy.make_item('Fleischgericht mit Reis', None, 'Menü 1'),
                          legacy.make_item('Gemüsegericht mit Reis', 99, 'Menü 2'),
                          legacy.make_item('Zusätzliche Suppe', 3, 'Suppe')]}
        legacy.apply_campus_prices(days)
        rows = days[str(MON)]
        self.assertEqual([x['price'] for x in rows], [13.9, 12.9, 3])
        self.assertEqual(rows[0]['price_source'], 'admin_tariff')
        self.assertEqual(rows[1]['diet'], 'veggie')

    def test_mensa_vector_row_starts_above_category_label(self):
        doc = fitz.open()
        page = doc.new_page(width=1050, height=590)
        page.insert_text((20, 30), '09.11.2026 - 13.11.2026')
        for label, top, bottom in [('Tagesuppe',100,160), ('Powered by plants',160,240),
                                   ('Meaty',240,330), ('Global & Grill',330,430)]:
            page.draw_rect(fitz.Rect(20,top,1030,bottom), color=None, fill=(.8,.8,.8))
            page.insert_text((25,(top+bottom)/2),label,fontsize=10)
        for i, day in enumerate(legacy.WEEKDAYS):
            x=250+i*153
            page.insert_text((x,80),day.upper(),fontsize=10)
            page.insert_text((x,125),'Klare Gemuesesuppe',fontsize=9)
            page.insert_text((x,180),'Penne Pomodoro',fontsize=9)
            page.insert_text((x,200),'Tomatensauce und Rucola',fontsize=9)
            page.insert_text((x,220),'5,80',fontsize=9)
            page.insert_text((x,260),'"One Pot" Beef mit Reis',fontsize=9)
            page.insert_text((x,300),'6,40',fontsize=9)
            page.insert_text((x,350),'Halbes Grillhuhn',fontsize=9)
            page.insert_text((x,390),'Reis und Natursaft',fontsize=9)
            page.insert_text((x,410),'9,80',fontsize=9)
        days,_=legacy.parse_mensa(doc.tobytes(),MON)
        doc.close()
        for rows in days.values():
            self.assertIn('Penne Pomodoro',rows[1]['name'])
            self.assertTrue(rows[2]['name'].startswith('"One Pot"'))
            self.assertIn('Halbes Grillhuhn',rows[3]['name'])
            self.assertEqual(rows[2]['price'],6.4)

    def test_finn_downloads_bytes_even_for_previously_verified_url(self):
        image=b'\xff\xd8\xff'+b'x'*9000
        url='https://cdn.shopify.com/files/FINN_kw46.jpg?v=1794150305'
        previous={'state':'ok','source_image':url,'content_sha256':hashlib.sha256(image).hexdigest(),
                  'review_version':finn.FINN_REVIEW_VERSION,'review_week_start':str(MON)}
        with patch.object(finn,'select_finn_image',return_value=url), patch.object(finn.legacy,'safe_get',side_effect=[b'html',image]) as get:
            self.assertIsNone(finn.fetch_finn(MON,key='',previous=previous)[0])
            self.assertEqual(get.call_count,2)
        with patch.object(finn,'select_finn_image',return_value=url), patch.object(finn.legacy,'safe_get',side_effect=[b'html',image+b'changed']):
            with self.assertRaisesRegex(ValueError,'OPENAI_API_KEY'):
                finn.fetch_finn(MON,key='',previous=previous)

    def test_mensa_cache_is_bound_to_bytes_week_and_validator_version(self):
        days={(MON+timedelta(days=i)).isoformat():[{'name':'Verified complete dish'}] for i in range(5)}
        data={'weekStart':str(MON),'restaurants':[{'id':'mensa','days':days}],'sources':[{'id':'mensa'}]}
        audit={'state':'ok','source_sha256':'old','week_start':str(MON),'version':mensa.REVIEW_VERSION,
               'published_days_sha256':mensa.days_digest(days)}
        status={'sources':{'mensa':{}},'mensa_luna_audit':audit,'problems':[]}
        with TemporaryDirectory() as tmp:
            dp,sp,jp=[Path(tmp)/x for x in ('menus.json','status.json','data.js')]
            dp.write_text(json.dumps(data),encoding='utf-8')
            sp.write_text(json.dumps(status),encoding='utf-8')
            with patch.multiple(mensa,DATA=dp,STATUS=sp,JS=jp), patch.object(mensa,'acquire_pdf',return_value=(b'pdf','text',{'url':'https://www.wumensa.at/menuplan-deutsch/','sha256':'old'})), patch.object(mensa,'extract_for_week') as extract:
                self.assertFalse(mensa.run(MON,'gpt-6-luna'))
                extract.assert_not_called()
            with patch.multiple(mensa,DATA=dp,STATUS=sp,JS=jp), patch.object(mensa,'acquire_pdf',return_value=(b'new pdf','text',{'url':'https://www.wumensa.at/menuplan-deutsch/','sha256':'new'})), patch.dict('os.environ',{'OPENAI_API_KEY':'fake-test-key'}), patch.object(mensa,'extract_for_week',side_effect=ValueError('test validation blocked')) as extract:
                self.assertFalse(mensa.run(MON,'gpt-6-luna'))
                extract.assert_called_once()
            self.assertEqual(json.loads(dp.read_text(encoding='utf-8')),data)
            self.assertEqual(json.loads(sp.read_text(encoding='utf-8'))['sources']['mensa']['state'],'error')


if __name__ == '__main__':
    unittest.main()
