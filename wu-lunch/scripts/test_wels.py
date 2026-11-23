"""Wels-Ausgabe: Die Parser lesen die echten Seiten vom 17.11.2026 richtig und erfinden nichts.

Die Vorlagen unter fixtures/wels/ sind der sichtbare Text bzw. die Textpositionen
der Originalquellen dieses Tages.
"""
from datetime import date, datetime
from pathlib import Path
import json
import re
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


class SecondListTests(unittest.TestCase):
    """Zweite Liste des Betreibers (17.11.2026): neun weitere Restaurants."""

    def test_no_restaurant_twice_and_list_is_alphabetical(self):
        ids = [row['id'] for row in wels.RESTAURANTS]
        labels = [row['name'] for row in wels.RESTAURANTS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(ids), 14)
        self.assertEqual(labels, sorted(labels, key=lambda name: name.replace("'", '').casefold()))

    def test_imturm_one_price_covers_soup_main_salad_and_dessert(self):
        days = wels.check(wels.parse_imturm(read('imturm-2026-11-17.txt'), MONDAY), MONDAY)
        tuesday = days['2026-11-17']
        self.assertEqual(names(tuesday), ['Paprikahenderl / Gemüsevariation / Butterreis', 'Fleckerlspeis',
                                          'Kürbisknödel / Nussbutter'])
        self.assertEqual({(row['price'], row['included_soup'], row['description']) for row in tuesday},
                         {(13.4, 'Kartoffelcremesuppe', 'Mit Salatbuffet und Dessert')})
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_imturm(read('imturm-2026-11-17.txt'), date(2026, 11, 23))

    def test_hannibal_tariff_prices_and_friday_burgers(self):
        days = wels.check(wels.parse_hannibal(read('hannibal-2026-11-17.txt'), MONDAY), MONDAY)
        self.assertEqual([(row['name'], row['price']) for row in days['2026-11-17']], [
            ('Geschmorter Rindsbraten | Butterspätzle | Ofengemüse', 12.0), ('Polentaknödel | Peperonata', 11.5)])
        self.assertEqual([row['price'] for row in days['2026-11-20']], [13.9, 13.9])
        self.assertFalse(any('Lammrücken' in name for rows in days.values() for name in names(rows)))  # Abendkarte
        swapped = read('hannibal-2026-11-17.txt').replace(
            'Geschmorter Rindsbraten | Butterspätzle | Ofengemüse\noder\nPolentaknödel | Peperonata',
            'Polentaknödel | Peperonata\noder\nGeschmorter Rindsbraten | Butterspätzle | Ofengemüse')
        unsure = wels.parse_hannibal(swapped, MONDAY)['2026-11-17']
        self.assertEqual([row['price'] for row in unsure], [None, None])
        self.assertIn('Fleischgericht 12,00 €', unsure[0]['description'])

    def test_lalina_takes_only_the_newest_lunch_block(self):
        days = wels.check(wels.parse_lalina(read('lalina-2026-11-17.txt'), MONDAY), MONDAY)
        self.assertEqual(sorted(days), ['2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20'])
        self.assertEqual([(row['name'], row['price']) for row in days['2026-11-20']], [
            ('Hühnerkeule mit Kartoffeln – Zimtwaffeln', 14.9),
            ('Gefüllte Palatschinken in Tomatensauce dazu Kartoffeln', 14.9)])
        self.assertFalse(any('Emmentaler-Burger' in name for rows in days.values() for name in names(rows)))  # Vorwoche

    def test_ox_card_without_date_is_read_once_although_the_page_repeats_it(self):
        days = wels.check(wels.parse_ox(read('ox-2026-11-17.txt'), MONDAY), MONDAY)
        self.assertEqual(sorted(days), ['2026-11-16', '2026-11-17', '2026-11-18', '2026-11-19'])
        self.assertEqual([(row['name'], row['price'], row['included_starter']) for row in days['2026-11-18']], [
            ('Cheeseburger | Wedges', 12.9, 'Tagessuppe oder Salat'),
            ('Gemüsereis | Eis | Soja | Ingwer', 12.9, 'Tagessuppe oder Salat')])

    def test_dokkhun_period_without_year_week_starting_on_tuesday_and_dessert(self):
        # KW 48/2026: "(24. November – 27. November)" ohne Jahreszahl – die Karte fiel deshalb ganz aus.
        week = date(2026, 11, 23)
        days = wels.check(wels.parse_dokkhun(read('dokkhun-kw48.txt'), week), week)
        self.assertEqual(sorted(days), ['2026-11-24', '2026-11-25', '2026-11-26', '2026-11-27'])
        self.assertEqual([(row['name'][:22], row['price']) for row in days['2026-11-24']],
                         [('Gai Pad Kratherm (gebr', 14.5), ('Bla Pad Künchai (Buntb', 15.5)])
        thursday = days['2026-11-26']
        self.assertTrue(all('Schoko-Kirschkuchen' in row['description'] and 'Kirschkuchen' not in row['name'] for row in thursday))
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_dokkhun(read('dokkhun-kw48.txt'), date(2026, 11, 30))

    def test_dokkhun_without_any_period_uses_the_calendar_week_of_the_file_name(self):
        week = date(2026, 11, 23)
        text = read('dokkhun-kw48.txt').replace('(24. November – 27. November)', '')
        self.assertEqual(wels.dokkhun_week('https://cdn.website.dish.co/media/10/2c/10307750/Menu-KW-48.pdf'), 48)
        self.assertEqual(len(wels.parse_dokkhun(text, week, 48)), 4)
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_dokkhun(text, week, 47)
        with self.assertRaisesRegex(ValueError, 'Zeitraum'):
            wels.parse_dokkhun(text, week)

    def test_period_without_year_and_across_new_year(self):
        self.assertEqual(wels.period_of('24. November – 27. November', date(2026, 11, 23)), (date(2026, 11, 24), date(2026, 11, 27)))
        self.assertEqual(wels.period_of('28. Dezember – 3. Jänner', date(2026, 12, 28)), (date(2026, 12, 28), date(2027, 1, 3)))
        self.assertEqual(wels.period_of('28. Dezember – 3. Jänner 2027', date(2026, 12, 28)), (date(2026, 12, 28), date(2027, 1, 3)))
        self.assertIsNone(wels.period_of('Montag – Freitag von 11:30 bis 14:00 Uhr', date(2026, 11, 23)))
        self.assertEqual(wels.period_of('24. Nov. – 27. Nov.', date(2026, 11, 23)), (date(2026, 11, 24), date(2026, 11, 27)))
        self.assertEqual(wels.long_date('4. Jänner 2027'), date(2027, 1, 4))

    def test_ox_dated_card_with_one_price_in_the_head(self):
        # Seit KW 48/2026: Zeitraum und "ab € 13,90" im Kopf, kein Preis mehr je Tag – vorher "keine Tage erkannt".
        week = date(2026, 11, 23)
        days = wels.check(wels.parse_ox(read('ox-2026-11-23.txt'), week), week)
        self.assertEqual([len(days[day]) for day in sorted(days)], [2, 2, 2, 2, 1])
        self.assertEqual([(row['name'], row['price'], row['included_starter'], row['description']) for row in days['2026-11-27']],
                         [('Gegrilltes Lachsfilet auf Tomaten-Basilikum-Risotto', 13.9, 'Klare Rindsuppe mit Profiteroles', 'Mittagsmenü ab € 13,90')])
        self.assertFalse(any('Steaks' in row['name'] or row['name'] == 'OX' for rows in days.values() for row in rows))
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_ox(read('ox-2026-11-23.txt'), date(2026, 11, 30))

    def test_fallback_reader_reads_dated_cards_of_any_layout_and_refuses_without_week_proof(self):
        # Maßstab: die echten Seiten vom 17.11. und 23.11.2026, gelesen ohne Wissen über das jeweilige Lokal.
        week47, week48 = date(2026, 11, 16), date(2026, 11, 23)
        ox = wels.check(wels.generic_week(read('ox-2026-11-23.txt'), week48), week48)
        self.assertEqual([names(ox[day]) for day in sorted(ox)][-1],
                         ['Klare Rindsuppe mit Profiteroles', 'Gegrilltes Lachsfilet auf Tomaten-Basilikum-Risotto'])
        self.assertEqual(len(ox), 5)
        market = wels.generic_week(read('naschmarkt-2026-11-17.txt'), week47)
        self.assertEqual([(row['name'], row['price']) for row in market['2026-11-17']], [
            ('Hirschragout mit Kroketten und Rotkraut', 15.9),
            ('Gefüllte Zucchini mit Mozzarella gratiniert auf Tomatenragout dazu Erdäpfel', 12.9)])
        thai = wels.generic_week(read('dokkhun-kw48.txt'), week48)
        self.assertEqual([(row['name'][:16], row['price']) for row in thai['2026-11-24']],
                         [('Gemischter Salat', None), ('Gai Pad Kratherm', 14.5), ('Bla Pad Künchai ', 15.5)])
        self.assertTrue(thai['2026-11-24'][1]['name'].endswith('Knoblauchsauce, Gemüse, Reis)'))  # umbrochene Zeile
        self.assertEqual([(row['name'][:20], row['price']) for row in thai['2026-11-26']][:2],
                         [('Pad Krapao Pak Ruam ', 15.5), ('Kauw Pad Kiaw Wan Ga', 14.5)])   # Preis vor dem Gericht
        linde = wels.generic_week(read('linde-2026-11-17.txt'), date(2026, 11, 9))
        self.assertEqual((linde['2026-11-10'][1]['name'], linde['2026-11-10'][1]['price']),
                         ('Surbraten vom Schopf mit Kartoffeln und Krautsalat', 14.8))
        self.assertEqual(len(wels.generic_week(read('dokkhun-kw47.txt'), week47)), 4)        # "Donnertag"
        everything = [name for text, week in ((read('ox-2026-11-23.txt'), week48), (read('imturm-2026-11-17.txt'), week47),
                                              (read('inshaas-2026-11-17.txt'), week47), (read('hannibal-2026-11-17.txt'), week47))
                      for rows in wels.generic_week(text, week).values() for name in names(rows)]
        self.assertFalse([name for name in everything if re.search(r'@|Uhr|reserv|©|Steaks & Grill|Öffnungs', name, re.I)])
        # Ohne Datum oder Zeitraum wird nichts gezeigt; eine andere Woche wird als solche erkannt.
        with self.assertRaisesRegex(ValueError, 'kein Beleg'):
            wels.generic_week(read('ox-2026-11-17.txt'), week47)
        with self.assertRaises(wels.NotThisWeek):
            wels.generic_week(read('ox-2026-11-23.txt'), date(2026, 11, 30))
        with self.assertRaises(wels.NotThisWeek):
            wels.generic_week(read('naschmarkt-2026-11-17.txt'), week48)
        with self.assertRaises(ValueError):
            wels.generic_week(read('huber-2026-11-17.txt'), week47)

    def test_fallback_steps_in_when_the_own_reader_fails_and_never_replaces_a_good_state(self):
        now = datetime(2026, 11, 23, 9, 0, tzinfo=wels.TZ)
        page = ('<html><body><h1>Mittagsmenü</h1><p>23. November – 27. November 2026</p>'
                + ''.join(f'<h3>{day}</h3><p>Tagessuppe</p><p>Gericht {index} mit Beilage</p>' for index, day in enumerate(wels.DAY_NAMES))
                + '<p>OX</p></body></html>').encode()

        def get(url):
            if 'ox-wels' in url:
                return page
            raise OSError('offline')

        original = wels.parse_ox
        try:
            wels.parse_ox = lambda text, monday: (_ for _ in ()).throw(ValueError('OX: neue Form'))
            result = wels.build(None, date(2026, 11, 23), now, get)
            ox = next(row for row in result['restaurants'] if row['id'] == 'ox')
            self.assertEqual((ox['import']['state'], ox['import']['message']), ('fallback', 'ValueError: OX: neue Form'))
            self.assertEqual(names(ox['days']['2026-11-25']), ['Tagessuppe', 'Gericht 2 mit Beilage'])
            # Ein guter Stand derselben Woche bleibt stehen – der Ersatzleser überschreibt ihn nicht.
            good = json.loads(json.dumps(result))
            for row in good['restaurants']:
                if row['id'] == 'ox':
                    row['days'] = {day: [wels.dish('Vom eigenen Leser', 12.9)] for day in row['days']}
                    row['import'] = {'state': 'ok', 'message': ''}
            again = wels.build(good, date(2026, 11, 23), now, get)
            ox = next(row for row in again['restaurants'] if row['id'] == 'ox')
            self.assertEqual((ox['import']['state'], names(ox['days']['2026-11-25'])), ('error', ['Vom eigenen Leser']))
        finally:
            wels.parse_ox = original

    def test_goesser_monthly_plan_without_prices_and_without_allergen_letters(self):
        days = wels.check(wels.parse_goesser(read('goesser-november.txt'), MONDAY), MONDAY)
        self.assertEqual(len(days), 5)
        self.assertEqual([(row['name'], row.get('description')) for row in days['2026-11-16']], [
            ('Zigeunerschnitzerl mit Spätzle', None), ('Cremespinat mit Röstkartoffel und Spiegelei', 'Vegetarisch')])
        self.assertEqual(names(days['2026-11-18']), ['1/2 Grill Hendl mit Pommes Frites', 'Fisolengulasch mit Erdäpfel'])
        self.assertTrue(all(row['price'] is None and row['priceLabel'] == ' ' for rows in days.values() for row in rows))
        following = wels.parse_goesser(read('goesser-november.txt'), date(2026, 11, 23))
        self.assertEqual(names(following['2026-11-27']), [
            'gebackenes Buntbarschfilet mit Kartoffelsalat u. Sc.Tartar', 'Gemüseomelette mit Kartoffel'])
        links = wels.find_goesser_pdfs(read('links2.html').encode('utf-8'))
        self.assertEqual([link.rsplit('/', 1)[1] for link in links],
                         ['MONATSPLAN-10-Oktober-2026.pdf', 'MONATSPLAN-11-November-26.pdf'])

    def test_huber_daily_card_stops_before_the_standing_recommendations(self):
        days = wels.check(wels.parse_huber(read('huber-2026-11-17.txt'), MONDAY), MONDAY)
        self.assertEqual(list(days), ['2026-11-17'])
        self.assertEqual([(row['name'], row['price'], row.get('included_soup'), row.get('category')) for row in days['2026-11-17']], [
            ('Lebernetzbraten mit Kartoffeln und Sauerkraut', 13.5, 'Tagessuppe', None),
            ('Käsespätzle mit Blattsalat', 12.9, 'Tagessuppe', None),
            ('Apfelschnitte oder Eierlikörtorte', 4.5, None, 'Nachspeise')])
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_huber(read('huber-2026-11-17.txt'), date(2026, 11, 23))

    def test_denns_structured_data_with_weekly_soup(self):
        days = wels.check(wels.parse_denns(json.loads(read('denns-kw47.json')), MONDAY), MONDAY)
        self.assertEqual([(row['name'], row['price'], row.get('description')) for row in days['2026-11-17']], [
            ('Tagessuppe', 4.5, None), ('Pastinaken-Gulasch', 6.9, 'Vegan'), ('Zwiebelfleisch mit Hörnchen', 7.9, None)])
        self.assertEqual(len(days), 5)
        with self.assertRaises(wels.NotThisWeek):
            wels.parse_denns(json.loads(read('denns-kw47.json')), date(2026, 11, 23))

    def test_sorrymama_image_needs_two_identical_readings(self):
        texts = {1: read('sorrymama-ocr-1.txt'), 2: read('sorrymama-ocr-2.txt')}   # echte Texterkennung beider Größen
        days = wels.check(wels.read_sorrymama(b'bild', MONDAY, read=lambda image, scale: texts[scale]), MONDAY)
        self.assertEqual(len(days), 5)
        self.assertEqual([(row['name'], row['price']) for row in days['2026-11-18']], [
            ('Suppe oder Menü Salat – Kürbis-Kokos-Cremesuppe', 5.2),
            ('Hühnergeschnetzeltes – Champignons | Reis', 13.9),
            ('Gebackenes Seelachsfilet – Petersilienkartoffeln | Sauce Tartare', 13.9),
            ('Fusilli all’Arrabbiata – Tomatensauce | Chili | Knoblauch | Parmesan', 13.9)])
        misread = {1: texts[1], 2: texts[2].replace('13,90', '18,90', 1)}
        with self.assertRaises(ValueError):
            wels.read_sorrymama(b'bild', MONDAY, read=lambda image, scale: misread[scale])
        with self.assertRaises(wels.NotThisWeek):
            wels.read_sorrymama(b'bild', date(2026, 11, 23), read=lambda image, scale: texts[scale])
        page = read('links2.html').split('<div id="sorrymama">')[1].encode('utf-8')
        self.assertTrue(wels.find_sorrymama(page, MONDAY).endswith('Mittagskarte-16.11-20.11-724x1024.png'))
        with self.assertRaises(wels.NotThisWeek):
            wels.find_sorrymama(page, date(2026, 11, 23))

    def test_hayashi_standing_card_is_bound_to_the_exact_image(self):
        import hashlib
        from unittest.mock import patch
        image = b'lunchkarte'
        with patch.object(wels, 'HAYASHI_SHA256', hashlib.sha256(image).hexdigest()):
            days = wels.check(wels.hayashi_days(image, MONDAY), MONDAY)
            self.assertEqual(sorted(days), ['2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20'])   # Lunch Di–Fr
            self.assertEqual((days['2026-11-17'][0]['name'], days['2026-11-17'][0]['price']), ('Black Pepper Chicken', 13.9))
            with self.assertRaises(wels.Outdated):                 # geändertes Bild: lieber nichts als Veraltetes
                wels.hayashi_days(image + b'!', MONDAY)

    def test_changed_hayashi_image_removes_what_was_shown_before(self):
        # Anders als ein Abruffehler: Die hinterlegte Karte ist nachweislich überholt.
        from unittest.mock import patch
        hayashi = lambda result: next(row for row in result['restaurants'] if row['id'] == 'hayashi')
        def run(previous, outcome):
            def fake(identifier, url, week, get):
                if identifier != 'hayashi':
                    raise OSError('offline')
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            with patch.object(wels, 'fetch', side_effect=fake):
                return wels.build(previous, MONDAY, datetime(2026, 11, 18, 9, tzinfo=wels.TZ))
        shown = run(None, {'2026-11-18': [{'name': 'Black Pepper Chicken', 'price': 13.9}]})
        offline = run(shown, OSError('Zeitüberschreitung'))
        self.assertEqual(names(hayashi(offline)['days']['2026-11-18']), ['Black Pepper Chicken'])   # Ausfall: bleibt
        changed = run(shown, wels.Outdated('Karte geändert'))
        self.assertEqual((hayashi(changed)['days']['2026-11-18'], hayashi(changed)['import']['state']), ([], 'error'))

    def test_undated_card_counts_as_new_only_after_it_changed(self):
        from unittest.mock import patch
        card = lambda monday, dish: {(monday.isoformat()): [{'name': dish, 'price': 12.9}]}
        now = datetime(2026, 11, 17, 9, tzinfo=wels.TZ)
        ox = lambda result: next(row for row in result['restaurants'] if row['id'] == 'ox')
        def run(previous, monday, dish, moment=now):
            def fake(identifier, url, week, get):
                if identifier != 'ox':
                    raise OSError('offline')
                return card(week, dish)
            with patch.object(wels, 'fetch', side_effect=fake):
                return wels.build(previous, monday, moment)
        first = run(None, MONDAY, 'Cheeseburger | Wedges')
        self.assertEqual(ox(first)['import']['state'], 'ok')
        next_week = date(2026, 11, 23)
        weekend = run(first, next_week, 'Cheeseburger | Wedges')            # Samstag: Seite zeigt noch die alte Karte
        self.assertEqual((ox(weekend)['import']['state'], ox(weekend)['days']['2026-11-23']), ('not_published', []))
        monday_morning = run(weekend, next_week, 'Cheeseburger | Wedges')   # weiterhin unverändert
        self.assertEqual(ox(monday_morning)['import']['state'], 'not_published')
        updated = run(monday_morning, next_week, 'Wiener Schnitzel | Kartoffelsalat')
        self.assertEqual((ox(updated)['import']['state'], names(ox(updated)['days']['2026-11-23'])),
                         ('ok', ['Wiener Schnitzel | Kartoffelsalat']))
        again = run(updated, next_week, 'Wiener Schnitzel | Kartoffelsalat') # bleibt in derselben Woche gültig
        self.assertEqual(ox(again)['import']['state'], 'ok')

    def test_undated_baseline_survives_failed_fetches_and_weeks_without_a_new_card(self):
        from unittest.mock import patch
        ox = lambda result: next(row for row in result['restaurants'] if row['id'] == 'ox')
        def run(previous, monday, dish):
            def fake(identifier, url, week, get):
                if identifier != 'ox' or dish is None:
                    raise OSError('offline')
                return {week.isoformat(): [{'name': dish, 'price': 12.9}]}
            with patch.object(wels, 'fetch', side_effect=fake):
                return wels.build(previous, monday, datetime(2026, 11, 17, 9, tzinfo=wels.TZ))
        old = 'Cheeseburger | Wedges'
        week1 = run(None, MONDAY, old)
        week2, week3 = date(2026, 11, 23), date(2026, 11, 30)
        # Erster Abruf der neuen Woche scheitert – danach darf die alte Karte trotzdem nicht als neu gelten.
        failed = run(week1, week2, None)
        after_failure = run(failed, week2, old)
        self.assertEqual((ox(after_failure)['import']['state'], ox(after_failure)['days']['2026-11-23']), ('not_published', []))
        # Eine ganze Woche ohne neue Karte, dann wieder Wochenwechsel: weiterhin die alte Karte.
        third = run(after_failure, week3, old)
        self.assertEqual((ox(third)['import']['state'], ox(third)['days']['2026-11-30']), ('not_published', []))
        fresh = run(third, week3, 'Backhendl | Salat')
        self.assertEqual((ox(fresh)['import']['state'], names(ox(fresh)['days']['2026-11-30'])), ('ok', ['Backhendl | Salat']))
        # Ausfall mitten in der Woche: gezeigte Karte und beide Merkmale bleiben erhalten.
        outage = run(fresh, week3, None)
        self.assertEqual(names(ox(outage)['days']['2026-11-30']), ['Backhendl | Salat'])
        self.assertEqual({key: ox(outage)['import'].get(key) for key in ('fingerprint', 'stale')},
                         {key: ox(fresh)['import'].get(key) for key in ('fingerprint', 'stale')})

    def test_daily_card_adds_today_and_keeps_earlier_days_of_the_week(self):
        from unittest.mock import patch
        huber = lambda result: next(row for row in result['restaurants'] if row['id'] == 'huber')
        def run(previous, day, dish):
            def fake(identifier, url, week, get):
                if identifier != 'huber':
                    raise OSError('offline')
                return {day: [{'name': dish, 'price': 13.5}]}
            with patch.object(wels, 'fetch', side_effect=fake):
                return wels.build(previous, MONDAY, datetime(2026, 11, 18, 9, tzinfo=wels.TZ))
        tuesday = run(None, '2026-11-17', 'Lebernetzbraten')
        wednesday = run(tuesday, '2026-11-18', 'Backhendl')
        self.assertEqual([names(rows) for rows in huber(wednesday)['days'].values()],
                         [[], ['Lebernetzbraten'], ['Backhendl'], [], []])


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
