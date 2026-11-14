"""Publication safety regressions. No network or model billing."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import menu_sanity as sanity


def meal(**changes):
    return {'name': 'Plantbullar, Erdäpfelpüree, Röstzwiebel', 'price': 5.8,
            'category': 'Veggie', 'included_choices': ['Erdäpfelpüree', 'Röstzwiebel'],
            'description': 'Inklusive: Erdäpfelpüree, Röstzwiebel', **changes}


def menu(rows=None):
    return {'weekStart': '2026-11-16', 'restaurants': [{'id': 'mensa',
            'days': {'2026-11-16': rows or [meal()]}}]}


class MenuSanityTests(unittest.TestCase):
    def test_mensa_real_regression_removes_only_repeated_metadata(self):
        source = meal()
        clean = sanity.clean_item(source)
        self.assertEqual(clean['name'], source['name'])
        self.assertEqual(clean['price'], source['price'])
        self.assertEqual(clean['included_choices'], [])
        self.assertEqual(clean['description'], '')
        self.assertEqual(source['included_choices'], ['Erdäpfelpüree', 'Röstzwiebel'])
        self.assertEqual(sanity.clean_item(clean), clean)

    def test_real_extra_courses_and_unrelated_description_survive(self):
        source = meal(included_choices=['Erdäpfelpüree', 'Tagessuppe', 'Dessert'],
                      description='Inklusive: Erdäpfelpüree, Tagessuppe, Dessert | Zusatzkosten: Getränk 2 €')
        clean = sanity.clean_item(source)
        self.assertEqual(clean['included_choices'], ['Tagessuppe', 'Dessert'])
        self.assertEqual(clean['description'], 'Inklusive: Tagessuppe, Dessert | Zusatzkosten: Getränk 2 €')

    def test_similar_words_do_not_count_as_same_fact(self):
        source = meal(name='Salat mit Erdäpfelpüree', included_choices=['Erdäpfel', 'Salatdessert'], description='')
        self.assertEqual(sanity.clean_item(source), source)

    def test_unicode_punctuation_case_do_not_hide_duplicates_or_price_conflicts(self):
        source = sanity.clean_item(meal())
        duplicate = {**source, 'name': 'PLANTBULLAR | ERDÄPFELPÜREE | RÖSTZWIEBEL', 'price': 6.4}
        self.assertTrue(any('doppeltes Gericht' in issue for issue in sanity.row_issues([source, duplicate])))

    def test_distinct_stations_portions_and_menu_variants_survive(self):
        source = sanity.clean_item(meal())
        self.assertEqual(sanity.row_issues([source, {**source, 'category': 'Meaty'},
            {**source, 'portion': 'groß'}, {**source, 'included_choices': ['Tagessuppe']}]), [])
        data = menu([source])
        data['restaurants'][0]['days']['2026-11-17'] = [copy.deepcopy(source)]
        self.assertEqual(sanity.clean_menu(data)[2], [])

    def test_price_and_week_guards(self):
        for price in (True, -1, float('nan'), float('inf'), '5,80', 151):
            with self.subTest(price=price):
                self.assertTrue(sanity.row_issues([sanity.clean_item(meal(price=price))]))
        self.assertEqual(sanity.row_issues([sanity.clean_item(meal(price=None))]), [])
        data = menu()
        data['restaurants'][0]['days']['2026-11-23'] = [meal()]
        self.assertTrue(any('außerhalb' in x for x in sanity.clean_menu(data)[2]))

    def test_same_course_cannot_be_included_and_paid_extra(self):
        source = meal(name='Gemüsecurry', included_choices=['Tagessuppe'],
                      description='', extra_costs=['Tagessuppe +2 €'])
        self.assertTrue(any('Aufpreis' in x for x in sanity.row_issues([source])))

    def run_in_temp(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / 'data').mkdir()
        data = root / 'data/menus.json'
        data.write_text(json.dumps(menu()), encoding='utf-8')
        (root / 'data.js').write_text('original', encoding='utf-8')
        return tmp, root, data

    def test_luna_rejection_and_outage_do_not_write_menu_or_success_cache(self):
        for failure in ([{'restaurant': 'mensa', 'day': '2026-11-16', 'index': 0, 'reason': 'Widerspruch'}], RuntimeError('API nicht verfügbar')):
            tmp, root, data = self.run_in_temp()
            with tmp, patch.object(sanity, 'ROOT', root), patch.object(sanity, 'REPORT', root / 'data/report.json'), \
                 patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), \
                 patch.object(sanity, 'review_with_luna', **({'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure})):
                original = data.read_bytes()
                with self.assertRaises(ValueError):
                    sanity.run()
                self.assertEqual(data.read_bytes(), original)
                self.assertEqual((root / 'data.js').read_text(), 'original')
                report = json.loads((root / 'data/report.json').read_text())
                self.assertEqual(report['state'], 'blocked')
                self.assertEqual(report['reviewed'], {})

    def test_success_is_cached_but_price_change_requires_new_luna_review(self):
        tmp, root, data = self.run_in_temp()
        with tmp, patch.object(sanity, 'ROOT', root), patch.object(sanity, 'REPORT', root / 'data/report.json'), \
             patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), patch.object(sanity, 'review_with_luna', return_value=[]) as reviewer:
            sanity.run()
            self.assertEqual(reviewer.call_count, 1)
            self.assertEqual(json.loads(data.read_text())['restaurants'][0]['days']['2026-11-16'][0]['description'], '')
            sanity.run()
            self.assertEqual(reviewer.call_count, 1)
            changed = json.loads(data.read_text())
            changed['restaurants'][0]['days']['2026-11-16'][0]['price'] = 6.4
            data.write_text(json.dumps(changed))
            sanity.run()
            self.assertEqual(reviewer.call_count, 2)

    def test_offline_run_is_read_only_and_cannot_seed_ai_cache(self):
        tmp, root, data = self.run_in_temp()
        with tmp, patch.object(sanity, 'ROOT', root), patch.object(sanity, 'REPORT', root / 'data/report.json'), \
             patch.object(sanity, 'review_with_luna') as reviewer:
            original = data.read_bytes()
            sanity.run(offline=True)
            reviewer.assert_not_called()
            self.assertEqual(data.read_bytes(), original)
            self.assertFalse((root / 'data/report.json').exists())

    def test_model_must_confirm_all_reviewed_restaurants(self):
        def response(payload, status='completed'):
            obj = unittest.mock.Mock(status_code=200)
            obj.json.return_value = {'status': status, 'output': [{'type': 'message',
                'content': [{'type': 'output_text', 'text': json.dumps(payload)}]}]}
            return obj
        with patch.object(sanity.requests, 'post', return_value=response({'reviewed_restaurants': [], 'issues': []})):
            with self.assertRaises(ValueError):
                sanity.review_with_luna(menu()['restaurants'], '2026-11-16', 'test')
        with patch.object(sanity.requests, 'post', return_value=response({'reviewed_restaurants': ['mensa'], 'issues': []})):
            self.assertEqual(sanity.review_with_luna(menu()['restaurants'], '2026-11-16', 'test'), [])
        with patch.object(sanity.requests, 'post', return_value=response({}, status='incomplete')):
            with self.assertRaises(ValueError):
                sanity.review_with_luna(menu()['restaurants'], '2026-11-16', 'test')


if __name__ == '__main__':
    unittest.main()
