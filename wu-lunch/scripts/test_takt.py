"""Wächter-Entscheidungen ohne Netzwerk: Wann importieren, ruhen, übergeben, enden?"""
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo
import json
import unittest

import takt

ZONE = ZoneInfo('Europe/Vienna')
CONFIG = takt.policy()
WATCH = CONFIG['watch']


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=ZONE)


def menus(week='2026-11-16', missing=(), day='2026-11-16'):
    names = ('mensa', 'finn', 'lia', 'topfdeckel', 'losteria', 'omakueche')
    return {'weekStart': week, 'restaurants': [
        {'id': name, 'days': {day: [] if name in missing or name == 'losteria' else [{'name': 'Gericht'}]}}
        for name in names]}


def step(now, missing=(), last=None, started=None):
    return takt.decide(now, config=CONFIG, missing=list(missing), last_import_at=last,
                       started_at=started or now)


class WatchWindowTests(unittest.TestCase):
    def test_week_start_period_covers_sunday_evening_to_monday_lunch(self):
        self.assertFalse(takt.in_period(at(15, 16, 59), WATCH))   # Sonntag vor 17:00
        self.assertTrue(takt.in_period(at(15, 17, 0), WATCH))
        self.assertTrue(takt.in_period(at(16, 3, 0), WATCH))      # Nacht auf Montag
        self.assertTrue(takt.in_period(at(16, 13, 29), WATCH))
        self.assertFalse(takt.in_period(at(16, 13, 30), WATCH))
        self.assertFalse(takt.in_period(at(18, 9, 0), WATCH))     # Mittwoch

    def test_period_may_wrap_around_the_end_of_the_week(self):
        wrap = {'periods': [{'from': [6, '20:00'], 'to': [0, '08:00']}]}
        self.assertTrue(takt.in_period(at(14, 23, 0), wrap))      # Samstag
        self.assertTrue(takt.in_period(at(15, 7, 0), wrap))       # Sonntag
        self.assertFalse(takt.in_period(at(15, 9, 0), wrap))

    def test_night_rest_ends_at_half_past_five(self):
        self.assertEqual(takt.quiet_seconds(at(15, 21, 0), WATCH), 0)
        self.assertEqual(takt.quiet_seconds(at(15, 22, 30), WATCH), 7 * 3600)
        self.assertEqual(takt.quiet_seconds(at(16, 5, 0), WATCH), 30 * 60)
        self.assertEqual(takt.quiet_seconds(at(16, 5, 30), WATCH), 0)


class MissingMenuTests(unittest.TestCase):
    def test_reports_only_tracked_restaurants_without_todays_menu(self):
        found = takt.missing_menus(menus(missing=('finn', 'topfdeckel', 'omakueche')), {}, at(16, 8), WATCH)
        self.assertEqual(found, ['finn', 'topfdeckel'])  # Dauerangebot/Saisonkarte zählen nicht
        self.assertEqual(takt.missing_menus(menus(), {}, at(16, 8), WATCH), [])

    def test_weekend_looks_at_next_monday_and_old_week_counts_as_missing(self):
        sunday = at(15, 18)
        self.assertEqual(takt.missing_menus(menus(missing=('lia',)), {}, sunday, WATCH), ['lia'])
        old = takt.missing_menus(menus(week='2026-11-09', day='2026-11-09'), {}, sunday, WATCH)
        self.assertEqual(old, ['finn', 'lia', 'mensa', 'topfdeckel'])
        self.assertEqual(takt.missing_menus(None, None, sunday, WATCH), ['*'])

    def test_source_silent_for_over_a_week_does_not_keep_the_watch_busy(self):
        status = {'sources': {'finn': {'last_success': '2026-11-02T08:00:00+01:00'},
                              'lia': {'last_success': '2026-11-13T08:00:00+01:00'}}}
        found = takt.missing_menus(menus(missing=('finn', 'lia')), status, at(16, 8), WATCH)
        self.assertEqual(found, ['lia'])


class DecisionTests(unittest.TestCase):
    def test_monday_morning_regression_checks_every_quarter_hour_while_menus_are_missing(self):
        # 16.11.2026: Finn, Lia und Topf fehlten; GitHubs Zeitplan startete erst um 13:42.
        missing = ('finn', 'lia', 'topfdeckel')
        self.assertEqual(step(at(16, 6, 15), missing)['action'], 'import')
        waiting = step(at(16, 6, 25), missing, last=at(16, 6, 15))
        self.assertEqual((waiting['action'], waiting['seconds']), ('sleep', 300))
        self.assertEqual(step(at(16, 6, 30), missing, last=at(16, 6, 15))['action'], 'import')

    def test_complete_menus_are_rechecked_hourly_until_the_period_ends(self):
        self.assertEqual(step(at(16, 9, 0), last=at(16, 8, 30))['action'], 'sleep')
        self.assertEqual(step(at(16, 9, 30), last=at(16, 8, 30))['action'], 'import')
        self.assertEqual(step(at(16, 13, 30), last=at(16, 13, 0))['action'], 'stop')

    def test_sunday_evening_checks_hourly_then_rests_until_morning(self):
        missing = ('finn',)
        self.assertEqual(step(at(15, 17, 5), missing)['action'], 'import')
        self.assertEqual(step(at(15, 17, 30), missing, last=at(15, 17, 5))['action'], 'sleep')
        self.assertEqual(step(at(15, 18, 5), missing, last=at(15, 17, 5))['action'], 'import')
        night = step(at(16, 1, 0), missing, last=at(15, 22, 5))
        self.assertEqual((night['action'], night['reason']), ('sleep', 'Nachtruhe'))
        self.assertLessEqual(night['seconds'], takt.STEP_SECONDS)

    def test_other_weekdays_watch_only_while_something_is_missing(self):
        self.assertEqual(step(at(18, 9, 0))['action'], 'stop')
        self.assertEqual(step(at(18, 9, 0), ('topfdeckel',))['action'], 'import')
        self.assertEqual(step(at(18, 14, 0), ('topfdeckel',))['action'], 'stop')
        self.assertEqual(step(at(14, 10, 0), ('finn',))['action'], 'stop')  # Samstag

    def test_job_hands_over_before_github_ends_it(self):
        started = at(15, 21, 0)  # Übergabe fällt in die Nachtruhe: trotzdem rechtzeitig
        before = step(started + timedelta(minutes=takt.BUDGET_MINUTES - 1), last=started, started=started)
        self.assertEqual(before['action'], 'sleep')
        self.assertEqual(step(started + timedelta(minutes=takt.BUDGET_MINUTES), last=started,
                              started=started)['action'], 'handover')


class SingleWatchTests(unittest.TestCase):
    def rows(self, *rows):
        return json.dumps([{'databaseId': number, 'status': status} for number, status in rows])

    def test_newer_run_yields_to_older_active_watch_but_not_to_its_predecessor(self):
        listing = self.rows((100, 'in_progress'), (200, 'in_progress'), (90, 'completed'))
        with patch.object(takt, 'gh', return_value=listing):
            self.assertEqual(takt.other_watch('takt.yml', '200', ''), 100)      # Zweitstart weicht
            self.assertIsNone(takt.other_watch('takt.yml', '200', '100'))       # Nachfolger übernimmt
            self.assertIsNone(takt.other_watch('takt.yml', '100', ''))          # der Ältere bleibt
            self.assertEqual(takt.other_watch('takt.yml', '', ''), 100)         # ensure: es läuft einer

    def test_ensure_starts_a_watch_only_when_needed_and_none_is_running(self):
        calls = []
        def fake_gh(*args, **kwargs):
            calls.append(args)
            return self.rows() if args[:2] == ('run', 'list') else ''
        class Clock(datetime):
            current = at(16, 7, 0)
            @classmethod
            def now(cls, tz=None):
                return cls.current
        with patch.object(takt, 'gh', side_effect=fake_gh), patch.object(takt, 'datetime', Clock):
            takt.ensure()
            self.assertIn(('workflow', 'run', WATCH['workflow'], '--ref', 'master'), calls)
            calls.clear()
            Clock.current = at(14, 15, 0)  # Samstagnachmittag: keine Wache nötig
            takt.ensure()
            self.assertEqual(calls, [])


class WatchRunSimulation(unittest.TestCase):
    """Ganzer Wachlauf mit simulierter Uhr: Montag 05:20 bis zum Ende des Zeitraums."""

    def simulate(self, start, publish_at, rival=False, max_minutes=None):
        clock = {'now': start}
        log = {'imports': [], 'dispatched': []}
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock['now']
        def sleep(seconds):
            clock['now'] += timedelta(seconds=seconds)
        def published(*paths):
            missing = () if clock['now'] >= publish_at else ('finn', 'topfdeckel')
            files = {'data/menus.json': menus(missing=missing), 'status.json': {},
                     'data/update-status.json': {'last_completed': (start - timedelta(hours=7)).isoformat()}}
            return [files[path] for path in paths]
        def trigger(workflow, branch, **kwargs):
            log['imports'].append(clock['now'])
            sleep(240)  # ein Import dauert einige Minuten
            return {'status': 'completed'}
        def gh(*args, **kwargs):
            if args[:2] == ('run', 'list'):
                return json.dumps([{'databaseId': 5, 'status': 'in_progress'}] if rival else [])
            log['dispatched'].append(args)
            return ''
        budget = max_minutes or takt.BUDGET_MINUTES
        with patch.object(takt, 'datetime', Clock), patch.object(takt.time, 'sleep', sleep), \
             patch.object(takt, 'published', published), patch.object(takt, 'trigger_import', trigger), \
             patch.object(takt, 'gh', gh), patch.object(takt, 'BUDGET_MINUTES', budget), \
             patch.dict('os.environ', {'GITHUB_RUN_ID': '77', 'WU_TAKT_PREDECESSOR': ''}):
            original = takt.decide
            with patch.object(takt, 'decide', lambda *a, **k: original(*a, **{**k, 'budget_minutes': budget})):
                self.assertEqual(takt.run(), 0)
        return clock['now'], log

    def test_monday_from_night_rest_to_noon(self):
        ended, log = self.simulate(at(16, 5, 20), publish_at=at(16, 8, 0), max_minutes=600)
        times = [moment.strftime('%H:%M') for moment in log['imports']]
        self.assertEqual(times[0], '05:30')                       # erster Import direkt nach der Nachtruhe
        early = [t for t in times if t < '08:00']
        self.assertGreaterEqual(len(early), 8)                    # dichter Takt, solange Menüs fehlen
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(log['imports'], log['imports'][1:])]
        self.assertTrue(all(gap <= 20 for gap in gaps[:len(early) - 1]))
        late = [t for t in times if t >= '08:30']
        self.assertTrue(2 <= len(late) <= 6)                      # danach nur noch stündlich
        self.assertEqual(ended.strftime('%H:%M')[:2], '13')       # endet mit dem Wachzeitraum
        self.assertEqual(log['dispatched'], [])

    def test_job_limit_triggers_exactly_one_successor_with_own_run_id(self):
        _, log = self.simulate(at(16, 5, 20), publish_at=at(16, 8, 0), max_minutes=120)
        self.assertEqual(log['dispatched'], [('workflow', 'run', WATCH['workflow'], '--ref', 'master',
                                              '-f', 'predecessor=77')])

    def test_second_watch_exits_without_importing(self):
        ended, log = self.simulate(at(16, 6, 0), publish_at=at(16, 8, 0), rival=True)
        self.assertEqual((log['imports'], log['dispatched'], ended), ([], [], at(16, 6, 0)))


if __name__ == '__main__':
    unittest.main()
