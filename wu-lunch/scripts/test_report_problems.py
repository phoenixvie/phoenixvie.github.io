"""Störungsmeldung: genau ein Issue je anhaltender Störung, selbsttätiges Schließen, kein Lärm bei Netzfehlern."""
import json
import sys
import unittest

sys.dont_write_bytecode = True
import report_problems as report


class FakeGitHub:
    def __init__(self, issues=()):
        self.issues, self.calls = list(issues), []

    def __call__(self, method, path, fields=None):
        self.calls.append((method, path, fields))
        return self.issues if method == "GET" else None


def wels(state, message="", days=None, ident="ox"):
    return {"restaurants": [{"id": ident, "name": "OX", "url": "https://www.ox-wels.at/",
                             "days": days or {"2026-11-23": []}, "import": {"state": state, "message": message}}]}


class ReportProblemsTests(unittest.TestCase):
    def test_wu_reports_only_persistent_errors(self):
        status = {"sources": {
            "karmafood": {"state": "error", "consecutive_failures": 29, "note": "Karma Food: ungewöhnliches Enddatum",
                          "last_success": "2026-11-17T17:25:04+01:00"},
            "lia": {"state": "error", "consecutive_failures": 1, "note": "Zeitüberschreitung"},
            "finn": {"state": "not_published", "consecutive_failures": 0, "note": "noch nicht veröffentlicht"},
            "mensa": {"state": "cached", "consecutive_failures": 0}}}
        data = {"restaurants": [{"id": "karmafood", "name": "Karma Food", "url": "https://karmafood.at/x"}]}
        problems = report.wu_problems(status, data)
        self.assertEqual(list(problems), ["wu:karmafood"])
        self.assertEqual((problems["wu:karmafood"]["name"], problems["wu:karmafood"]["url"]), ("Karma Food", "https://karmafood.at/x"))
        self.assertIn("29 Abrufe", problems["wu:karmafood"]["detail"])

    def test_wels_reports_reader_failures_and_fallback_but_no_network_noise_or_old_weeks(self):
        self.assertEqual(list(report.wels_problems(wels("error", "ValueError: OX: keine Tage erkannt"))), ["wels:ox"])
        self.assertEqual(list(report.wels_problems(wels("fallback", "ValueError: OX: neue Form"))), ["wels:ox"])
        for state, message in (("error", "OSError: offline"), ("error", "HTTPError: 503 Server Error"),
                               ("not_published", "OX zeigt noch die Karte der Vorwoche"), ("ok", "")):
            self.assertEqual(report.wels_problems(wels(state, message)), {}, (state, message))

    def test_restaurants_without_any_menu_are_reported_from_tuesday_morning(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        at = lambda day, hour: datetime(2026, 11, day, hour, 0, tzinfo=ZoneInfo("Europe/Vienna"))
        week = {f"2026-11-{day}": [] for day in range(23, 28)}
        data = {"weekStart": "2026-11-23", "restaurants": [
            {"id": "inshaas", "name": "In's Haas", "url": "https://x", "days": dict(week),
             "import": {"state": "not_published", "message": "In's Haas zeigt 2026-11-16"}},
            {"id": "linde", "name": "Linde", "days": {**week, "2026-11-25": [{"name": "Schnitzel mit Reis"}]},
             "import": {"state": "ok", "message": ""}}]}
        self.assertEqual(report.wels_problems(data, at(23, 11)), {})                       # Montag: normal
        self.assertEqual(report.wels_problems(data, at(24, 7)), {})                        # Dienstag früh: noch still
        tuesday = report.wels_problems(data, at(24, 9))
        self.assertEqual(list(tuesday), ["wels:inshaas"])                                  # Linde hat eine Karte
        self.assertIn("keine Karte", tuesday["wels:inshaas"]["detail"])
        self.assertEqual(list(report.wels_problems(data, at(26, 9))), ["wels:inshaas"])    # Tageskarten bleiben still
        self.assertEqual(report.wels_problems(data, at(28, 9)), {})                        # Samstag: neue Woche
        self.assertEqual(report.wels_problems({**data, "weekStart": "2026-11-16"}, at(24, 9)), {})
        # WU: Saisonkarte und Dauerangebot haben bewusst keine Tageskarte; zurückgehaltene Freigabe wird gemeldet.
        wu = {"weekStart": "2026-11-23", "restaurants": [
            {"id": "gruenehuette", "name": "Grüne Hütte", "status": "not_published", "days": dict(week)},
            {"id": "losteria", "name": "L'Osteria", "status": "seasonal", "days": dict(week)},
            {"id": "mensa", "name": "Mensa", "status": "verified", "days": {day: [{"name": "x"}] for day in week}}]}
        status = {"sources": {"gruenehuette": {"state": "not_published", "note": "Grüne Hütte: Datumsüberschrift fehlt"},
                              "mensa": {"state": "withheld", "note": "doppeltes Gericht"}}}
        self.assertEqual(list(report.wu_problems(status, wu, at(23, 11))), ["wu:mensa"])
        found = report.wu_problems(status, wu, at(24, 9))
        self.assertEqual(sorted(found), ["wu:gruenehuette", "wu:mensa"])
        self.assertIn("Datumsüberschrift fehlt", found["wu:gruenehuette"]["message"])

    def test_one_issue_per_problem_and_closing_after_recovery(self):
        problems = report.wels_problems(wels("error", "ValueError: OX: keine Tage erkannt"))
        github = FakeGitHub()
        self.assertEqual(report.sync(problems, "wels", run=github), (["wels:ox"], []))
        fields = next(call[2] for call in github.calls if call[:2] == ("POST", "issues"))
        self.assertEqual((fields["title"], fields["labels[]"]), ("Import-Störung: OX (Wels)", "import-stoerung"))
        self.assertIn(report.marker("wels:ox"), fields["body"])
        self.assertIn("keine Tage erkannt", fields["body"])
        # Beim nächsten Lauf existiert das Issue schon: kein zweites.
        existing = FakeGitHub([{"number": 7, "body": fields["body"]}])
        self.assertEqual(report.sync(problems, "wels", run=existing), ([], []))
        self.assertEqual([call[0] for call in existing.calls], ["GET"])
        # Störung behoben: Issue wird geschlossen – aber nur im eigenen Bereich.
        recovered = FakeGitHub([{"number": 7, "body": fields["body"]}, {"number": 8, "body": report.marker("wu:karmafood")}])
        self.assertEqual(report.sync({}, "wels", run=recovered), ([], ["wels:ox"]))
        self.assertEqual([call[:2] for call in recovered.calls if call[0] != "GET"],
                         [("POST", "issues/7/comments"), ("PATCH", "issues/7")])
        self.assertEqual(recovered.calls[-1][2], {"state": "closed"})

    def test_dry_run_changes_nothing(self):
        github = FakeGitHub([{"number": 8, "body": report.marker("wels:old")}])
        report.sync(report.wels_problems(wels("fallback", "x")), "wels", run=github, dry_run=True)
        self.assertEqual([call[0] for call in github.calls], ["GET"])

    def test_workflows_run_the_report_after_every_import(self):
        for name, scope in (("wu-lunch-menus.yml", "wu"), ("wels-mittag.yml", "wels")):
            text = (report.ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn(f"report_problems.py --scope {scope}", text, name)
            self.assertIn("issues: write", text, name)


if __name__ == "__main__":
    unittest.main()
