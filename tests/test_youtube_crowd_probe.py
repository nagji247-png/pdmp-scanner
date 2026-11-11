import importlib.util
import unittest

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

if __name__ == "__main__":
    unittest.main()
