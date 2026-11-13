"""Offline regression tests for publication observer sampling policy."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from observe_publication import scheduled_names, normalize, SOURCES

TZ=ZoneInfo("Europe/Vienna")

class PublicationObserverTests(unittest.TestCase):
    def moment(self,day,hour):
        return datetime.fromisoformat(day+"T"+f"{hour:02d}:00:00").replace(tzinfo=TZ)

    def test_friday_sunday_monday_tuesday_samples(self):
        for day in ("2026-11-06","2026-11-08","2026-11-09","2026-11-10"):
            for hour in (7,10,13,17):
                self.assertEqual(len(scheduled_names(self.moment(day,hour))),len(SOURCES))
        self.assertEqual(scheduled_names(self.moment("2026-11-07",10)),[])

    def test_midweek_only_baschly(self):
        self.assertEqual(scheduled_names(self.moment("2026-11-11",10)),
                         ["baschly-veggie","baschly-fleisch"])
        self.assertEqual(scheduled_names(self.moment("2026-11-11",17)),[])

    def test_stop_after_four_weeks(self):
        self.assertEqual(scheduled_names(self.moment("2026-12-04",7)),[])

    def test_unchanged_content_same_digest(self):
        x=b"<html><nav>Header A</nav><main>Das Angebot dieser Woche Montag Kuerbissuppe Curry mit Reis</main></html>"
        y=b"<html><nav>Header B</nav><main>Das Angebot dieser Woche Montag Kuerbissuppe Curry mit Reis</main></html>"
        self.assertEqual(normalize(x,"baschly-veggie")[0],normalize(y,"baschly-veggie")[0])

if __name__=="__main__":
    unittest.main()
