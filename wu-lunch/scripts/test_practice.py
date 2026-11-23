"""Leseübung (practice.py): Urteil, Vergleich, Ablage – und die geprüften Übungsfälle als feste Tests."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import practice
import update_wels as wels

MONDAY = date(2026, 11, 23)
CARD = """Wochenkarte 23.11. – 27.11.2026
Montag
Grießnockerlsuppe
Wiener Schnitzel vom Schwein mit Petersilerdäpfeln 12,90 €
Dienstag
Frittatensuppe
Gebratenes Zanderfilet mit Gemüsereis 13,50 €
Mittwoch
Kürbiscremesuppe
Spinatknödel mit brauner Butter und Parmesan 11,90 €
Donnerstag
Nudelsuppe
Rindsgulasch mit Semmelknödel 12,90 €
Freitag
Erdäpfelsuppe
Gebackener Karfiol mit Sauce Tartare 11,50 €
"""


def days(*names):
    return {MONDAY.isoformat(): [{"name": name, "price": None} for name in names]}


class Judge(unittest.TestCase):
    def test_both_readers_agree_on_a_plain_week_card(self):
        generic = practice.read_with(wels.generic_week, CARD, MONDAY)
        self.assertTrue(generic["ok"], generic)
        self.assertEqual(len(generic["days"]), 5)
        verdict, detail = practice.judge(generic, {"ok": True, "days": json.loads(json.dumps(generic["days"]))})
        self.assertEqual((verdict, detail["agreement"]), ("einig", 1.0))

    def test_longer_wording_of_the_same_dish_still_counts_as_the_same(self):
        score, only_a, only_b = practice.agreement(days("Rindsgulasch mit Semmelknödel"), days("Rindsgulasch mit Semmelknödel und Salat"))
        self.assertEqual((score, only_a, only_b), (1.0, [], []))

    def test_different_dishes_are_reported_as_differences(self):
        score, only_a, only_b = practice.agreement(days("Rindsgulasch", "Nudelsuppe"), days("Rindsgulasch", "Apfelstrudel"))
        self.assertEqual(score, 0.5)
        self.assertEqual((only_a, only_b), ([f"{MONDAY}: nudelsuppe"], [f"{MONDAY}: apfelstrudel"]))

    def test_verdicts(self):
        ok, failed = {"ok": True, "days": days("Rindsgulasch mit Knödel")}, {"ok": False, "other_week": False, "error": "x"}
        other = {"ok": False, "other_week": True, "error": "andere Woche"}
        self.assertEqual(practice.judge(failed, ok)[0], "nur_ki")              # der Lernfall: der Ersatzleser scheitert, die Karte ist lesbar
        self.assertEqual(practice.judge(ok, failed)[0], "nur_ersatzleser")
        self.assertEqual(practice.judge(failed, failed)[0], "beide_gescheitert")
        self.assertEqual(practice.judge(other, other)[0], "andere_woche")       # alte Karte: kein Lesefehler
        self.assertEqual(practice.judge(failed, other)[0], "andere_woche")
        # Der Ersatzleser zeigt eine Karte, die laut Vergleichslesung zu einer anderen Woche gehört: der schwerste Fall.
        self.assertEqual(practice.judge(ok, other)[0], "uneinig")
        self.assertEqual(practice.judge(ok, {"ok": True, "days": days("Ganz anderes Gericht")})[0], "uneinig")
        # Ohne Vergleichslesung (kein Schlüssel) wird nichts behauptet, was niemand geprüft hat.
        self.assertEqual(practice.judge(ok, None)[0], "nur_ersatzleser")
        self.assertEqual(practice.judge(failed, None)[0], "beide_gescheitert")
        self.assertEqual(practice.judge(other, None)[0], "andere_woche")

    def test_a_reader_that_throws_is_a_result_not_a_crash(self):
        result = practice.read_with(wels.generic_week, "Hier steht keine Karte.", MONDAY)
        self.assertFalse(result["ok"])
        self.assertIn("Wochentagen", result["error"])
        old = practice.read_with(wels.generic_week, CARD.replace("23.11. – 27.11.2026", "09.11. – 13.11.2026"), MONDAY)
        self.assertEqual((old["ok"], old["other_week"]), (False, True))


class Cards(unittest.TestCase):
    def test_excerpt_keeps_the_card_and_drops_the_rest_of_the_page(self):
        page = "\n".join(f"Kopfzeile {n}" for n in range(60)) + "\n" + CARD + "\n".join(f"Impressum Zeile {n}" for n in range(200))
        text = practice.excerpt(page)
        self.assertIn("Wochenkarte 23.11.", text)
        self.assertIn("Gebackener Karfiol", text)
        self.assertNotIn("Kopfzeile 10", text)
        self.assertNotIn("Impressum Zeile 100", text)
        self.assertTrue(practice.read_with(wels.generic_week, text, MONDAY)["ok"])   # der Ausschnitt genügt zum Lesen

    def test_card_text_follows_a_pdf_link(self):
        pages = {"https://lokal.example/mittag": b'<a href="/files/speisekarte.pdf">Speisekarte</a><a href="/files/wochenkarte-kw48.pdf">Woche</a>',
                 "https://lokal.example/files/wochenkarte-kw48.pdf": b"%PDF-fake"}
        with mock.patch.object(wels, "pdf_text", lambda raw: "PDF:" + raw.decode()):
            text = practice.card_text({"url": "https://lokal.example/mittag", "kind": "pdf-link", "pdf_link_hint": "wochenkarte"}, pages.__getitem__)
        self.assertEqual(text, "PDF:%PDF-fake")
        with self.assertRaises(ValueError):
            practice.card_text({"url": "https://lokal.example/mittag", "kind": "pdf-link", "pdf_link_hint": "mittagsmenue"}, pages.__getitem__)

    def test_pdf_link_prefers_the_file_of_the_wanted_calendar_week(self):
        pages = {"https://lokal.example/": b'<a href="/dl/1/Menuplan+KW+49.pdf">naechste</a><a href="/dl/2/Menuplan+KW+48.pdf">diese</a>',
                 "https://lokal.example/dl/1/Menuplan+KW+49.pdf": b"%PDF-49", "https://lokal.example/dl/2/Menuplan+KW+48.pdf": b"%PDF-48"}
        source = {"url": "https://lokal.example/", "kind": "pdf-link", "pdf_link_hint": r"Menuplan\+KW"}
        with mock.patch.object(wels, "pdf_text", lambda raw: raw.decode()):
            self.assertEqual(practice.card_text(source, pages.__getitem__, MONDAY), "%PDF-48")
            self.assertEqual(practice.card_text(source, pages.__getitem__), "%PDF-49")     # ohne Woche: der erste Link


class Store(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [mock.patch.object(practice, name, root / folder) for name, folder in
                        (("CARDS", "cards"), ("RESULTS", "results"), ("EXPECTED", "expected"), ("SCOREBOARD", "scoreboard.json"))]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.temp.cleanup()

    def test_run_stores_card_and_result_and_rescore_builds_the_scoreboard(self):
        def get(url):
            if "kaputt" in url:
                raise OSError("nicht erreichbar")
            return ("<html><body><pre>" + (CARD if "gut" in url else "Speisekarte ohne Wochentage, " * 20) + "</pre></body></html>").encode()
        sources = [{"id": "gut", "url": "https://gut.example", "kind": "html"},
                   {"id": "schwer", "url": "https://schwer.example", "kind": "html"},
                   {"id": "kaputt", "url": "https://kaputt.example", "kind": "html"}]
        practice.run(MONDAY, sources, get=get, log=lambda line: None)
        self.assertTrue((practice.CARDS / "gut" / "2026-11-23.txt").exists())
        self.assertFalse((practice.CARDS / "kaputt").exists())
        board = practice.rescore(log=lambda line: None)
        self.assertEqual(len(board), 1)
        week = board[0]
        self.assertEqual((week["cards"], week["generic_solved"], week["abruf_fehlgeschlagen"]), (2, 1, 1))
        self.assertEqual(week["generic_rate"], 0.5)
        self.assertEqual(json.loads((practice.RESULTS / "gut" / "2026-11-23.json").read_text())["verdict"], "nur_ersatzleser")

    def test_rescore_keeps_the_stored_second_reading_and_shows_what_improved(self):
        (practice.CARDS / "lokal").mkdir(parents=True)
        (practice.CARDS / "lokal" / "2026-11-23.txt").write_text(CARD, encoding="utf-8")
        ai = practice.read_with(wels.generic_week, CARD, MONDAY)
        practice._dump(practice.RESULTS / "lokal" / "2026-11-23.json", {"id": "lokal", "week": "2026-11-23", "verdict": "nur_ki", "ai": ai})
        changes = []
        board = practice.rescore(log=changes.append)
        self.assertEqual(changes, ["lokal 2026-11-23: nur_ki → einig"])      # der Ersatzleser hat die Karte dazugelernt
        self.assertEqual(board[0]["einig"], 1)

    def test_prune_removes_old_cards_but_never_a_verified_case(self):
        for name in ("alt", "geprueft"):
            (practice.CARDS / name).mkdir(parents=True)
            (practice.CARDS / name / "2026-06-01.txt").write_text(CARD, encoding="utf-8")
        practice._dump(practice.EXPECTED / "geprueft-2026-06-01.json", {"id": "geprueft", "week": "2026-06-01", "days": {}})
        practice.prune(date(2026, 11, 23))
        self.assertFalse((practice.CARDS / "alt" / "2026-06-01.txt").exists())
        self.assertTrue((practice.CARDS / "geprueft" / "2026-06-01.txt").exists())


class VerifiedCases(unittest.TestCase):
    """Was der Ersatzleser einmal richtig gelernt hat, muss er weiter so lesen (practice/expected)."""

    def test_every_verified_practice_card_is_still_read_exactly_as_checked(self):
        for identifier, monday, text, expected in practice.expected_cases():
            with self.subTest(card=f"{identifier} {monday}"):
                self.assertEqual(wels.check(wels.generic_week(text, monday), monday), expected)


if __name__ == "__main__":
    unittest.main()
