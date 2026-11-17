from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo
import unittest
import update_schedule as schedule

ZONE=ZoneInfo('Europe/Vienna')
MON=datetime(2026,11,16,tzinfo=ZONE)

def topf_week(verified_at, days=5):
    rows={(MON+timedelta(days=i)).date().isoformat():([{'name':'Gericht'}] if i<days else []) for i in range(5)}
    return {'weekStart':'2026-11-16','restaurants':[{'id':'topfdeckel','validFrom':'2026-11-16',
            'browser_verified_at':verified_at,'days':rows}]}

class UpdatePolicyTests(unittest.TestCase):
    def setUp(self):
        # Unabhängig von der Umgebung des Testlaufs: Normalbetrieb ohne Vollprüfung.
        environment=patch.dict('os.environ',{'WU_RECHECK_ALL':'0'})
        environment.start()
        self.addCleanup(environment.stop)

    def test_workflow_crons_and_gates_match_the_public_policy(self):
        schedule.check_workflows()

    def test_scheduled_import_runs_whenever_github_starts_it_during_the_day(self):
        for day in ('2026-11-16','2027-07-05'):
            self.assertTrue(schedule.allowed('menus',datetime.fromisoformat(day+'T06:30:00').replace(tzinfo=ZONE),record={}))
            self.assertFalse(schedule.allowed('menus',datetime.fromisoformat(day+'T03:30:00').replace(tzinfo=ZONE),record={}))
        # Verspätete Starts (Regression 10.–13.11.2026: ~15 Uhr statt 08:15) und
        # Wochenendläufe werden nicht mehr als "außerhalb des Fensters" verworfen.
        self.assertTrue(schedule.allowed('menus',datetime(2026,11,10,15,50,tzinfo=ZONE),record={}))
        self.assertTrue(schedule.allowed('menus',datetime(2026,11,15,10,0,tzinfo=ZONE),record={}))
        self.assertFalse(schedule.allowed('menus',datetime(2026,11,16,23,52,tzinfo=ZONE),record={}))
        self.assertTrue(schedule.allowed('menus',datetime(2026,11,16,23,52,tzinfo=ZONE),'workflow_dispatch'))
        self.assertTrue(schedule.allowed('mensa_snapshot',datetime(2026,11,16,17,24,tzinfo=ZONE)))
        self.assertFalse(schedule.allowed('mensa_snapshot',datetime(2026,11,15,10,0,tzinfo=ZONE)))
        self.assertFalse(schedule.allowed('observation',datetime(2026,12,4,10,0,tzinfo=ZONE)))

    def test_scheduled_import_is_skipped_right_after_another_completed_import(self):
        now=datetime(2026,11,16,7,15,tzinfo=ZONE)
        fresh={'last_completed':(now-timedelta(minutes=6)).isoformat()}
        older={'last_completed':(now-timedelta(minutes=45)).isoformat()}
        self.assertFalse(schedule.allowed('menus',now,record=fresh))
        self.assertTrue(schedule.allowed('menus',now,record=older))
        self.assertTrue(schedule.allowed('menus',now,'workflow_dispatch',record=fresh))

    def test_topf_browser_runs_by_need_not_by_clock(self):
        late=datetime(2026,11,16,13,42,tzinfo=ZONE)
        # Stand vom 16.11.2026: nur der Montag vorhanden, letzte Browserprüfung in der Vorwoche.
        stale=topf_week('2026-11-13T16:15:36+01:00',days=1)
        self.assertTrue(schedule.topf_browser_due(late,data=stale,status={}))
        self.assertTrue(schedule.topf_browser_due(late,'workflow_dispatch',data=stale,status={}))
        # Nach einem Fehlversuch nicht im Minutentakt, aber bald wieder.
        failed={'topf_browser_attempt':{'at':(late-timedelta(minutes=10)).isoformat()}}
        self.assertFalse(schedule.topf_browser_due(late,data=stale,status=failed))
        failed={'topf_browser_attempt':{'at':(late-timedelta(minutes=50)).isoformat()}}
        self.assertTrue(schedule.topf_browser_due(late,data=stale,status=failed))
        # Vollständig geprüfte Woche: kein erneuter Abruf mehr (Vorgabe des Betreibers).
        done=topf_week('2026-11-16T07:20:00+01:00')
        for moment in (datetime(2026,11,16,8,15,tzinfo=ZONE),datetime(2026,11,16,12,15,tzinfo=ZONE),datetime(2026,11,19,10,30,tzinfo=ZONE)):
            self.assertFalse(schedule.topf_browser_due(moment,data=done,status={}))
            self.assertFalse(schedule.topf_browser_due(moment,'workflow_dispatch',data=done,status={}))
        # Schon am Wochenende für die kommende Woche geprüft: gilt am Montag weiter.
        weekend=topf_week('2026-11-14T13:05:00+01:00')
        self.assertFalse(schedule.topf_browser_due(datetime(2026,11,15,9,0,tzinfo=ZONE),data=weekend,status={}))
        self.assertFalse(schedule.topf_browser_due(datetime(2026,11,16,5,30,tzinfo=ZONE),data=weekend,status={}))
        # Code-Änderung oder ausdrückliche Vollprüfung: trotzdem einmal ausführen.
        self.assertTrue(schedule.topf_browser_due(datetime(2026,11,16,8,15,tzinfo=ZONE),'push',data=done,status={}))
        with patch.dict('os.environ',{'WU_RECHECK_ALL':'1'}):
            self.assertTrue(schedule.topf_browser_due(datetime(2026,11,16,8,15,tzinfo=ZONE),data=done,status={}))
        # Am folgenden Wochenende zählt die nächste Woche: wieder fällig.
        self.assertTrue(schedule.topf_browser_due(datetime(2026,11,21,10,0,tzinfo=ZONE),data=done,status={}))
