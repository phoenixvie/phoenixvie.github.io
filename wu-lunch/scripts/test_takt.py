"""Wächter-Entscheidungen ohne Netzwerk: Wann importieren, warten, übergeben, enden?

Vorgabe des Betreibers (17.11.2026): Freitagabend, Samstag 3x, Sonntag 3x,
Montag engmaschig, danach täglich.
"""
from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo
import json
import unittest

import takt

ZONE = ZoneInfo('Europe/Vienna')
CONFIG = takt.policy()
WATCH = CONFIG['watch']


def at(day, hour, minute=0):
    """November 2026: 13 = Freitag, 14 = Samstag, 15 = Sonntag, 16 = Montag."""
    return datetime(2026, 11, day, hour, minute, tzinfo=ZONE)


def menus(week='2026-11-16', missing=(), empty_days=None):
    monday = date.fromisoformat(week)
    empty_days = empty_days or {}
    names = ('mensa', 'finn', 'lia', 'topfdeckel', 'losteria', 'omakueche')
    rows = lambda name, day: [] if (name in missing or name == 'losteria' or day in empty_days.get(name, ())) else [{'name': 'Gericht'}]
    return {'weekStart': week, 'restaurants': [
        {'id': name, 'days': {(monday + timedelta(days=i)).isoformat(): rows(name, (monday + timedelta(days=i)).isoformat())
                              for i in range(5)}} for name in names]}


def step(now, missing=(), last=None, started=None):
    return takt.decide(now, config=CONFIG, missing=list(missing), last_import_at=last,
                       started_at=started or now)


class ScheduleTests(unittest.TestCase):
    def test_watch_is_always_active_from_friday_evening_to_monday_evening(self):
        self.assertFalse(takt.in_period(at(13, 17, 59), WATCH))   # Freitag vor 18:00
        self.assertTrue(takt.in_period(at(13, 18, 0), WATCH))
        self.assertTrue(takt.in_period(at(14, 3, 0), WATCH))      # Samstagnacht
        self.assertTrue(takt.in_period(at(15, 23, 0), WATCH))     # Sonntag
        self.assertTrue(takt.in_period(at(16, 17, 59), WATCH))    # Montag
        self.assertFalse(takt.in_period(at(16, 18, 0), WATCH))
        self.assertFalse(takt.in_period(at(18, 9, 0), WATCH))     # Mittwoch

    def test_requested_check_times_per_day(self):
        count = lambda day: len(takt.slots_on(date(2026, 11, day), WATCH, ZONE))
        times = lambda day: [slot.strftime('%H:%M') for slot in takt.slots_on(date(2026, 11, day), WATCH, ZONE)]
        self.assertEqual(times(14), ['00:10', '08:00', '13:00', '18:00'])   # Freitagnacht + Samstag 3x
        self.assertEqual(count(15), 3)                                      # Sonntag 3x
        self.assertGreaterEqual(count(16), 6)                               # Montag engmaschig
        for weekday in (17, 18, 19, 20):                                    # Dienstag bis Freitag täglich
            self.assertEqual(times(weekday), ['07:00', '10:30'])
        self.assertEqual(takt.dense_interval(at(16, 6, 0), WATCH), 15)
        self.assertIsNone(takt.dense_interval(at(16, 14, 0), WATCH))
        self.assertIsNone(takt.dense_interval(at(17, 6, 0), WATCH))

    def test_latest_and_next_fixed_time(self):
        friday_night = at(14, 0, 5)
        self.assertEqual(takt.latest_slot(friday_night, WATCH), at(13, 10, 30))
        self.assertEqual(takt.next_slot(friday_night, WATCH), at(14, 0, 10))
        self.assertEqual(takt.latest_slot(at(15, 23, 0), WATCH), at(15, 21, 0))
        self.assertEqual(takt.next_slot(at(15, 23, 0), WATCH), at(16, 5, 30))

    def test_day_whose_menu_is_needed_next(self):
        self.assertEqual(takt.target_day(at(14, 10)), date(2026, 11, 16))   # Samstag -> Montag
        self.assertEqual(takt.target_day(at(15, 22)), date(2026, 11, 16))   # Sonntag -> Montag
        self.assertEqual(takt.target_day(at(16, 13, 59)), date(2026, 11, 16))
        self.assertEqual(takt.target_day(at(16, 14, 0)), date(2026, 11, 17))  # ab Nachmittag: morgen
        self.assertEqual(takt.target_day(at(19, 15)), date(2026, 11, 20))   # Donnerstag -> Freitag
        self.assertEqual(takt.target_day(at(20, 15)), date(2026, 11, 20))   # Freitag bleibt Freitag


class MissingMenuTests(unittest.TestCase):
    def test_reports_only_tracked_restaurants_without_the_needed_menu(self):
        found = takt.missing_menus(menus(missing=('finn', 'topfdeckel', 'omakueche')), {}, at(16, 8), WATCH)
        self.assertEqual(found, ['finn', 'topfdeckel'])  # Dauerangebot/Saisonkarte zählen nicht
        self.assertEqual(takt.missing_menus(menus(), {}, at(16, 8), WATCH), [])

    def test_weekend_looks_at_next_monday_and_old_week_counts_as_missing(self):
        sunday = at(15, 18)
        self.assertEqual(takt.missing_menus(menus(missing=('lia',)), {}, sunday, WATCH), ['lia'])
        old = takt.missing_menus(menus(week='2026-11-09'), {}, sunday, WATCH)
        self.assertEqual(old, ['finn', 'lia', 'mensa', 'topfdeckel'])
        self.assertEqual(takt.missing_menus(None, None, sunday, WATCH), ['*'])

    def test_tomorrows_gap_keeps_the_watch_alive_overnight(self):
        # Stand 16.11.2026: Topf & Deckel hatte nur den Montag; Dienstag bis Freitag leer.
        data = menus(empty_days={'topfdeckel': ('2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20')})
        self.assertEqual(takt.missing_menus(data, {}, at(16, 9), WATCH), [])
        self.assertEqual(takt.missing_menus(data, {}, at(16, 18), WATCH), ['topfdeckel'])
        self.assertEqual(takt.missing_menus(data, {}, at(17, 7), WATCH), ['topfdeckel'])

    def test_source_silent_for_over_a_week_does_not_keep_the_watch_busy(self):
        status = {'sources': {'finn': {'last_success': '2026-11-02T08:00:00+01:00'},
                              'lia': {'last_success': '2026-11-13T08:00:00+01:00'}}}
        found = takt.missing_menus(menus(missing=('finn', 'lia')), status, at(16, 8), WATCH)
        self.assertEqual(found, ['lia'])


class DecisionTests(unittest.TestCase):
    def test_friday_night_check_then_wait_for_saturday_morning(self):
        missing = ('finn',)
        self.assertEqual(step(at(13, 20, 0), missing, last=at(13, 10, 35))['action'], 'sleep')
        due = step(at(14, 0, 10), missing, last=at(13, 10, 35))
        self.assertEqual((due['action'], due['reason']), ('import', 'fester Termin 14.11. 00:10'))
        waiting = step(at(14, 0, 20), missing, last=at(14, 0, 12))
        self.assertEqual(waiting['action'], 'sleep')
        self.assertIn('14.11. 08:00', waiting['reason'])
        self.assertEqual(step(at(14, 8, 0), missing, last=at(14, 0, 12))['action'], 'import')

    def test_missed_fixed_time_is_caught_up_once(self):
        # Wächter startet erst Samstag 10:20: 08:00 wird sofort nachgeholt, aber nur einmal.
        self.assertEqual(step(at(14, 10, 20), last=at(14, 0, 12))['action'], 'import')
        self.assertEqual(step(at(14, 10, 26), last=at(14, 10, 21))['action'], 'sleep')

    def test_monday_morning_regression_checks_every_quarter_hour_while_menus_are_missing(self):
        # 16.11.2026: Finn, Lia und Topf fehlten; GitHubs Zeitplan startete erst um 13:42.
        missing = ('finn', 'lia', 'topfdeckel')
        self.assertEqual(step(at(16, 5, 30), missing, last=at(15, 21, 3))['action'], 'import')
        waiting = step(at(16, 5, 40), missing, last=at(16, 5, 33))
        self.assertEqual((waiting['action'], waiting['seconds']), ('sleep', 480))
        self.assertEqual(step(at(16, 5, 48), missing, last=at(16, 5, 33))['action'], 'import')

    def test_monday_without_gaps_only_uses_the_fixed_times(self):
        self.assertEqual(step(at(16, 6, 0), last=at(16, 5, 33))['action'], 'sleep')
        self.assertEqual(step(at(16, 6, 50), last=at(16, 5, 33))['action'], 'sleep')
        self.assertEqual(step(at(16, 7, 0), last=at(16, 5, 33))['action'], 'import')
        self.assertEqual(step(at(16, 18, 0), last=at(16, 17, 32))['action'], 'stop')

    def test_tuesday_to_friday_checks_daily_while_something_is_missing(self):
        self.assertEqual(step(at(18, 9, 0), last=at(17, 15, 0))['action'], 'stop')          # alles da: Wächter ruht
        self.assertEqual(step(at(18, 7, 0), ('topfdeckel',), last=at(17, 10, 32))['action'], 'import')
        between = step(at(18, 9, 0), ('topfdeckel',), last=at(18, 7, 3))
        self.assertEqual(between['action'], 'sleep')                                        # kein Viertelstundentakt
        self.assertEqual(step(at(18, 10, 30), ('topfdeckel',), last=at(18, 7, 3))['action'], 'import')
        # Über Nacht bleibt er aktiv, damit der Termin um 07:00 sicher stattfindet.
        self.assertEqual(step(at(16, 18, 0), ('topfdeckel',), last=at(16, 17, 32))['action'], 'sleep')

    def test_waits_precisely_until_the_next_fixed_time(self):
        waiting = step(at(14, 7, 57), last=at(14, 0, 12))
        self.assertEqual((waiting['action'], waiting['seconds']), ('sleep', 180))

    def test_job_hands_over_before_github_ends_it(self):
        started = at(14, 1, 0)
        before = step(started + timedelta(minutes=takt.BUDGET_MINUTES - 1), last=at(14, 0, 12), started=started)
        self.assertEqual(before['action'], 'sleep')
        self.assertEqual(step(started + timedelta(minutes=takt.BUDGET_MINUTES), last=at(14, 0, 12),
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
        import tempfile
        from pathlib import Path
        calls = []
        running = {'rows': self.rows()}
        def fake_gh(*args, **kwargs):
            calls.append(args)
            return running['rows'] if args[:2] == ('run', 'list') else ''
        class Clock(datetime):
            current = at(18, 9, 0)   # Mittwoch
            @classmethod
            def now(cls, tz=None):
                return cls.current
        started = lambda: ('workflow', 'run', WATCH['workflow'], '--ref', 'master') in calls
        with tempfile.TemporaryDirectory() as tmp, patch.object(takt, 'gh', side_effect=fake_gh), \
             patch.object(takt, 'datetime', Clock), patch.object(takt, 'ROOT', Path(tmp)), \
             patch.object(takt, 'policy', return_value=CONFIG):
            (Path(tmp) / 'data').mkdir()
            write = lambda data: (Path(tmp) / 'data/menus.json').write_text(json.dumps(data), encoding='utf-8')
            write(menus())
            takt.ensure()                      # Mittwoch, alles veröffentlicht: keine Wache nötig
            self.assertEqual(calls, [])
            write(menus(missing=('topfdeckel',)))
            takt.ensure()                      # ein Menü fehlt: Wache starten
            self.assertTrue(started())
            calls.clear()
            running['rows'] = self.rows((100, 'in_progress'))
            takt.ensure()                      # es läuft schon eine
            self.assertFalse(started())
            calls.clear()
            running['rows'] = self.rows()
            write(menus())
            Clock.current = at(14, 7, 0)       # Samstag: Wachzeitraum, auch wenn alles da wäre
            takt.ensure()
            self.assertTrue(started())


class HandoverTests(unittest.TestCase):
    """Die Wachkette darf an einer verschluckten Übergabe nicht reißen (17.11.2026).

    Reißt sie, wacht bis zum nächsten GitHub-Zeitplan niemand – genau die
    Verspätung, wegen der es den Taktgeber gibt.
    """

    OLD = [{'databaseId': 70, 'status': 'completed', 'conclusion': 'success'},
           {'databaseId': 77, 'status': 'in_progress', 'conclusion': None}]

    def hand_over(self, listings, dispatch_error=None):
        calls, naps = [], []
        answers = iter(listings)
        def gh(*args, **kwargs):
            calls.append(args)
            if args[:2] == ('run', 'list'):
                answer = next(answers)
                if isinstance(answer, Exception):
                    raise answer
                return json.dumps(answer)
            if dispatch_error:
                raise dispatch_error
            return ''
        with patch.object(takt, 'gh', side_effect=gh):
            result = takt.hand_over('takt.yml', 'master', '77', sleep=naps.append)
        return result, [call for call in calls if call[:2] == ('workflow', 'run')], naps

    def test_waits_until_github_really_lists_the_successor(self):
        successor = {'databaseId': 90, 'status': 'queued', 'conclusion': None}
        result, dispatches, naps = self.hand_over([self.OLD, self.OLD, self.OLD + [successor]])
        self.assertTrue(result)
        self.assertEqual(dispatches, [('workflow', 'run', 'takt.yml', '--ref', 'master', '-f', 'predecessor=77')])
        self.assertEqual(naps, [20, 20])

    def test_swallowed_dispatch_is_reported_as_failed(self):
        polls = takt.HANDOVER_CONFIRM_SECONDS // 20
        result, dispatches, naps = self.hand_over([self.OLD] * (polls + 1))
        self.assertFalse(result)                       # ältere Läufe zählen nicht als Nachfolger
        self.assertEqual((len(dispatches), len(naps)), (1, polls))

    def test_successor_that_failed_at_once_does_not_count(self):
        polls = takt.HANDOVER_CONFIRM_SECONDS // 20
        broken = {'databaseId': 90, 'status': 'completed', 'conclusion': 'failure'}
        self.assertFalse(self.hand_over([self.OLD] + [self.OLD + [broken]] * polls)[0])

    def test_successor_that_already_finished_regularly_counts(self):
        done = {'databaseId': 90, 'status': 'completed', 'conclusion': 'success'}
        self.assertTrue(self.hand_over([self.OLD, self.OLD + [done]])[0])

    def test_failed_dispatch_and_flaky_status_queries(self):
        result, dispatches, naps = self.hand_over([self.OLD], dispatch_error=RuntimeError('HTTP 503'))
        self.assertEqual((result, naps), (False, []))  # gar nicht ausgelöst: sofort melden
        successor = {'databaseId': 90, 'status': 'in_progress', 'conclusion': None}
        flaky = [RuntimeError('HTTP 502'), RuntimeError('HTTP 502'), self.OLD + [successor]]
        self.assertTrue(self.hand_over(flaky)[0])      # gestörte Abfragen werden einfach wiederholt

    def test_start_check_survives_a_short_outage_and_then_watches_anyway(self):
        naps = []
        with patch.object(takt, 'other_watch', side_effect=[RuntimeError('HTTP 502'), 100]):
            self.assertEqual(takt.first_watch_check('takt.yml', '200', '', sleep=naps.append), 100)
        with patch.object(takt, 'other_watch', side_effect=RuntimeError('HTTP 502')) as query:
            self.assertIsNone(takt.first_watch_check('takt.yml', '200', '', sleep=naps.append))
            self.assertEqual(query.call_count, takt.START_TRIES)

    def test_job_limit_leaves_room_for_a_running_import_and_handover_retries(self):
        workflow = (takt.ROOT.parent / '.github/workflows/wu-lunch-takt.yml').read_text(encoding='utf-8')
        limit = int(workflow.split('timeout-minutes:')[1].split()[0])
        attempt = (takt.HANDOVER_CONFIRM_SECONDS + takt.RETRY_SECONDS) / 60
        self.assertLessEqual(limit, 355)               # GitHub selbst beendet Jobs nach 360 Minuten
        self.assertGreaterEqual(limit - takt.BUDGET_MINUTES - 25, 3 * attempt)


def wels(*filled, week='2026-11-16', name='huber'):
    """Welser Stand: das Lokal mit Tageskarte hat an den genannten Tagen (Tag im November) Gerichte."""
    monday = date.fromisoformat(week)
    days = {(monday + timedelta(days=i)).isoformat(): ([{'name': 'Tagesteller'}] if (monday + timedelta(days=i)).day in filled else [])
            for i in range(5)}
    return {'weekStart': week, 'restaurants': [{'id': name, 'days': days}, {'id': 'goesser', 'days': {day: [] for day in days}}]}


class DailyMenuTests(unittest.TestCase):
    """Lokale mit täglich neuer Karte (Wels: Gasthaus Huber) – 24.11.2026: Das Dienstagsmenü stand um 09:50 auf der
    Webseite, aber nicht in der App, weil seit der Nacht kein Import gelaufen war."""

    DAILY = WATCH['daily']

    def test_settings_name_the_wels_import_and_morning_times(self):
        self.assertEqual(self.DAILY['workflow'], 'wels-mittag.yml')
        self.assertEqual(self.DAILY['restaurants'], ['huber'])
        self.assertEqual(self.DAILY['slots'], ['08:30', '09:30', '10:30', '11:30'])
        self.assertTrue((takt.ROOT / self.DAILY['file']).resolve().exists())

    def test_todays_card_counts_as_missing_until_the_afternoon(self):
        missing = lambda now, data: takt.missing_daily(data, now, self.DAILY)
        self.assertEqual(missing(at(17, 9, 0), wels(16)), ['huber'])            # Dienstagvormittag: heute fehlt
        self.assertEqual(missing(at(17, 9, 0), wels(16, 17)), [])               # heute ist da
        self.assertEqual(missing(at(17, 15, 0), wels(16, 17)), ['huber'])       # nachmittags zählt schon morgen (wach bleiben)
        self.assertEqual(missing(at(20, 9, 0), wels(16, 17, 18, 19)), ['huber'])   # Freitagvormittag
        self.assertEqual(missing(at(20, 15, 0), wels(16, 17, 18, 19)), [])      # Freitagnachmittag: nichts mehr zu holen
        self.assertEqual(missing(at(16, 7, 0), wels()), ['huber'])              # Montagfrüh
        self.assertEqual(missing(at(17, 9, 0), None), [])                       # Datei nicht lesbar: kein Dauerlauf
        self.assertEqual(takt.missing_daily(wels(16), at(17, 9, 0), None), [])  # nicht eingerichtet

    def test_a_restaurant_silent_all_week_does_not_keep_the_watch_awake(self):
        self.assertEqual(takt.missing_daily(wels(), at(17, 9, 0), self.DAILY), ['huber'])   # Dienstag: Montag kann ein Ausrutscher sein
        self.assertEqual(takt.missing_daily(wels(), at(18, 9, 0), self.DAILY), [])          # Mittwoch, noch nie etwas: Betriebsurlaub
        self.assertEqual(takt.missing_daily(wels(16), at(18, 9, 0), self.DAILY), ['huber'])

    def test_import_is_due_at_each_morning_time_once_and_only_on_the_day_itself(self):
        due = lambda now, last=None, missing=('huber',): takt.daily_due(now, self.DAILY, list(missing), last)
        self.assertFalse(due(at(17, 8, 0)))                                     # vor dem ersten Termin
        self.assertTrue(due(at(17, 8, 31)))
        self.assertFalse(due(at(17, 8, 50), last=at(17, 8, 31)))                # 08:30 ist bedient
        self.assertTrue(due(at(17, 9, 31), last=at(17, 8, 31)))
        self.assertFalse(due(at(17, 9, 31), missing=()))                        # Karte ist da
        self.assertFalse(due(at(17, 20, 0)))                                    # abends gilt schon morgen: kein Abruf in der Nacht
        self.assertEqual(takt.seconds_to_daily_slot(at(17, 8, 0), self.DAILY), 1800)
        self.assertIsNone(takt.seconds_to_daily_slot(at(17, 12, 0), self.DAILY))

    def test_watch_stays_awake_for_a_missing_daily_card(self):
        quiet = at(18, 9, 0)                                                    # Mittwoch, außerhalb des Wachzeitraums, WU vollständig
        self.assertEqual(takt.decide(quiet, config=CONFIG, missing=[], last_import_at=quiet, started_at=quiet)['action'], 'stop')
        self.assertEqual(takt.decide(quiet, config=CONFIG, missing=[], last_import_at=quiet, started_at=quiet, keep_alive=True)['action'], 'sleep')


class WatchRunSimulation(unittest.TestCase):
    """Ganzer Wachlauf mit simulierter Uhr."""

    def simulate(self, start, until, publish_at, rival=False, max_minutes=None, swallowed=0, outage=0,
                 failing_starts=0, daily=None, complete=False):
        clock = {'now': start, 'imported': False}   # 'imported': neue Menüs wurden tatsächlich abgeholt
        log = {'imports': [], 'dispatched': [], 'failed': []}
        github = {'listings': 0, 'failing_starts': failing_starts}
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock['now']
        class Finished(Exception):
            pass
        def sleep(seconds):
            clock['now'] += timedelta(seconds=seconds)
            if clock['now'] >= until:
                raise Finished()
        def published(*paths):
            now = clock['now']
            if now < at(14, 0, 0):                      # bis Freitag 24:00: laufende Woche, vollständig
                data = menus(week='2026-11-09')
            else:                                       # neue Woche; Finn und Topf kommen später
                data = menus(missing=() if clock['imported'] or complete else ('finn', 'topfdeckel'))
            files = {'data/menus.json': data, 'status.json': {},
                     'data/update-status.json': {'last_completed': (start - timedelta(hours=3)).isoformat()}}
            if daily:                                   # Welser Tageskarte: Stand je nach Uhrzeit
                files[WATCH['daily']['file']] = daily(now)
            return [files.get(path) for path in paths]
        def trigger(workflow, branch, **kwargs):
            if github['failing_starts'] > 0:            # GitHub nimmt den Start gerade nicht an
                github['failing_starts'] -= 1
                log['failed'].append(clock['now'])
                raise RuntimeError('gh workflow run: HTTP 503')
            log['imports'].append(clock['now'])
            if clock['now'] >= publish_at:              # das Restaurant hat inzwischen veröffentlicht
                clock['imported'] = True
            sleep(240)  # ein Import dauert einige Minuten
            return {'status': 'completed'}
        def gh(*args, **kwargs):
            if args[:2] == ('run', 'list'):
                github['listings'] += 1
                if github['listings'] <= outage:
                    raise RuntimeError('gh run list: HTTP 502')
                rows = [{'databaseId': 5, 'status': 'in_progress'}] if rival else []
                if len(log['dispatched']) > swallowed:   # der Nachfolger wird wirklich geführt
                    rows.append({'databaseId': 78, 'status': 'queued', 'conclusion': None})
                return json.dumps(rows)
            log['dispatched'].append(args)
            return ''
        budget = max_minutes or 10 ** 6
        original = takt.decide
        with patch.object(takt, 'datetime', Clock), patch.object(takt.time, 'sleep', sleep), \
             patch.object(takt, 'published', published), patch.object(takt, 'trigger_import', trigger), \
             patch.object(takt, 'gh', gh), \
             patch.object(takt, 'decide', lambda *a, **k: original(*a, **{**k, 'budget_minutes': budget})), \
             patch.dict('os.environ', {'GITHUB_RUN_ID': '77', 'WU_TAKT_PREDECESSOR': ''}):
            try:
                takt.run()
            except Finished:
                pass
        return clock['now'], log

    def stamps(self, log):
        return [moment.strftime('%a %H:%M') for moment in log['imports']]

    def test_whole_weekend_follows_the_requested_rhythm(self):
        ended, log = self.simulate(at(13, 18, 30), until=at(17, 12, 0), publish_at=at(16, 8, 0))
        stamps = self.stamps(log)
        day = lambda name: [s for s in stamps if s.startswith(name)]
        self.assertEqual(day('Fri'), [])                                         # Freitagabend: nichts mehr zu holen
        self.assertEqual(day('Sat'), ['Sat 00:10', 'Sat 08:00', 'Sat 13:00', 'Sat 18:00'])
        self.assertEqual(day('Sun'), ['Sun 09:00', 'Sun 15:00', 'Sun 21:00'])
        monday = day('Mon')
        self.assertEqual(monday[0], 'Mon 05:30')
        early = [s for s in monday if s < 'Mon 08:00']
        self.assertGreaterEqual(len(early), 8)                                   # dichter Takt, solange Menüs fehlen
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(log['imports'], log['imports'][1:])
                if a >= at(16, 5, 30) and b < at(16, 8, 0)]
        self.assertTrue(gaps and max(gaps) <= 20)
        late = [s for s in monday if s >= 'Mon 08:30']
        self.assertEqual(late, ['Mon 08:30', 'Mon 10:00', 'Mon 11:30', 'Mon 13:30', 'Mon 15:30', 'Mon 17:30'])
        self.assertEqual(day('Tue'), [])                                         # alles veröffentlicht: Wächter beendet
        self.assertLess(ended, at(16, 18, 30))
        self.assertEqual(log['dispatched'], [])

    def test_daily_card_is_fetched_by_the_wels_import_on_the_morning_it_appears(self):
        # Dienstag, WU vollständig. Huber veröffentlicht um 09:45. Der Welser Import wird um 08:30 und 09:30 direkt
        # angestoßen (noch nichts da). Um 10:30 läuft der feste WU-Termin, der den Welser Import als Folgelauf startet –
        # danach ist die Karte da, und bis zum Nachmittag wird nichts mehr angestoßen.
        daily = lambda now: wels(16, 17) if now >= at(17, 10, 35) else wels(16)
        ended, log = self.simulate(at(17, 6, 0), until=at(17, 13, 55), publish_at=at(17, 9, 45), daily=daily, complete=True)
        wels_runs = [call for call in log['dispatched'] if call[:3] == ('workflow', 'run', 'wels-mittag.yml')]
        self.assertEqual(len(wels_runs), 2)
        self.assertEqual(self.stamps(log), ['Tue 07:00', 'Tue 10:30'])
        self.assertEqual([call for call in log['dispatched'] if call[:2] == ('workflow', 'run') and call[2] != 'wels-mittag.yml'], [])

    def test_daily_card_that_never_appears_is_tried_at_the_four_times_and_not_more(self):
        ended, log = self.simulate(at(17, 6, 0), until=at(17, 13, 55), publish_at=at(19, 0, 0), daily=lambda now: wels(16), complete=True)
        wels_runs = [call for call in log['dispatched'] if call[:3] == ('workflow', 'run', 'wels-mittag.yml')]
        self.assertEqual(len(wels_runs), 3)        # 08:30, 09:30, 11:30 – um 10:30 startet ihn der WU-Import als Folgelauf
        self.assertEqual(self.stamps(log), ['Tue 07:00', 'Tue 10:30'])

    def test_without_a_daily_card_problem_the_week_stays_quiet(self):
        ended, log = self.simulate(at(17, 6, 0), until=at(17, 13, 55), publish_at=at(16, 0, 0), daily=lambda now: wels(16, 17), complete=True)
        self.assertEqual(log['dispatched'], [])
        self.assertEqual(self.stamps(log), [])     # Wächter endet sofort: nichts ausständig

    def test_gap_after_monday_is_checked_daily_until_closed(self):
        # Veröffentlichung erst Mittwoch 08:00: Di 07:00/10:30, Mi 07:00 und 10:30 (holt es ab), danach Ende.
        ended, log = self.simulate(at(16, 17, 0), until=at(19, 12, 0), publish_at=at(18, 8, 0))
        stamps = self.stamps(log)
        self.assertEqual([s for s in stamps if s.startswith('Tue')], ['Tue 07:00', 'Tue 10:30'])
        self.assertEqual([s for s in stamps if s.startswith('Wed')], ['Wed 07:00', 'Wed 10:30'])
        self.assertEqual([s for s in stamps if s.startswith('Thu')], [])
        self.assertLess(ended, at(18, 12, 0))

    def test_job_limit_triggers_exactly_one_successor_with_own_run_id(self):
        _, log = self.simulate(at(14, 1, 0), until=at(16, 0, 0), publish_at=at(16, 8, 0), max_minutes=120)
        self.assertEqual(log['dispatched'], [('workflow', 'run', WATCH['workflow'], '--ref', 'master',
                                              '-f', 'predecessor=77')])

    def test_second_watch_exits_without_importing(self):
        ended, log = self.simulate(at(16, 6, 0), until=at(16, 12, 0), publish_at=at(16, 8, 0), rival=True)
        self.assertEqual((log['imports'], log['dispatched'], ended), ([], [], at(16, 6, 0)))

    def test_swallowed_handover_is_repeated_until_a_successor_exists(self):
        handover = ('workflow', 'run', WATCH['workflow'], '--ref', 'master', '-f', 'predecessor=77')
        ended, log = self.simulate(at(14, 1, 0), until=at(16, 0, 0), publish_at=at(16, 8, 0), max_minutes=120,
                                   swallowed=2)
        self.assertEqual(log['dispatched'], [handover] * 3)
        self.assertLess(ended, at(14, 3, 20))                                    # danach endet der alte Lauf

    def test_watch_starts_despite_a_short_github_outage(self):
        for outage in (2, takt.START_TRIES):
            _, log = self.simulate(at(16, 6, 0), until=at(16, 7, 0), publish_at=at(16, 8, 0), outage=outage)
            self.assertGreaterEqual(len(log['imports']), 3, outage)             # Montagstakt läuft trotzdem

    def test_failed_import_start_is_retried_at_once_instead_of_skipping_the_time(self):
        _, log = self.simulate(at(14, 7, 30), until=at(14, 12, 0), publish_at=at(16, 8, 0), failing_starts=2)
        self.assertEqual([m.strftime('%H:%M') for m in log['failed']], ['08:00', '08:01'])
        self.assertEqual(self.stamps(log), ['Sat 08:02'])

    def test_permanently_failing_import_start_gives_up_until_the_next_time(self):
        _, log = self.simulate(at(14, 7, 30), until=at(14, 13, 30), publish_at=at(16, 8, 0), failing_starts=10 ** 6)
        morning = [m for m in log['failed'] if m < at(14, 12, 0)]
        self.assertEqual(len(morning), takt.MAX_FAILED_STARTS)                   # kein Dauerfeuer
        self.assertEqual(log['failed'][takt.MAX_FAILED_STARTS].strftime('%H:%M'), '13:00')


if __name__ == '__main__':
    unittest.main()
