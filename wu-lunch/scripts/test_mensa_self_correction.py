"""Regression 16.11.2026: Die Mensa-Wochenkarte blieb reduziert, weil eine einzige
abgelehnte KI-Antwort den Import bis zum nächsten Tag beendete.

Originaldaten: das an diesem Montag veröffentlichte PDF und die damals
abgelehnte KI-Antwort. Kein Netzwerk, keine Modellkosten.
"""
import copy
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import update_mensa_ai as mensa

FIXTURES = Path(__file__).parent / 'fixtures'
MON = date(2026, 11, 16)
RAW = (FIXTURES / 'mensa-2026-11-16-monday.pdf').read_bytes()
REJECTED = json.loads((FIXTURES / 'mensa-2026-11-16-monday.rejected-answer.json').read_text(encoding='utf-8'))
SOURCE = REJECTED['source']


def corrected():
    """Was eine Korrekturrunde liefern soll: der gedruckte Bannerpreis in price_eur."""
    result = copy.deepcopy(REJECTED['result'])
    for item in result['items']:
        if item['category'] == 'Menüoption' and item['price_eur'] is None:
            item['price_eur'] = 7.60
    return result


def extract(answers):
    calls = []
    def model(key, name, inputs, **kwargs):
        calls.append(inputs)
        return copy.deepcopy(answers[min(len(calls), len(answers)) - 1]), {'calls': len(calls)}
    text = mensa.independent_period(RAW, MON)
    with TemporaryDirectory() as tmp, patch.object(mensa, 'CANDIDATE', Path(tmp) / 'candidate.json'), \
         patch.object(mensa, 'RESULTS', Path(tmp) / 'results'), \
         patch.object(mensa.ai, 'call_model', side_effect=model):
        try:
            days, _, _ = mensa.extract_for_week(MON, 'test-key', 'gpt-6-luna', (RAW, text, SOURCE))
            outcome = days
        except ValueError as error:
            outcome = error
        record = json.loads((Path(tmp) / 'candidate.json').read_text(encoding='utf-8'))
    return outcome, calls, record


class MensaSelfCorrectionTests(unittest.TestCase):
    def test_rejected_answer_is_repaired_in_one_round_with_the_exact_finding(self):
        days, calls, record = extract([REJECTED['result'], corrected()])
        self.assertIsInstance(days, dict)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(len(rows) >= 10 for rows in days.values()))
        feedback = calls[1][-1]['content'][0]['text']
        self.assertIn('fehlender Gerichtpreis', feedback)
        self.assertIn('Smart Menü', feedback)
        self.assertIn('nichts erfinden', feedback)
        # Die Originalquelle wird erneut mitgeschickt, nicht nur die alte Antwort.
        self.assertTrue(any(part.get('type') == 'input_file' for part in calls[1][0]['content']))
        self.assertEqual(record['validated_by'], mensa.REVIEW_VERSION)
        self.assertEqual(record['corrections'], 1)
        for rows in days.values():
            option = [r for r in rows if r['category'] == 'Menüoption']
            self.assertEqual([r['price'] for r in option], [7.6])

    def test_first_answer_that_passes_costs_exactly_one_call(self):
        days, calls, _ = extract([corrected()])
        self.assertIsInstance(days, dict)
        self.assertEqual(len(calls), 1)

    def test_answer_that_stays_wrong_is_never_published_and_rounds_are_capped(self):
        outcome, calls, record = extract([REJECTED['result']])
        self.assertIsInstance(outcome, ValueError)
        self.assertIn('fehlender Gerichtpreis', str(outcome))
        self.assertEqual(len(calls), 1 + mensa.MAX_CORRECTIONS)
        self.assertNotIn('validated_by', record)

    def test_a_correction_cannot_smuggle_in_an_unprinted_price(self):
        invented = corrected()
        for item in invented['items']:
            if item['category'] == 'Menüoption':
                item['price_eur'] = 6.90  # steht nirgends im PDF
        outcome, calls, _ = extract([REJECTED['result'], invented])
        self.assertIsInstance(outcome, ValueError)
        self.assertIn('Preis nicht in Tageszelle/Tarifspalte', str(outcome))

    def test_findings_name_day_category_and_dish_for_every_rejected_row(self):
        text = mensa.independent_period(RAW, MON)
        with self.assertRaises(ValueError) as caught:
            mensa.validate_menu(REJECTED['result'], text, MON, SOURCE['url'])
        message = str(caught.exception)
        for day in ('2026-11-16', '2026-11-20'):
            self.assertIn(f'[{day} · Menüoption · Smart Menü', message)

    def test_plain_word_ending_is_the_same_source_word(self):
        self.assertTrue(mensa.same_source_word('vegan', 'veganes'))
        self.assertTrue(mensa.same_source_word('warme', 'warmer'))
        self.assertFalse(mensa.same_source_word('salat', 'blattsalat'))
        self.assertFalse(mensa.same_source_word('reis', 'reisgericht'))


class MensaRetryBudgetTests(unittest.TestCase):
    def run_with(self, audit, now):
        days = {(MON + timedelta(days=i)).isoformat(): [{'name': 'Bisheriges Gericht'}] for i in range(5)}
        data = {'weekStart': str(MON), 'restaurants': [{'id': 'mensa', 'days': days}], 'sources': [{'id': 'mensa'}]}
        status = {'sources': {'mensa': {}}, 'mensa_luna_audit': audit, 'problems': []}
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        with TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ('menus.json', 'status.json', 'data.js')]
            paths[0].write_text(json.dumps(data), encoding='utf-8')
            paths[1].write_text(json.dumps(status), encoding='utf-8')
            with patch.multiple(mensa, DATA=paths[0], STATUS=paths[1], JS=paths[2]), \
                 patch.object(mensa, 'datetime', Clock), patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}), \
                 patch.object(mensa, 'acquire_pdf', return_value=(b'pdf', 'text', {'url': SOURCE['url'], 'sha256': 'new'})), \
                 patch.object(mensa, 'extract_for_week', side_effect=ValueError('blocked')) as reader:
                mensa.run(MON, 'gpt-6-luna')
            return reader.call_count, json.loads(paths[1].read_text(encoding='utf-8'))['mensa_luna_audit']

    def test_failed_reading_is_retried_the_same_morning_but_not_endlessly(self):
        failed = {'state': 'error', 'source_sha256': 'new', 'week_start': str(MON),
                  'version': mensa.REVIEW_VERSION, 'last_attempt_at': '2026-11-16T06:15:00+01:00'}
        at = lambda hour, minute: datetime(2026, 11, 16, hour, minute, tzinfo=mensa.TZ)
        calls, audit = self.run_with(dict(failed), at(6, 30))
        self.assertEqual(calls, 0)                       # Pause nach dem Fehlversuch
        self.assertIn('frühestens nach', audit['error'])
        calls, audit = self.run_with(dict(failed), at(7, 30))
        self.assertEqual(calls, 1)                       # früher: erst am nächsten Tag
        self.assertEqual(audit['attempts']['count'], 2)
        calls, audit = self.run_with(audit, at(11, 0))
        self.assertEqual(calls, 0)                       # Tageskontingent erschöpft
        self.assertIn('bereits 2-mal', audit['error'])


if __name__ == '__main__':
    unittest.main()
