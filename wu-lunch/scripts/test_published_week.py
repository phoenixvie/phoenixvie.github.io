"""Vorgabe des Betreibers (17.11.2026): Ein Restaurant, das seine Wochenkarte
veröffentlicht hat, wird in dieser Woche nicht mehr neu abgerufen.

Kein Netzwerk, keine Modellkosten: Jeder Abrufversuch wird nur mitgezählt.
"""
import copy
import json
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import update_menus as legacy
import update_new_restaurants as newer

MON = date(2026, 11, 16)
TUE = MON + timedelta(days=1)
IDS = ("mensa", "campus", "glashaus", "baschly", "losteria", "omakueche", "topfdeckel",
       "gruenehuette", "lia", "karmafood", "finn")
STATES = {"baschly": "undated", "losteria": "seasonal", "omakueche": "recurring", "finn": "ai_crosschecked"}


def week(filled=range(5)):
    return {(MON + timedelta(days=i)).isoformat():
            ([{"name": "Tagesgericht mit Beilage", "price": 9.9, "category": "Menü", "price_small": 7.9,
               "price_large": 9.9}] if i in filled else []) for i in range(5)}


def dataset():
    restaurants, sources = [], []
    for ident in IDS:
        status = STATES.get(ident, "verified")
        dated = status not in ("undated", "seasonal", "recurring")
        restaurants.append({"id": ident, "status": status, "days": week() if ident != "losteria" else week(()),
                            "validFrom": MON.isoformat() if dated else None,
                            "validUntil": (MON + timedelta(days=4)).isoformat() if dated else None,
                            **({"seasonal": [{"name": "Saisonpizza"}]} if ident == "losteria" else {})})
        sources.append({"id": ident, "status": status})
    return {"weekStart": MON.isoformat(), "weekEnd": (MON + timedelta(days=4)).isoformat(),
            "restaurants": restaurants, "sources": sources}


def status_record():
    stamp = "2026-11-14T13:05:00+01:00"   # schon am Samstag für die kommende Woche übernommen
    return {"sources": {ident: {"state": "ok", "last_success": stamp, "content_sha256": "hash-" + ident,
                                "parser_version": 4} for ident in IDS}, "problems": []}


class PublishedWeekRule(unittest.TestCase):
    def setUp(self):
        # Unabhängig von der Umgebung des Testlaufs: Normalbetrieb ohne Vollprüfung.
        environment = patch.dict("os.environ", {"WU_RECHECK_ALL": "0"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_only_a_dated_verified_complete_week_counts_as_published(self):
        data = dataset()
        self.assertTrue(legacy.week_published(data, "mensa", MON))
        self.assertTrue(legacy.week_published(data, "finn", MON))
        self.assertFalse(legacy.week_published(data, "baschly", MON))       # undatierte Karte
        self.assertFalse(legacy.week_published(data, "mensa", MON + timedelta(days=7)))
        legacy.restaurant(data, "campus")["days"][(MON + timedelta(days=4)).isoformat()] = []
        self.assertFalse(legacy.week_published(data, "campus", MON))        # ein Tag fehlt noch
        legacy.restaurant(data, "topfdeckel")["status"] = "daily"
        self.assertFalse(legacy.week_published(data, "topfdeckel", MON))    # nur Tageskarte
        legacy.restaurant(data, "lia")["validFrom"] = "2026-11-09"
        self.assertFalse(legacy.week_published(data, "lia", MON))           # Karte der Vorwoche
        with patch.dict("os.environ", {"WU_RECHECK_ALL": "1"}):
            self.assertFalse(legacy.week_published(data, "mensa", MON))     # ausdrückliche Vollprüfung


class ImporterSkipsPublishedWeeks(unittest.TestCase):
    def run_importer(self, data, environment=None):
        fetched = []
        def offline(url, *args, **kwargs):
            fetched.append(url)
            raise RuntimeError("offline")
        with TemporaryDirectory() as tmp:
            paths = {name: Path(tmp) / name for name in ("menus.json", "data.js", "status.json")}
            paths["menus.json"].write_text(json.dumps(data), encoding="utf-8")
            paths["status.json"].write_text(json.dumps(status_record()), encoding="utf-8")
            with patch.multiple(legacy, JSON_PATH=paths["menus.json"], DATA_PATH=paths["data.js"],
                                STATUS_PATH=paths["status.json"]), \
                 patch.multiple(newer, DATA=paths["menus.json"], FRONT=paths["data.js"], STATUS=paths["status.json"]), \
                 patch.object(legacy, "safe_get", side_effect=offline), patch.object(legacy.time, "sleep"), \
                 patch.dict("os.environ", {"WU_RECHECK_ALL": "0", "OPENAI_API_KEY": "", **(environment or {})}):
                legacy.run(TUE)
                newer.run(TUE)
            return fetched, json.loads(paths["menus.json"].read_text(encoding="utf-8")), \
                json.loads(paths["status.json"].read_text(encoding="utf-8"))

    def test_published_restaurants_are_not_fetched_again(self):
        original = dataset()
        fetched, data, status = self.run_importer(copy.deepcopy(original))
        hosts = {url.split("/")[2] for url in fetched}
        self.assertEqual(hosts, {"shop.baschly.com"})      # nur die undatierte Karte wird weiter beobachtet
        for ident in ("mensa", "campus", "glashaus", "topfdeckel", "gruenehuette", "lia", "karmafood", "finn"):
            self.assertEqual(legacy.restaurant(data, ident)["days"], legacy.restaurant(original, ident)["days"])
            self.assertEqual(status["sources"][ident]["state"], "cached")
            self.assertEqual(status["sources"][ident]["last_success"], "2026-11-14T13:05:00+01:00")
        self.assertEqual(legacy.restaurant(data, "topfdeckel")["status"], "verified")   # nicht auf "daily" zurückgesetzt

    def test_incomplete_and_unpublished_restaurants_are_still_checked(self):
        data = dataset()
        legacy.restaurant(data, "campus")["days"][(MON + timedelta(days=4)).isoformat()] = []   # Freitag fehlt
        finn = legacy.restaurant(data, "finn")
        finn.update(days=week(()), status="not_published", validFrom=None)
        topf = legacy.restaurant(data, "topfdeckel")
        topf.update(days=week((0,)), status="daily", validFrom=None)                            # Stand 16.11.2026
        fetched, _, _ = self.run_importer(data)
        hosts = {url.split("/")[2] for url in fetched}
        self.assertEqual(hosts, {"shop.baschly.com", "www.dascampus.at", "finn.wien", "topfdeckel.at"})

    def test_explicit_full_recheck_fetches_everything(self):
        fetched, _, _ = self.run_importer(dataset(), {"WU_RECHECK_ALL": "1"})
        hosts = {url.split("/")[2] for url in fetched}
        for host in ("www.wumensa.at", "www.dasglashaus.at", "www.dascampus.at", "lia.coffee",
                     "www.zurgruenenhuette.com", "topfdeckel.at", "karmafood.at", "finn.wien"):
            self.assertIn(host, hosts)


class ControlReadingSkipsPublishedWeeks(unittest.TestCase):
    def test_ai_control_reading_only_for_open_or_flawed_restaurants(self):
        import repair_menus_ai as repair
        data = dataset()
        legacy.restaurant(data, "campus")["days"][(MON + timedelta(days=1)).isoformat()] = []       # heute fehlt etwas
        legacy.restaurant(data, "lia")["days"][MON.isoformat()][0]["price"] = None                  # Preis fehlt
        status = status_record()
        status["ai_repair"] = {}
        with TemporaryDirectory() as tmp:
            paths = {name: Path(tmp) / name for name in ("menus.json", "data.js", "status.json", "report.json")}
            paths["menus.json"].write_text(json.dumps(data), encoding="utf-8")
            paths["status.json"].write_text(json.dumps(status), encoding="utf-8")
            with patch.multiple(repair, DATA=paths["menus.json"], FRONTEND=paths["data.js"],
                                STATUS=paths["status.json"], REPORT=paths["report.json"]), \
                 patch.dict("os.environ", {"WU_RECHECK_ALL": "0", "OPENAI_API_KEY": ""}):
                report = repair.run(TUE)
        checked = {row["restaurant"] for row in report["results"]}
        self.assertIn("campus", checked)
        self.assertIn("lia", checked)
        self.assertIn("baschly", checked)                       # undatiert: bleibt unter Beobachtung
        for published in ("glashaus", "gruenehuette", "karmafood", "mensa", "finn", "topfdeckel"):
            self.assertNotIn(published, checked)


if __name__ == "__main__":
    unittest.main()
