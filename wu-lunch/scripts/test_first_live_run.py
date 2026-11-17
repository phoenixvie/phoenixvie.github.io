"""Regressionen aus dem ersten echten Lauf nach der Umstellung (17.11.2026, 01:22 Uhr).

1. Topf & Deckel: "Optionale Beilage: Basmatireis ..." wurde als Hauptgericht zum
   vollen Preis gelesen; die Abschlussprüfung hielt die Wochenkarte zu Recht zurück.
2. Mensa: Dieselbe Karte wurde einmal freigegeben und Minuten später verworfen,
   weil das Modell "Spezialpasta lt. Tagesaushang" schrieb und reine Hinweise wie
   "Änderungen vorbehalten." als offene Warnung galten.
3. Veröffentlichung: Ein gleichzeitig schreibender Workflow führte dazu, dass das
   fertige Importergebnis verworfen und alles (samt KI) wiederholt wurde.

Kein Netzwerk, keine Modellkosten.
"""
import copy
import json
import os
import subprocess
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import update_menus as legacy
import update_mensa_ai as mensa

FIXTURES = Path(__file__).parent / 'fixtures'
MON = date(2026, 11, 16)

WEDNESDAY = [
    "Hauptspeisen", "KLEIN", "€", "7.50", "/ GROSS", "€", "11.90",
    "Thai Larb-Salat mit Faschiertem, Kräutermix & Limetten-Dressing",
    "Optionale Beilage: Basmatireis. Allergene: A, C, D, F, G, L",
    "Mediterrane Hühnerpfanne mit Ofengemüse, getrockneten Tomaten & Basilikum-Zitronen-Creme",
    "Beilage: Frischer Blattsalat. Allergene: A, C, F, G, L, M, O",
    "Veggie", "Kürbis-Feta Lasagne mit Bechamelsauce",
    "Beilage: Frischer Blattsalat. Allergene: A, C, G, L, M",
    "Veggie", "Red Thai Curry in cremiger Kokos Sauce & Wokgemüse",
    "Beilage: Basmatireis. Allergene: D, F, G, N, O",
    "Dessert", "€", "2.90", "Dessert des Tages",
]


class TopfSideDishRegression(unittest.TestCase):
    def test_optional_side_dish_line_is_not_a_main_dish(self):
        items = legacy.topf_main_items(WEDNESDAY)
        names = [item["name"] for item in items]
        self.assertEqual(names, [
            "Thai Larb-Salat mit Faschiertem, Kräutermix & Limetten-Dressing",
            "Mediterrane Hühnerpfanne mit Ofengemüse, getrockneten Tomaten & Basilikum-Zitronen-Creme",
            "Kürbis-Feta Lasagne mit Bechamelsauce",
            "Red Thai Curry in cremiger Kokos Sauce & Wokgemüse"])
        self.assertFalse(any("beilage" in name.casefold() or "allergene" in name.casefold() for name in names))
        self.assertEqual([item["diet"] for item in items], ["unknown", "unknown", "veggie", "veggie"])

    def test_portion_prices_come_from_the_page_heading(self):
        self.assertEqual({(i["price_small"], i["price_large"]) for i in legacy.topf_main_items(WEDNESDAY)}, {(7.5, 11.9)})
        raised = [line.replace("7.50", "7.90").replace("11.90", "12.50") for line in WEDNESDAY]
        self.assertEqual({(i["price_small"], i["price_large"]) for i in legacy.topf_main_items(raised)}, {(7.9, 12.5)})
        # Ohne gedruckte Preise in der Überschrift gilt der bisher bekannte Tarif.
        plain = ["Hauptspeisen"] + WEDNESDAY[7:]
        self.assertEqual({(i["price_small"], i["price_large"]) for i in legacy.topf_main_items(plain)},
                         {legacy.TOPF_PORTION_TARIFF})
        # Widersprüchliche Angaben werden nicht veröffentlicht.
        swapped = [line.replace("7.50", "12.90") for line in WEDNESDAY]
        with self.assertRaisesRegex(ValueError, "Portionspreise"):
            legacy.topf_main_items(swapped)


class TopfActiveTabRegression(unittest.TestCase):
    """17.11.2026 (Trockenlauf): Der erste Reiter-Klick ging verloren; der Montag
    bekam unbemerkt die Gerichte des voreingestellten heutigen Tages."""
    ACTIVE = "flex-1 rounded-[10px] bg-[#6BAF7C] text-white shadow-[0_2px_6px_rgba(107,175,124,0.25)]"
    IDLE = "flex-1 rounded-[10px] bg-transparent text-[#1A1A1A] hover:bg-white/60"

    def setUp(self):
        import update_topf_browser     # lädt ohne Browser-Treiber (der wird erst beim Abruf gebraucht)
        self.topf = update_topf_browser

    def tabs(self, active):
        return [self.ACTIVE if name == active else self.IDLE for name in self.topf.DAY_NAMES]

    def test_exactly_one_differently_styled_button_is_the_active_day(self):
        for day in self.topf.DAY_NAMES:
            self.assertEqual(self.topf.active_tab(self.tabs(day)), day)

    def test_ambiguous_or_changed_markup_gives_no_answer(self):
        topf = self.topf
        self.assertIsNone(topf.active_tab([self.IDLE] * 5))                                   # keiner aktiv
        self.assertIsNone(topf.active_tab([self.ACTIVE, self.ACTIVE, self.IDLE, self.IDLE, self.IDLE]))
        self.assertIsNone(topf.active_tab([self.ACTIVE, "andere", self.IDLE, self.IDLE, self.IDLE]))
        self.assertIsNone(topf.active_tab([self.ACTIVE, None, self.IDLE, self.IDLE, self.IDLE]))  # Knopf fehlt
        self.assertIsNone(topf.active_tab(self.tabs("Montag")[:4]))

    def test_lost_first_click_is_repeated_and_a_stuck_tab_aborts(self):
        topf = self.topf
        class Page:
            def __init__(self, needed_clicks): self.needed, self.clicks, self.state = needed_clicks, 0, "Dienstag"
            def wait_for_timeout(self, ms): pass
            def evaluate(self, script, names): return [TopfActiveTabRegression.ACTIVE if n == self.state else TopfActiveTabRegression.IDLE for n in names]
        class Button:
            def __init__(self, page): self.page = page
            def click(self, timeout=None):
                self.page.clicks += 1
                if self.page.clicks >= self.page.needed: self.page.state = "Montag"
        page = Page(needed_clicks=3)                 # Seite reagiert erst auf den dritten Klick
        topf.open_tab(page, "Montag", Button(page))
        self.assertEqual((page.clicks, page.state), (3, "Montag"))
        stuck = Page(needed_clicks=99)               # Reiter reagiert nie: nichts veröffentlichen
        with self.assertRaisesRegex(ValueError, "nicht aktiv"):
            topf.open_tab(stuck, "Montag", Button(stuck))


class MensaNoticeWordingRegression(unittest.TestCase):
    RAW = (FIXTURES / 'mensa-2026-11-16-monday.pdf').read_bytes()
    ANSWER = json.loads((FIXTURES / 'mensa-2026-11-16-monday.notice-answer.json').read_text(encoding='utf-8'))

    def extract(self, result):
        calls = []
        def model(*args, **kwargs):
            calls.append(args)
            return copy.deepcopy(result), {}
        text = mensa.independent_period(self.RAW, MON)
        with TemporaryDirectory() as tmp, patch.object(mensa, 'CANDIDATE', Path(tmp) / 'candidate.json'), \
             patch.object(mensa, 'RESULTS', Path(tmp) / 'results'), patch.object(mensa.ai, 'call_model', side_effect=model):
            try:
                days, _, _ = mensa.extract_for_week(MON, 'test-key', 'gpt-6-luna', (self.RAW, text, self.ANSWER['source']))
                return days, len(calls)
            except ValueError as error:
                return error, len(calls)

    def test_real_answer_of_17_november_is_accepted_on_first_reading(self):
        days, calls = self.extract(self.ANSWER['result'])
        self.assertIsInstance(days, dict)
        self.assertEqual(calls, 1)                                   # keine Korrekturrunde nötig
        self.assertEqual(sum(len(rows) for rows in days.values()), 63)
        pasta = [r for r in days['2026-11-16'] if 'Spezialpasta' in r['name']]
        self.assertEqual([(r['price'], r['details_unpublished']) for r in pasta], [(None, True)])

    def test_pure_remarks_do_not_block_but_real_doubt_still_does(self):
        answer = copy.deepcopy(self.ANSWER['result'])
        answer['warnings'] = ["Für die Tagessuppen ist kein Preis angegeben.", "Änderungen vorbehalten."]
        self.assertIsInstance(self.extract(answer)[0], dict)
        for doubt in ("Der Preis für Mittwoch ist geschätzt.", "Zuordnung der Meaty-Zeile am Dienstag nicht eindeutig.",
                      "Zwei Zellen widersprechen sich.", "Donnerstag vermutlich Schnitzel."):
            answer['warnings'] = [doubt]
            outcome, calls = self.extract(answer)
            self.assertIsInstance(outcome, ValueError, doubt)
            self.assertIn('offene KI-Warnung', str(outcome))
            self.assertEqual(calls, 1 + mensa.MAX_CORRECTIONS)

    def test_doubt_about_a_notice_item_is_only_tolerated_if_no_price_was_taken_over(self):
        answer = copy.deepcopy(self.ANSWER['result'])
        doubt = next(w for w in answer['warnings'] if 'unsicher' in w)
        days = self.extract(answer)[0]
        self.assertTrue(mensa.resolved_notice_uncertainty(doubt, days))
        for rows in days.values():
            for row in rows:
                if 'Spezialpasta' in row['name']:
                    row['price'] = 8.2                              # Zweifel, aber Preis übernommen
        self.assertFalse(mensa.resolved_notice_uncertainty(doubt, days))
        self.assertFalse(mensa.resolved_notice_uncertainty("Spezialpasta laut Aushang: Angaben widersprechen sich.", days))

    def test_uncertain_real_dish_gets_an_actionable_finding(self):
        answer = copy.deepcopy(self.ANSWER['result'])
        real = next(i for i in answer['items'] if i['category'] == 'Meaty')
        real['confidence'] = 'medium'
        outcome, _ = self.extract(answer)
        self.assertIsInstance(outcome, ValueError)
        self.assertIn("unsichere Gerichtzuordnung (confidence=medium", str(outcome))
        self.assertIn(real['name'][:40], str(outcome))


class PublishKeepsImportResult(unittest.TestCase):
    SCRIPT = Path(__file__).with_name('publish_data.sh')
    FILES = {'wu-lunch/data.js': 'data', 'wu-lunch/data/menus.json': '{"menu": 1}\n', 'wu-lunch/status.json': '{}\n',
             'wu-lunch/data/update-status.json': '{}\n', 'wu-lunch/source-archive/index.json': '{}\n',
             'wu-lunch/data/publication-observations.json': '{"samples": 1}\n',
             'wu-lunch/ai-pilot/source/mensa-latest.json': '{"snapshot": 1}\n'}

    def git(self, cwd, *args, check=True):
        env = {**os.environ, 'GIT_AUTHOR_NAME': 'test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
               'GIT_COMMITTER_NAME': 'test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid'}
        return subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True, env=env, check=check)

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.origin, self.importer, self.other = root / 'origin.git', root / 'importer', root / 'other'
        subprocess.run(['git', 'init', '--bare', '-q', str(self.origin)], check=True)
        self.git(self.origin, 'symbolic-ref', 'HEAD', 'refs/heads/master')
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(self.importer)], check=True, capture_output=True)
        self.git(self.importer, 'checkout', '-q', '-b', 'master')
        for name, content in self.FILES.items():
            path = self.importer / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        self.git(self.importer, 'add', '-A')
        self.git(self.importer, 'commit', '-q', '-m', 'Ausgangsstand')
        self.git(self.importer, 'push', '-q', 'origin', 'master')
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(self.other)], check=True, capture_output=True)

    def other_pushes(self, name, content):
        (self.other / name).write_text(content, encoding='utf-8')
        self.git(self.other, 'commit', '-q', '--allow-empty', '-am', 'anderer Workflow')
        self.git(self.other, 'push', '-q', 'origin', 'master')

    def publish(self):
        env = {**os.environ, 'GIT_AUTHOR_NAME': 'bot', 'GIT_AUTHOR_EMAIL': 'bot@example.invalid',
               'GIT_COMMITTER_NAME': 'bot', 'GIT_COMMITTER_EMAIL': 'bot@example.invalid'}
        return subprocess.run(['bash', str(self.SCRIPT), 'master', 'WU Lunch: Menüimport Test'],
                              cwd=self.importer, capture_output=True, text=True, env=env)

    def published(self, name):
        return self.git(self.origin, 'show', 'master:' + name).stdout

    def test_other_workflow_wrote_a_different_file_import_result_survives(self):
        # 17.11.2026: Die Mensa-PDF-Sicherung schrieb während des Imports.
        (self.importer / 'wu-lunch/data/menus.json').write_text('{"menu": "63 Gerichte"}\n', encoding='utf-8')
        # Der Lauf hinterlässt auch Dateien, die nicht veröffentlicht werden (geändert bzw. neu).
        (self.importer / 'wu-lunch/ai-pilot/source/mensa-latest.json').write_text('{"snapshot": "lokal"}\n', encoding='utf-8')
        (self.importer / 'wu-lunch/ai-pilot/results').mkdir(parents=True)
        (self.importer / 'wu-lunch/ai-pilot/results/mensa-current.json').write_text('{}', encoding='utf-8')
        self.other_pushes('wu-lunch/data.js', 'data')  # kein inhaltlicher Unterschied nötig: separater Commit
        (self.other / 'README.txt').write_text('Code-Änderung', encoding='utf-8')
        self.git(self.other, 'add', 'README.txt')
        self.git(self.other, 'commit', '-q', '-m', 'Code')
        self.git(self.other, 'push', '-q', 'origin', 'master')
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.published('README.txt'), 'Code-Änderung')
        self.assertEqual(self.published('wu-lunch/data/menus.json'), '{"menu": "63 Gerichte"}\n')
        self.assertEqual(self.published('wu-lunch/ai-pilot/source/mensa-latest.json'), '{"snapshot": 1}\n')
        self.assertEqual(self.git(self.origin, 'log', '--format=%s', '-1', 'master').stdout.strip(), 'WU Lunch: Menüimport Test')

    def test_shared_measurement_file_keeps_the_other_side_and_still_publishes_menus(self):
        (self.importer / 'wu-lunch/data/menus.json').write_text('{"menu": 2}\n', encoding='utf-8')
        (self.importer / 'wu-lunch/data/publication-observations.json').write_text('{"samples": "import"}\n', encoding='utf-8')
        self.other_pushes('wu-lunch/data/publication-observations.json', '{"samples": "monitor"}\n')
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.published('wu-lunch/data/menus.json'), '{"menu": 2}\n')
        self.assertEqual(self.published('wu-lunch/data/publication-observations.json'), '{"samples": "monitor"}\n')

    def test_real_overlap_in_import_files_is_reported_and_nothing_is_overwritten(self):
        (self.importer / 'wu-lunch/data/menus.json').write_text('{"menu": "import"}\n', encoding='utf-8')
        self.other_pushes('wu-lunch/data/menus.json', '{"menu": "fremd"}\n')
        result = self.publish()
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(self.published('wu-lunch/data/menus.json'), '{"menu": "fremd"}\n')
        self.assertEqual(self.git(self.importer, 'status', '--porcelain').stdout.strip(), '')   # kein halber Rebase

    def test_nothing_to_publish_creates_no_commit(self):
        before = self.git(self.origin, 'rev-parse', 'master').stdout
        result = self.publish()
        self.assertEqual(result.returncode, 0)
        self.assertIn('Keine Datenänderungen', result.stdout)
        self.assertEqual(self.git(self.origin, 'rev-parse', 'master').stdout, before)

    def test_plain_publish_without_interference(self):
        (self.importer / 'wu-lunch/status.json').write_text('{"health": "healthy"}\n', encoding='utf-8')
        self.assertEqual(self.publish().returncode, 0)
        self.assertEqual(self.published('wu-lunch/status.json'), '{"health": "healthy"}\n')


if __name__ == '__main__':
    unittest.main()
