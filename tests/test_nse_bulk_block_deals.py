import unittest
from nse_bulk_block_deals import parse_deal_csv, parse_day

class BulkBlockDealsTests(unittest.TestCase):
    def test_parses_disclosed_buyer_and_seller_rows(self):
        raw = ("Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Weighted Avg Price\n"
               "18-Nov-2026,ABC,ABC LTD,CLIENT ONE,BUY,250000,125.50\n"
               "18-Nov-2026,XYZ,XYZ LTD,CLIENT TWO,SELL,100000,80.25\n").encode()
        rows = parse_deal_csv(raw, "Bulk", parse_day("2026-11-18"))
        self.assertEqual(rows[0]["client"], "CLIENT ONE")
        self.assertEqual(rows[0]["side"], "BUY")
        self.assertEqual(rows[1]["side"], "SELL")
        self.assertEqual(rows[0]["quantity"], 250000)

    def test_only_exact_exchange_date_is_kept(self):
        raw = ("Date,Symbol,Client Name,Buy/Sell,Quantity Traded,Trade Price\n"
               "17-Nov-2026,ABC,CLIENT,BUY,1000,10\n").encode()
        self.assertEqual(parse_deal_csv(raw, "Block", parse_day("2026-11-18")), [])

    def test_missing_columns_or_invalid_trade_values_fail_closed(self):
        with self.assertRaises(ValueError):
            parse_deal_csv(b"Date,Symbol\n", "Bulk", parse_day("2026-11-18"))
        raw = ("Date,Symbol,Client Name,Buy/Sell,Quantity Traded,Trade Price\n"
               "18-Nov-2026,ABC,CLIENT,BUY,0,10\n").encode()
        with self.assertRaises(ValueError):
            parse_deal_csv(raw, "Bulk", parse_day("2026-11-18"))

if __name__ == "__main__": unittest.main()
