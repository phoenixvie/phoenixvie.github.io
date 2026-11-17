"""Wels-Ausgabe: Die Parser lesen die echten Seiten vom 17.11.2026 richtig und erfinden nichts.

Die Vorlagen unter fixtures/wels/ sind der sichtbare Text bzw. die Textpositionen
der Originalquellen dieses Tages.
"""
from datetime import date, datetime
from pathlib import Path
import json
import unittest

import update_wels as wels

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'wels'
MONDAY = date(2026, 11, 16)
read = lambda name: (FIXTURES / name).read_text(encoding='utf-8')
names = lambda rows: [row['name'] for row in rows]


class ParserTests(unittest.TestCase):
    def test_naschmarkt_two_daily_dishes_plus_weekly_star(self):
        days = wels.check(wels.parse_naschmarkt(read('naschmarkt-2026-11-17.txt'), MONDAY), MONDAY)
        self.assertEqual(len(days), 5)
        tuesday = days['2026-11-17']
        self.assertEqual([(row['name'], row['price']) for row in tuesday[:2]], [
            ('Hirschragout mit Kroketten und Rotkraut', 15.9),
            ('Gefüllte Zucchini mit Mozzarella gratiniert auf Tomatenragout dazu Erdäpfel', 12.9)])
        self.assertEqual((tuesday[2]['name'], tuesday[2]['price'], tuesday[2]['description']),
                         ('Schupfnudeln „Süß-Sauer“ mit Asiagemüse', 12.9, 'Star der Woche'))
        self.assertFalse(any('Wahlweise' in name for rows in days.values() for name in names(rows)))

    def test_inshaas_prices_follow_the_tariff_only_for_the_usual_pattern(self):
        days = wels.check(wels.parse_inshaas(read('inshaas-2026-11-17.txt'), MONDAY), MONDAY)
        self.assertEqual([(row['name'], row['price']) for row in days['2026-11-20']], [
            ('Ofenkabeljau / Kürbisgemüse / Kartoffelpüree', 12.5),
            ('Geschmorte Melanzani / Kirschtomatenragout / Basilikum / Parmesan', 11.9),
            ('Eiernudelsalat / Tempura Gemüse / Sprossen', 11.5),
            ('Tagessuppe', 4.9)])
        # Vertauschte Reihenfolge: lieber kein Einzelpreis als ein falsch zugeordneter.
        swapped = read('inshaas-2026-11-17.txt').replace(
            'Ofenkabeljau / Kürbisgemüse / Kartoffelpüree\nGeschmorte Melanzani / Kirschtomatenragout / Basilikum / Parmesan',
            'Geschmorte Melanzani / Kirschtomatenragout / Basilikum / Parmesan\nOfenkabeljau / Kürbisgemüse / Kartoffelpüree')
        friday = wels.parse_inshaas(swapped, MONDAY)['2026-11-20']
        self.assertEqual([row['price'] for row in friday[:3]], [None, None, None])
        self.assertIn('Vegetarisch 11,90 €', friday[0]['description'])

    def test_linde_shows_last_week_so_nothing_is_taken_for_this_week(self):
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_linde(read('linde-2026-11-17.txt'), MONDAY)
        previous = date(2026, 11, 9)
        days = wels.check(wels.parse_linde(read('linde-2026-11-17.txt'), previous), previous)
        self.assertEqual(sorted(days), ['2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13'])
        friday = days['2026-11-13'][0]   # die Seite lässt das Kürzel "Fr." weg
        self.assertEqual((friday['name'], friday['price'], friday['included_soup']),
                         ('Pochiertes Seehechtfilet auf Kürbis-Kartoffelgemüse mit Dillsauce', 14.8,
                          'Nudelsuppe oder Tagessuppe'))

    def test_linde_refuses_a_plan_whose_days_cannot_be_counted(self):
        broken = read('linde-2026-11-17.txt').replace('€ 14,80', '', 1)
        with self.assertRaises(ValueError):
            wels.parse_linde(broken, date(2026, 11, 9))

    def test_dokkhun_weekly_pdf_with_misspelled_weekday(self):
        days = wels.check(wels.parse_dokkhun(read('dokkhun-kw47.txt'), MONDAY), MONDAY)
        self.assertEqual(sorted(days), ['2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20'])
        thursday = days['2026-11-19']    # in der Karte steht "Donnertag"
        self.assertEqual([row['price'] for row in thursday], [14.5, 14.5])
        self.assertTrue(thursday[0]['name'].startswith('Spagetti Med Mamuang Gai'))
        self.assertEqual(thursday[0]['included_starter'], 'Gemischter Salat')
        self.assertEqual(thursday[0]['description'], 'Nur Hauptspeise: 1,00 € günstiger')
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_dokkhun(read('dokkhun-kw47.txt'), date(2026, 11, 23))

    def test_billa_poster_is_read_by_position_for_the_right_week(self):
        pages = json.loads(read('billa-kw47-48.json'))
        days = wels.check(wels.parse_billa(pages, MONDAY), MONDAY)
        self.assertEqual([(row['name'], row['price']) for row in days['2026-11-17']], [
            ('Gnocchi in Blattspinatrahmsauce dazu Kirschtomaten & frischer Parmesan', 8.4),
            ('Gefüllte Zucchini mit Faschiertem & Käse überbacken, dazu Petersilerdäpfel', 9.9)])
        self.assertEqual(days['2026-11-18'][1]['name'], 'Gebackenes Schnitzel vom Schwein, mit Reis')
        self.assertIn('Gericht kann je Filiale abweichen', days['2026-11-18'][1]['description'])
        self.assertEqual(days['2026-11-16'][0]['description'], 'Mit Suppe oder Dessert')
        following = wels.parse_billa(pages, date(2026, 11, 23))
        self.assertEqual(names(following['2026-11-27']), ['Kürbisstrudel mit Salatbouquet & Knoblauch-Rahm-Dip',
                                                          'Seelachs gebacken mit Erdäpfel-Vogerlsalat'])
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_billa(pages, date(2026, 11, 30))

    def test_menu_links_are_found_on_the_real_pages(self):
        links = read('links.html').encode('utf-8')
        self.assertTrue(wels.find_dokkhun_pdf(links, 'https://dok-khun.metro.biz/').endswith('/Menu-KW-47.pdf'))
        self.assertIn('Mittagsmenue_KW_47_48', wels.find_billa_pdf(links.split(b'<div id="billa">')[1], 'https://www.billa.at/'))
        with self.assertRaises(wels.NotThisWeek):
            wels.find_dokkhun_pdf(b'<a href="/Abendkarte.pdf">Abendkarte</a>', 'https://dok-khun.metro.biz/')


class SafetyTests(unittest.TestCase):
    def test_week_shown_matches_the_app(self):
        at = lambda day, hour=12: datetime(2026, 11, day, hour, tzinfo=wels.TZ)
        self.assertEqual(wels.target_week(at(17)), MONDAY)                 # Dienstag
        self.assertEqual(wels.target_week(at(20, 23)), MONDAY)             # Freitagabend
        self.assertEqual(wels.target_week(at(21, 1)), date(2026, 11, 23))  # Samstag: kommende Woche

    def test_implausible_results_are_rejected(self):
        good = {'2026-11-17': [{'name': 'Hirschragout', 'price': 15.9}]}
        self.assertEqual(wels.check(good, MONDAY), good)
        for bad in ({}, {'2026-11-24': good['2026-11-17']}, {'2026-11-17': []},
                    {'2026-11-17': [{'name': '12', 'price': 9.0}]}, {'2026-11-17': [{'name': 'Hirschragout', 'price': 159.0}]}):
            with self.assertRaises(ValueError):
                wels.check(bad, MONDAY)

    def build(self, previous, pages, now=datetime(2026, 11, 17, 9, tzinfo=wels.TZ)):
        def get(url):
            if url not in pages:
                raise OSError('nicht erreichbar: ' + url)
            return pages[url]
        return wels.build(previous, MONDAY, now, get)

    def test_failed_fetch_keeps_the_good_state_of_the_same_week_and_never_blocks_others(self):
        from unittest.mock import patch
        url = {row['id']: row['url'] for row in wels.RESTAURANTS}
        html = lambda name: ('<html><body><main>' + ''.join(
            f'<p>{line}</p>' for line in read(name).splitlines()) + '</main></body></html>').encode('utf-8')
        pages = {url['naschmarkt']: html('naschmarkt-2026-11-17.txt'), url['inshaas']: html('inshaas-2026-11-17.txt')}
        first = self.build(None, pages)
        by_id = lambda result: {row['id']: row for row in result['restaurants']}
        self.assertEqual([row['id'] for row in first['restaurants']], [row['id'] for row in wels.RESTAURANTS])
        self.assertEqual(by_id(first)['naschmarkt']['import']['state'], 'ok')
        self.assertEqual(len(by_id(first)['inshaas']['days']['2026-11-18']), 4)
        self.assertEqual(by_id(first)['billa']['import']['state'], 'error')      # nicht erreichbar: bleibt leer
        self.assertEqual(by_id(first)['billa']['days']['2026-11-17'], [])
        # Zweiter Lauf: Naschmarkt fällt aus – der gute Stand derselben Woche bleibt stehen.
        second = self.build(first, {url['inshaas']: pages[url['inshaas']]}, datetime(2026, 11, 17, 11, tzinfo=wels.TZ))
        self.assertEqual(by_id(second)['naschmarkt']['days'], by_id(first)['naschmarkt']['days'])
        self.assertEqual(by_id(second)['naschmarkt']['import']['state'], 'error')
        # Unveränderter Inhalt: Zeitstempel bleibt, damit kein leerer Commit entsteht.
        third = self.build(second, {url['inshaas']: pages[url['inshaas']]}, datetime(2026, 11, 17, 13, tzinfo=wels.TZ))
        self.assertEqual(third, second)
        # Neue Woche: alte Gerichte werden nicht in die neue Woche getragen.
        with patch.object(wels, 'fetch', side_effect=OSError('offline')):
            fresh = wels.build(second, date(2026, 11, 23), datetime(2026, 11, 21, 9, tzinfo=wels.TZ))
        self.assertTrue(all(not rows for row in fresh['restaurants'] for rows in row['days'].values()))
        self.assertEqual(sorted(fresh['restaurants'][0]['days'])[0], '2026-11-23')

    def test_published_file_is_valid_for_the_app(self):
        data = json.loads(wels.OUTPUT.read_text(encoding='utf-8'))
        self.assertRegex(data['weekStart'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertEqual([row['id'] for row in data['restaurants']], [row['id'] for row in wels.RESTAURANTS])
        for row in data['restaurants']:
            self.assertEqual(len(row['days']), 5)
            self.assertTrue(row['url'].startswith('https://'))

    def test_page_reuses_the_shared_app_code_instead_of_copying_it(self):
        folder = wels.OUTPUT.parent
        page = (folder / 'index.html').read_text(encoding='utf-8')
        self.assertIn('window.WU_FOOD_SITE', page)
        self.assertIn('src="../app.js', page)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ['index.html', 'menus.json'])
        self.assertNotIn('supabase', page.lower())


if __name__ == '__main__':
    unittest.main()
