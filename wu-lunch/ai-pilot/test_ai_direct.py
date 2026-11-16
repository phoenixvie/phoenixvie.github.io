"""Offline tests for the isolated AI experiment (no API key or external request)."""
import unittest
from datetime import date
import json
from unittest.mock import patch
import ai_direct as ai

class DirectAITests(unittest.TestCase):
    def test_eleven_restaurants_have_explicit_original_sources(self):
        self.assertEqual(len(ai.SOURCES),11)
        self.assertEqual(len(ai.SOURCES["baschly"]),2)
        self.assertIn("wochenmenu",ai.SOURCES["topfdeckel"][1])
        self.assertTrue(all(url.startswith("https://") for urls in ai.SOURCES.values() for url in urls))

    def test_generic_html_preserves_headers_prices_and_tables(self):
        html=b"""<html><head><script>TRICK</script></head><body>
        <nav>Navigation</nav><main><h2>Mittagsmenue</h2>
        <table><tr><th>Portion</th><th>Preis</th></tr>
        <tr><td>klein</td><td>7,50</td></tr></table>
        <img alt="Lunch Speisekarte" src="/menu.jpg"></main></body></html>"""
        cleaned,truncated=ai.generic_html_for_model(html)
        self.assertFalse(truncated)
        for part in ('<table>','<th>Preis</th>','7,50','alt="Lunch Speisekarte"'):
            self.assertIn(part,cleaned)
        self.assertNotIn("TRICK",cleaned)

    def test_model_schema_is_strict(self):
        self.assertFalse(ai.SCHEMA["additionalProperties"])
        self.assertEqual(set(ai.SCHEMA["properties"]),set(ai.SCHEMA["required"]))
        self.assertFalse(ai.ITEM_SCHEMA["additionalProperties"])

    def test_unverified_missing_price_is_not_rejected(self):
        item={"date":"2026-11-06","name":"Suppe mit Hauptgericht",
              "category":"Menue","portion":None,"price_eur":None,
              "included_items":["Suppe"],"extra_costs":[],
              "source_url":ai.SOURCES["campus"][0],"evidence_excerpt":"Suppe mit Hauptgericht",
              "confidence":"medium"}
        res={"status":"found","period":"2026-11-02 bis 2026-11-06","notes":"",
             "warnings":[],"items":[item]}
        sources=[{"url":ai.SOURCES["campus"][0],"fetched":True}]
        self.assertEqual(ai.validate(res,sources,date(2026,11,2),"campus"),[])

    def test_wrong_week_or_unknown_source_are_flagged(self):
        entry={"date":"2026-10-30","name":"Spaghetti Pomodoro",
               "category":"Menu","portion":None,"price_eur":12.0,
               "included_items":[],"extra_costs":[],
               "source_url":"https://evil.example/test",
               "evidence_excerpt":"Spaghetti Pomodoro € 12","confidence":"high"}
        res={"status":"found","period":None,"notes":"","warnings":[],"items":[entry]}
        problems=ai.validate(res,[{"url":ai.SOURCES["lia"][0],"fetched":True}],date(2026,11,2),"lia")
        self.assertTrue(any("unbekannte Quelle" in p for p in problems))
        self.assertTrue(any("außerhalb" in p for p in problems))

    def test_half_greater_than_whole_flagged(self):
        def item(portion,price):
            return {"date":"2026-11-06","name":"Pizza",
                    "category":"Pizza","portion":portion,"price_eur":price,
                    "included_items":[],"extra_costs":[],
                    "source_url":ai.SOURCES["lia"][0],
                    "evidence_excerpt":"Pizza mit Aufpreis",
                    "confidence":"high"}
        res={"status":"found","period":None,"notes":"","warnings":[],
             "items":[item("halb",13),item("ganz",10)]}
        self.assertTrue(any("kleine/halbe" in p for p in ai.validate(
            res,[{"url":ai.SOURCES["lia"][0],"fetched":True}],date(2026,11,2),"lia")))

    def test_api_decodes_structured_response(self):
        class FakeResponse:
            status_code=200
            def json(self):
                return {"status":"completed",
                        "output":[{"type":"message","content":[{"type":"output_text",
                        "text":json.dumps({"status":"not_published","period":None,"notes":"",
                             "warnings":[],"items":[]})}]}],
                        "usage":{"input_tokens":100,"output_tokens":40}}
        with patch.object(ai.SESSION,"post",return_value=FakeResponse()) as mock:
            result,usage=ai.call_model("fake-key","gpt-6.1-terra",[{"role":"user","content":[]}])
        self.assertEqual(result["status"],"not_published")
        self.assertEqual(usage["input_tokens"],100)
        self.assertTrue(mock.call_args.kwargs["json"]["text"]["format"]["strict"])
        self.assertFalse(mock.call_args.kwargs["json"]["store"])

    def test_short_outage_is_retried_and_auth_error_is_not(self):
        payload={"status":"not_published","period":None,"notes":"","warnings":[],"items":[]}
        class Reply:
            def __init__(self,code):self.status_code=code;self.text="detail"
            def json(self):
                return {"status":"completed","output":[{"type":"message","content":[
                    {"type":"output_text","text":json.dumps(payload)}]}],"usage":{}}
        waits=[]
        # Überlastung und ein Verbindungsabbruch: danach klappt es ohne Zutun.
        with patch.object(ai.SESSION,"post",side_effect=[Reply(503),ai.requests.ConnectionError("reset"),Reply(200)]) as post:
            result,_=ai.call_model("fake-key","gpt-6-luna",[],sleep=waits.append)
        self.assertEqual(result["status"],"not_published")
        self.assertEqual(post.call_count,3)
        self.assertEqual(waits,list(ai.RETRY_WAITS[:2]))
        # Falscher Schlüssel: sofortiger Fehler, kein sinnloses Wiederholen.
        waits.clear()
        with patch.object(ai.SESSION,"post",return_value=Reply(401)) as post:
            with self.assertRaisesRegex(ValueError,"HTTP 401"):
                ai.call_model("fake-key","gpt-6-luna",[],sleep=waits.append)
        self.assertEqual((post.call_count,waits),(1,[]))
        # Dauerhafte Störung: begrenzte Versuche, dann klarer Fehler.
        with patch.object(ai.SESSION,"post",return_value=Reply(529)) as post:
            with self.assertRaisesRegex(ValueError,"vorübergehend nicht verfügbar"):
                ai.call_model("fake-key","gpt-6-luna",[],sleep=waits.append)
        self.assertEqual(post.call_count,len(ai.RETRY_WAITS)+1)

    def test_correction_request_keeps_the_source_and_names_the_findings(self):
        original=[{"role":"user","content":[{"type":"input_text","text":"QUELLE"}]}]
        follow=ai.correction_inputs(original,{"status":"found","items":[{"name":"Suppe"}]},
                                    ["Preis fehlt [2026-11-16 · Menüoption · Smart Menü]"])
        self.assertEqual(follow[0],original[0])
        self.assertEqual(len(original),1)
        text=follow[-1]["content"][0]["text"]
        for expected in ("NICHT freigegeben","Preis fehlt [2026-11-16 · Menüoption · Smart Menü]",
                         "nichts erfinden",'"name": "Suppe"'):
            self.assertIn(expected,text)

    def test_render_html_escapes_source_data(self):
        report={"week_start":"2026-11-02","checked_at":"now","model":"gpt-6-luna",
                "api_calls":1,"restaurants":{"lia":{"name":"Lia","sources":[],
                "production":{"status":"empty","items":[]},"result":{"status":"found",
                  "notes":"<img src=x onerror=alert(1)>","warnings":[],"items":[]}}}}
        html=ai.html_report(report)
        self.assertIn("&lt;img",html)
        self.assertNotIn("<img src=x",html)

if __name__=="__main__":
    unittest.main()
