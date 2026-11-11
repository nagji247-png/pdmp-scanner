import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("probe", "tools/youtube_crowd_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class ProbeTests(unittest.TestCase):
    def test_direction_keywords(self):
        self.assertEqual(probe.classify("Nifty rally and strong breakout"), "BULLISH")
        self.assertEqual(probe.classify("Nifty crash and market fall"), "BEARISH")
        self.assertEqual(probe.classify("Nifty sideways range-bound"), "NEUTRAL")
    def test_empty_text_is_neutral(self):
        self.assertEqual(probe.classify(""), "NEUTRAL")
    def test_six_assets(self):
        self.assertEqual(set(probe.ASSETS), {"NIFTY","SENSEX","BANKNIFTY","GOLD","SILVER","CRUDEOIL"})

    def test_missing_api_key_fails_closed_without_production_write(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": ""}), redirect_stdout(output):
            status = probe.main()
        self.assertEqual(status, 2)
        result = __import__("json").loads(output.getvalue())
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["production_write"])

    def test_transcripts_are_explicitly_not_claimed(self):
        source = open("tools/youtube_crowd_probe.py", encoding="utf-8").read()
        self.assertIn('NOT_AVAILABLE_VIA_PUBLIC_DATA_API', source)
        self.assertIn('"production_write":False', source)

    def test_queries_use_alternatives(self):
        for query in probe.ASSETS.values():
            self.assertIn("|", query)
            self.assertTrue(any(ord(ch) > 127 for ch in query), "Hindi terms should be included")

if __name__ == "__main__":
    unittest.main()
