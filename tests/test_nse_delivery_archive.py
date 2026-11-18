import unittest
from nse_delivery_archive import parse_delivery_csv

class DeliveryArchiveTests(unittest.TestCase):
    def test_parses_eq_delivery_and_ignores_other_series(self):
        raw = ("SYMBOL, SERIES, DATE1, TTL_TRD_QNTY, DELIV_QTY, DELIV_PER\\n"
               "ABC, EQ, 18-Nov-2026, 100000, 60000, 60.00\\n"
               "ABC, BE, 18-Nov-2026, 100, -, -\\n").encode()
        result = parse_delivery_csv(raw, "2026-11-18", min_rows=1)
        self.assertEqual(result["ABC"]["delivery_qty"], 60000)
        self.assertEqual(result["ABC"]["delivery_pct"], 60.0)
        self.assertEqual(result["ABC"]["traded_qty"], 100000)

    def test_dash_is_missing_not_zero(self):
        raw = ("SYMBOL,SERIES,DATE1,TTL_TRD_QNTY,DELIV_QTY,DELIV_PER\\n"
               "ABC,EQ,18-Nov-2026,100000,-,-\\n").encode()
        result = parse_delivery_csv(raw, "2026-11-18", min_rows=1)
        self.assertIsNone(result["ABC"]["delivery_qty"])
        self.assertIsNone(result["ABC"]["delivery_pct"])

    def test_wrong_date_duplicate_and_inconsistent_pct_fail(self):
        head = "SYMBOL,SERIES,DATE1,TTL_TRD_QNTY,DELIV_QTY,DELIV_PER\\n"
        with self.assertRaises(ValueError):
            parse_delivery_csv((head+"ABC,EQ,17-Nov-2026,100000,60000,60\\n").encode(), "2026-11-18", min_rows=1)
        with self.assertRaises(ValueError):
            parse_delivery_csv((head+"ABC,EQ,18-Nov-2026,100000,60000,60\\nABC,EQ,18-Nov-2026,100000,60000,60\\n").encode(), "2026-11-18", min_rows=1)
        with self.assertRaises(ValueError):
            parse_delivery_csv((head+"ABC,EQ,18-Nov-2026,100000,60000,30\\n").encode(), "2026-11-18", min_rows=1)

if __name__ == "__main__": unittest.main()
