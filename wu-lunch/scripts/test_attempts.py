"""Begrenzte KI-Wiederholungen: Selbstheilung am selben Tag ohne Kostenfalle."""
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

import attempts

ZONE = ZoneInfo('Europe/Vienna')
IDENT = attempts.identity('2026-11-16', 'v1', 'abc')


def at(hour, minute=0, day=16):
    return datetime(2026, 11, day, hour, minute, tzinfo=ZONE)


class AttemptBudgetTests(unittest.TestCase):
    def test_first_attempt_is_always_allowed(self):
        self.assertEqual(attempts.allowed({}, IDENT, at(7)), (True, ''))

    def test_second_attempt_needs_a_pause_and_third_waits_for_tomorrow(self):
        record = {}
        attempts.register(record, IDENT, at(7))
        self.assertFalse(attempts.allowed(record, IDENT, at(7, 30))[0])
        self.assertIn('frühestens nach', attempts.allowed(record, IDENT, at(7, 30))[1])
        self.assertTrue(attempts.allowed(record, IDENT, at(8, 5))[0])
        attempts.register(record, IDENT, at(8, 5))
        self.assertEqual(record['attempts']['count'], 2)
        allowed, reason = attempts.allowed(record, IDENT, at(12))
        self.assertFalse(allowed)
        self.assertIn('bereits 2-mal mit KI geprüft', reason)
        self.assertTrue(attempts.allowed(record, IDENT, at(6, day=17))[0])

    def test_changed_source_week_or_checker_version_starts_fresh(self):
        record = {}
        attempts.register(record, IDENT, at(7))
        attempts.register(record, IDENT, at(9))
        for other in (attempts.identity('2026-11-16', 'v1', 'changed'),
                      attempts.identity('2026-11-23', 'v1', 'abc'),
                      attempts.identity('2026-11-16', 'v2', 'abc')):
            self.assertTrue(attempts.allowed(record, other, at(9, 1))[0])


if __name__ == '__main__':
    unittest.main()
