import unittest

from atm_option_window_backtest import build_report, score_window


def make_record(day, expiry, premium_offset=0, oi_offset=0):
    contracts = []
    for i in range(21):
        strike = 24000 + i * 50
        for side in ("CE", "PE"):
            base = 100.0 if side == "CE" else 95.0
            contracts.append({
                "expiry": expiry,
                "side": side,
                "strike": strike,
                "close": base + premium_offset if side == "CE" else base - premium_offset,
                "open_interest": 1000 + oi_offset,
            })
    return {
        "date": day,
        "option_contracts": {
            "NIFTY": {"contracts": contracts},
            "BANKNIFTY": {"contracts": contracts},
        },
    }


def make_close(day, nifty, bank):
    return {"date": day, "indices": {"Nifty 50": nifty, "Nifty Bank": bank}}


class ATMOptionWindowBacktestTests(unittest.TestCase):
    def test_uses_nearest_common_unexpired_expiry_and_both_sides(self):
        previous = make_record("2026-11-16", "2026-11-17", 0, 0)
        current = make_record("2026-11-17", "2026-11-17", 10, 100)
        previous_next = make_record("2026-11-16", "2026-11-24", 0, 0)
        current_next = make_record("2026-11-17", "2026-11-24", 10, 100)
        previous["option_contracts"]["NIFTY"]["contracts"] += previous_next["option_contracts"]["NIFTY"]["contracts"]
        current["option_contracts"]["NIFTY"]["contracts"] += current_next["option_contracts"]["NIFTY"]["contracts"]

        result = score_window(previous, current, "NIFTY", 24500, 5)

        self.assertTrue(result["available"])
        self.assertEqual(result["expiry"], "2026-11-24")
        self.assertEqual(result["matched_contracts"], 22)
        self.assertEqual(result["classified_contracts"], 22)
        self.assertEqual(result["signal"], "BULLISH")
        self.assertEqual(result["by_side"]["CE"]["signal"], "BULLISH")
        self.assertEqual(result["by_side"]["PE"]["signal"], "BULLISH")

    def test_atm_plus_minus_ten_requires_twenty_one_strikes(self):
        previous = make_record("2026-11-16", "2026-11-24")
        current = make_record("2026-11-17", "2026-11-24", 1, 10)
        result = score_window(previous, current, "NIFTY", 24500, 10)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["selected_strikes"]), 21)
        self.assertEqual(result["matched_contracts"], 42)

    def test_incomplete_strike_coverage_fails_closed(self):
        previous = make_record("2026-11-16", "2026-11-24")
        current = make_record("2026-11-17", "2026-11-24", 1, 10)
        current["option_contracts"]["NIFTY"]["contracts"] = [
            row for row in current["option_contracts"]["NIFTY"]["contracts"]
            if not (row["strike"] == 24500 and row["side"] == "PE")
        ]
        result = score_window(previous, current, "NIFTY", 24500, 10)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "incomplete_contract_pair")

    def test_missing_leg_does_not_shift_or_expand_the_listed_strike_window(self):
        previous = make_record("2026-11-16", "2026-11-24")
        current = make_record("2026-11-17", "2026-11-24", 1, 10)
        # Add three outer strikes on both sides so an implementation that
        # drops incomplete strikes could otherwise replace the missing ATM.
        for strike in (23850, 23900, 23950, 25050, 25100, 25150):
            for record, premium, oi in ((previous, 0, 0), (current, 1, 10)):
                for side in ("CE", "PE"):
                    record["option_contracts"]["NIFTY"]["contracts"].append({
                        "expiry": "2026-11-24", "side": side, "strike": strike,
                        "close": (100 if side == "CE" else 95) + (premium if side == "CE" else -premium),
                        "open_interest": 1000 + oi,
                    })
        current["option_contracts"]["NIFTY"]["contracts"] = [
            row for row in current["option_contracts"]["NIFTY"]["contracts"]
            if not (row["strike"] == 24500 and row["side"] == "PE")
        ]

        result = score_window(previous, current, "NIFTY", 24500, 10)

        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "incomplete_contract_pair")

    def test_report_uses_next_archived_session_close_and_stays_research_only(self):
        previous = make_record("2026-11-16", "2026-11-24")
        signal = make_record("2026-11-17", "2026-11-24", 1, 100)
        oi = {"records": [previous, signal]}
        closes = {"records": [
            make_close("2026-11-16", 24500, 52000),
            make_close("2026-11-17", 24500, 52000),
            make_close("2026-11-18", 24400, 51900),
        ]}

        report = build_report(oi, closes)

        self.assertEqual(report["status"], "exploratory_only")
        self.assertFalse(report["production_score_changed"])
        self.assertFalse(report["eligible_for_live_score"])
        self.assertEqual(report["by_asset"]["NIFTY"]["observations"][0]["next_session_date"], "2026-11-18")
        summary = report["by_asset"]["NIFTY"]["summary"]["atm_plus_minus_5"]
        self.assertEqual(summary["directional_samples"], 1)
        self.assertEqual(summary["crowd_follow_accuracy_pct"], 0.0)
        self.assertEqual(summary["contrarian_accuracy_pct"], 100.0)
        self.assertEqual(report["sensex"]["status"], "not_tested")


if __name__ == "__main__":
    unittest.main()
