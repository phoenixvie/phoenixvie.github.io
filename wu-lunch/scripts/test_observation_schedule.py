import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from observe_publication import scheduled_names

class ObservationScheduleTest(unittest.TestCase):
    def test_saturday_and_delayed_starts_are_not_silent_noops(self):
        zone=ZoneInfo('Europe/Vienna')
        self.assertIn('mensa',scheduled_names(datetime(2026,11,14,10,37,tzinfo=zone)))
        self.assertIn('campus',scheduled_names(datetime(2026,11,13,22,41,tzinfo=zone)))
        self.assertEqual(scheduled_names(datetime(2026,11,18,17,20,tzinfo=zone)),['baschly-veggie','baschly-fleisch'])
        self.assertEqual(scheduled_names(datetime(2026,12,5,10,0,tzinfo=zone)),[])
