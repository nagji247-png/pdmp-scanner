import unittest
from mcx_oi_forward_backtest import evaluate_forward_price_oi


def session(day, gold_close, gold_oi, silver_close=100, silver_oi=10):
    return {"date": day, "contract_rows": [
        {"Symbol": "GOLD", "ExpiryDate": "04DEC2026", "Close": gold_close, "OpenInterest": gold_oi},
        {"Symbol": "SILVER", "ExpiryDate": "05DEC2026", "Close": silver_close, "OpenInterest": silver_oi},
    ]}


class MCXForwardBacktestTests(unittest.TestCase):
    def test_uses_same_contract_and_next_archived_session(self):
        archive = {"records": [
            session("2026-11-02", 100, 10, 200, 20),
            session("2026-11-03", 102, 12, 202, 22),
            session("2026-11-04", 103, 13, 203, 23),
        ]}
        result = evaluate_forward_price_oi(archive, min_signal_sessions=1)
        self.assertEqual(result["observations"], 2)
        self.assertEqual(result["signal_sessions"], 1)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["by_symbol"]["GOLD"]["signal_sessions"], 1)
        self.assertEqual(result["by_symbol"]["SILVER"]["signal_sessions"], 1)
        self.assertEqual(result["sample"][0]["signal_date"], "2026-11-03")
        self.assertEqual(result["sample"][0]["outcome_date"], "2026-11-04")
        self.assertEqual(result["sample"][0]["price_oi_regime"], "price_up_oi_up")
        self.assertFalse(result["included_in_asset_final"])
        self.assertFalse(result["trading_signal"])
        insufficient = evaluate_forward_price_oi(archive)
        self.assertEqual(insufficient["status"], "insufficient_sample")
        self.assertEqual(insufficient["by_symbol"]["GOLD"]["status"], "insufficient_sample")
        self.assertEqual(insufficient["by_symbol"]["SILVER"]["status"], "insufficient_sample")

    def test_no_observation_when_expiry_rolls_or_contract_missing(self):
        archive = {"records": [
            {"date": "2026-11-02", "contract_rows": [
                {"Symbol": "GOLD", "ExpiryDate": "04DEC2026", "Close": 100, "OpenInterest": 10}]},
            {"date": "2026-11-03", "contract_rows": [
                {"Symbol": "GOLD", "ExpiryDate": "05FEB2027", "Close": 102, "OpenInterest": 12}]},
            {"date": "2026-11-04", "contract_rows": [
                {"Symbol": "GOLD", "ExpiryDate": "05FEB2027", "Close": 103, "OpenInterest": 13}]},
        ]}
        result = evaluate_forward_price_oi(archive)
        self.assertEqual(result["observations"], 0)
        self.assertEqual(result["status"], "insufficient_sample")

    def test_rejects_duplicate_contract_and_duplicate_dates(self):
        duplicate = session("2026-11-02", 100, 10)
        duplicate["contract_rows"].append(dict(duplicate["contract_rows"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate contract"):
            evaluate_forward_price_oi({"records": [duplicate]})
        with self.assertRaisesRegex(ValueError, "duplicate or non-increasing"):
            evaluate_forward_price_oi({"records": [
                session("2026-11-02", 100, 10), session("2026-11-02", 101, 11)]})

    def test_rejects_invalid_price_or_oi(self):
        bad = session("2026-11-02", 100, 10)
        bad["contract_rows"][0]["OpenInterest"] = -1
        with self.assertRaisesRegex(ValueError, "invalid price/OI"):
            evaluate_forward_price_oi({"records": [bad]})

    def test_flat_next_session_is_not_counted_as_contrarian_hit(self):
        result = evaluate_forward_price_oi({"records": [
            session("2026-11-02", 100, 10),
            session("2026-11-03", 102, 12),
            session("2026-11-04", 102, 13),
        ]})
        bucket = result["regimes"]["price_up_oi_up"]
        self.assertEqual(bucket["next_flat"], 1)
        self.assertEqual(bucket["contrarian_hits"], 0)


if __name__ == "__main__":
    unittest.main()
