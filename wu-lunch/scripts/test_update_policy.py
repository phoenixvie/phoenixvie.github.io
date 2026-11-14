from datetime import datetime
from zoneinfo import ZoneInfo
import unittest
import update_schedule as schedule

class UpdatePolicyTests(unittest.TestCase):
    def test_workflow_crons_and_gates_match_the_public_policy(self):
        schedule.check_workflows()

    def test_vienna_windows_summer_winter_weekend_and_manual(self):
        zone=ZoneInfo('Europe/Vienna')
        for day in ('2026-11-16','2027-07-05'):
            self.assertTrue(schedule.allowed('menus',datetime.fromisoformat(day+'T06:30:00').replace(tzinfo=zone)))
            self.assertFalse(schedule.allowed('menus',datetime.fromisoformat(day+'T05:30:00').replace(tzinfo=zone)))
        self.assertTrue(schedule.allowed('menus',datetime(2026,11,14,18,40,tzinfo=zone)))
        self.assertFalse(schedule.allowed('menus',datetime(2026,11,15,10,0,tzinfo=zone)))
        self.assertTrue(schedule.allowed('menus',datetime(2026,11,15,10,0,tzinfo=zone),'workflow_dispatch'))
        self.assertTrue(schedule.allowed('topf_browser',datetime(2026,11,16,7,55,tzinfo=zone)))
        self.assertFalse(schedule.allowed('topf_browser',datetime(2026,11,17,7,55,tzinfo=zone)))
        self.assertFalse(schedule.allowed('observation',datetime(2026,12,4,10,0,tzinfo=zone)))
