"""Upload zu Google Play: Ablauf gegen eine nachgestellte Google-Schnittstelle (kein Netz, keine Zugangsdaten)."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("upload_play", ROOT / "wu-lunch-app/scripts/upload-play.py")
play = importlib.util.module_from_spec(spec)
spec.loader.exec_module(play)


class Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        if self._body is None:
            raise ValueError("leer")
        return self._body


class FakeGoogle:
    """Merkt sich alle Aufrufe; `fail` bestimmt, welcher Schritt mit welchem Fehler scheitert."""

    def __init__(self, fail=None, draft_app=False, no_review=False):
        self.calls, self.fail, self.draft_app, self.edits, self.committed = [], fail or {}, draft_app, 0, []
        self.no_review = no_review
        self.languages, self.images, self.pending = ["de-DE", "en-US"], {}, {"releases": [{"status": "completed"}]}

    def request(self, method, url, timeout=None, **kwargs):
        path = url.split("/applications/" + play.PACKAGE, 1)[1]
        self.calls.append((method, path, kwargs.get("json")))
        for part, (status, message) in self.fail.items():
            if part in path and method != "DELETE":
                return Response(status, {"error": {"message": message}})
        if method == "GET" and path.endswith("/listings"):
            return Response(200, {"listings": [{"language": language} for language in self.languages]})
        if method == "DELETE" and path.endswith("/phoneScreenshots"):
            self.images[path.split("/listings/")[1].split("/")[0]] = []
            return Response(200, {"deleted": []})
        if method == "POST" and "/phoneScreenshots" in path:
            assert kwargs["headers"]["Content-Type"] == "image/png"
            self.images[path.split("/listings/")[1].split("/")[0]].append(kwargs["data"].read())
            return Response(200, {"image": {"id": "x"}})
        if method == "POST" and path == "/edits":
            self.edits += 1
            return Response(200, {"id": f"edit{self.edits}"})
        if method == "POST" and "/bundles" in path:
            assert kwargs["headers"]["Content-Type"] == "application/octet-stream"
            assert kwargs["data"].read() == b"AAB"
            return Response(200, {"versionCode": 12})
        if method == "PUT" and "/tracks/internal" in path:
            self.pending = kwargs["json"]
            return Response(200, kwargs["json"])
        if method == "POST" and path.endswith(":commit") and self.no_review:
            return Response(400, {"error": {"message": "Changes cannot be sent for review automatically. Please set the query parameter changesNotSentForReview to true."}})
        if method == "POST" and ":commit" in path:
            if self.draft_app and self.pending["releases"][0]["status"] != "draft":
                return Response(400, {"error": {"message": "Only releases with status draft may be created on draft app."}})
            self.committed.append(self.pending)
            return Response(200, {"id": "ok"})
        if method == "GET" and "/tracks/internal" in path:
            return Response(200, {"track": "internal", "releases": [{"name": "0.5.5", "status": "completed", "versionCodes": ["10"]}]})
        if method == "DELETE":
            return Response(204)
        raise AssertionError((method, path))


class UploadPlayTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.bundle = Path(self.dir.name) / "app.aab"
        self.bundle.write_bytes(b"AAB")
        self.notes = [{"language": "de-DE", "text": "Neu"}]

    def tearDown(self):
        self.dir.cleanup()

    def test_upload_sets_the_internal_track_and_commits(self):
        google = FakeGoogle()
        result = play.upload(google, self.bundle, "0.5.7", self.notes)
        self.assertEqual(result, {"versionCode": 12, "status": "completed", "track": "internal", "name": "0.5.7"})
        self.assertEqual([call[:2] for call in google.calls], [
            ("POST", "/edits"), ("POST", "/edits/edit1/bundles?uploadType=media"),
            ("PUT", "/edits/edit1/tracks/internal"), ("POST", "/edits/edit1:commit")])
        release = google.committed[0]["releases"][0]
        self.assertEqual(release, {"name": "0.5.7", "versionCodes": ["12"], "status": "completed", "releaseNotes": self.notes})

    def test_draft_app_gets_a_draft_release_in_a_fresh_edit(self):
        google = FakeGoogle(draft_app=True)
        result = play.upload(google, self.bundle, "0.5.7", self.notes)
        self.assertEqual(result["status"], "draft")
        self.assertEqual(google.edits, 2)                      # zweiter, frischer Entwurf
        self.assertEqual(len(google.committed), 1)
        self.assertEqual(google.committed[0]["releases"][0]["status"], "draft")

    def test_commit_is_repeated_without_review_when_google_asks_for_it(self):
        google = FakeGoogle(no_review=True)
        result = play.upload(google, self.bundle, "0.5.7", self.notes)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(google.edits, 1)                      # derselbe Entwurf, kein zweiter Upload
        self.assertEqual(google.calls[-1][1], "/edits/edit1:commit?changesNotSentForReview=true")
        self.assertEqual(len(google.committed), 1)

    def test_errors_are_explained_and_nothing_is_committed(self):
        for part, status, text, expected in [
            ("/edits", 403, "The caller does not have permission", "keinen Zugriff auf die App"),
            ("/edits", 404, "Package not found: at.startit.wufood.", "allererste Upload"),
            ("/bundles", 403, "Version code 12 has already been used.", "neuen Build"),
        ]:
            google = FakeGoogle(fail={part: (status, text)})
            with self.assertRaises(play.PlayError) as caught:
                play.upload(google, self.bundle, "0.5.7", self.notes)
            self.assertIn(expected, str(caught.exception))
            self.assertEqual(google.committed, [])

    def test_check_reads_the_track_and_discards_the_edit(self):
        google = FakeGoogle()
        result = play.check(google)
        self.assertEqual(result["versionCodes"], [10])
        methods = [call[0] for call in google.calls]
        self.assertEqual(methods, ["POST", "GET", "DELETE"])    # nichts hochgeladen, nichts bestätigt
        self.assertEqual(google.committed, [])

    def shots(self, **counts):
        folder = Path(self.dir.name)
        for language, count in counts.items():
            for number in range(1, count + 1):
                (folder / f"screenshot-{language}-{number}.png").write_bytes(f"{language}{number}".encode())
        return folder

    def test_screenshots_replace_the_old_ones_per_language_and_commit_once(self):
        google = FakeGoogle()
        result = play.upload_screenshots(google, self.shots(de=5, en=5))
        self.assertEqual(result, {"screenshots": {"de-DE": 5, "en-US": 5}, "sentForReview": True})
        self.assertEqual(google.images["de-DE"], [b"de1", b"de2", b"de3", b"de4", b"de5"])     # in Reihenfolge, alte vorher entfernt
        self.assertEqual(google.images["en-US"][0], b"en1")
        self.assertEqual(len(google.committed), 1)
        self.assertEqual([call[1] for call in google.calls if "/bundles" in call[1] or "/tracks" in call[1]], [])   # kein Release berührt

    def test_screenshots_only_for_languages_the_listing_has(self):
        google = FakeGoogle()
        google.languages = ["de-AT"]
        result = play.upload_screenshots(google, self.shots(de=3, en=3))
        self.assertEqual(result["screenshots"], {"de-AT": 3})
        self.assertNotIn("en-US", google.images)

    def test_failed_screenshot_upload_discards_the_edit_and_explains_missing_rights(self):
        google = FakeGoogle(fail={"phoneScreenshots?uploadType": (403, "The caller does not have permission")})
        with self.assertRaises(play.PlayError) as raised:
            play.upload_screenshots(google, self.shots(de=5, en=5))
        self.assertIn("Store-Präsenz verwalten", str(raised.exception))
        self.assertEqual(google.committed, [])
        self.assertEqual(google.calls[-1][0], "DELETE")              # Googles Entwurf verworfen: der Store-Eintrag bleibt, wie er war
        self.assertTrue(google.calls[-1][1].startswith("/edits/edit1"))

    def test_too_few_screenshots_or_no_matching_language_change_nothing(self):
        for google, counts in ((FakeGoogle(), {"de": 1}), (FakeGoogle(), {})):
            with self.assertRaises(play.PlayError):
                play.upload_screenshots(google, self.shots(**counts))
            self.assertEqual(google.committed, [])
        for name in list(Path(self.dir.name).glob("screenshot-*.png")):
            name.unlink()

    def test_screenshot_commit_falls_back_when_google_wants_manual_review_sending(self):
        google = FakeGoogle(no_review=True)
        result = play.upload_screenshots(google, self.shots(de=2))
        self.assertEqual((result["sentForReview"], len(google.committed)), (False, 1))

    def test_release_notes_come_from_the_repository_and_respect_the_limit(self):
        notes = play.release_notes()
        self.assertEqual({note["language"] for note in notes}, {"de-DE", "en-US"})
        self.assertTrue(all(0 < len(note["text"]) <= 500 for note in notes))
        long_file = Path(self.dir.name) / "notes.json"
        long_file.write_text(json.dumps({"de-DE": "x" * 501}), encoding="utf-8")
        with self.assertRaises(play.PlayError):
            play.release_notes(long_file)

    def test_secret_is_validated_without_ever_being_printed(self):
        saved = os.environ.get("PLAY_SERVICE_ACCOUNT_JSON")
        try:
            for value, expected in [("", "fehlt"), ("kein json", "kein gültiges JSON"), ('{"type":"user"}', "kein Dienstkonto-Schlüssel")]:
                os.environ["PLAY_SERVICE_ACCOUNT_JSON"] = value
                with self.assertRaises(play.PlayError) as caught:
                    play.session_from_env()
                self.assertIn(expected, str(caught.exception))
                if value:
                    self.assertNotIn(value, str(caught.exception))
        finally:
            if saved is None:
                os.environ.pop("PLAY_SERVICE_ACCOUNT_JSON", None)
            else:
                os.environ["PLAY_SERVICE_ACCOUNT_JSON"] = saved

    def test_workflow_uploads_only_on_the_explicit_task(self):
        workflow = (ROOT / ".github/workflows/wu-lunch-android.yml").read_text(encoding="utf-8")
        self.assertIn("inputs.aufgabe == 'app-bauen-und-play-intern'", workflow)
        self.assertIn("inputs.aufgabe == 'play-zugang-pruefen'", workflow)
        self.assertEqual(workflow.count("secrets.PLAY_SERVICE_ACCOUNT_JSON"), 3)
        self.assertIn("inputs.aufgabe == 'play-bilder-hochladen'", workflow)       # Screenshots: eigene Aufgabe, baut nichts
        self.assertIn("inputs.aufgabe != 'play-bilder-hochladen'", workflow)
        self.assertIn("default: app-bauen", workflow)           # ohne Auswahl wird nie hochgeladen


if __name__ == "__main__":
    unittest.main()
