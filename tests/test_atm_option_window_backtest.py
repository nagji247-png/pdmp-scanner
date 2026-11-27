import unittest

from atm_option_window_backtest import build_report, score_window


def make_record(day, expiry, premium_offset=0, oi_offset=0):
    contracts_by_symbol = {"NIFTY": [], "BANKNIFTY": []}
    for symbol, first_strike, step in (("NIFTY", 24000, 50), ("BANKNIFTY", 51000, 100)):
        for i in range(21):
            strike = first_strike + i * step
            for side in ("CE", "PE"):
                base = 100.0 if side == "CE" else 95.0
                contracts_by_symbol[symbol].append({
                    "expiry": expiry,
                    "side": side,
                    "strike": strike,
                    "close": base + premium_offset if side == "CE" else base - premium_offset,
                    "open_interest": 1000 + oi_offset,
                })
    return {
        "date": day,
        "option_contracts": {
            symbol: {"contracts": contracts}
            for symbol, contracts in contracts_by_symbol.items()
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

    def test_banknifty_fixture_uses_its_own_strike_interval(self):
        previous = make_record("2026-11-16", "2026-11-24")
        current = make_record("2026-11-17", "2026-11-24", 1, 10)
        result = score_window(previous, current, "BANKNIFTY", 52000, 5)
        self.assertTrue(result["available"])
        self.assertEqual(result["selected_strikes"], [51500, 51600, 51700, 51800, 51900, 52000, 52100, 52200, 52300, 52400, 52500])

    def test_missing_entire_strike_is_not_silently_skipped(self):
        previous = make_record("2026-11-16", "2026-11-24")
        current = make_record("2026-11-17", "2026-11-24", 1, 10)
        for record in (previous, current):
            record["option_contracts"]["NIFTY"]["contracts"] = [
                row for row in record["option_contracts"]["NIFTY"]["contracts"]
                if row["strike"] != 24500
            ]
        result = score_window(previous, current, "NIFTY", 24500, 5)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "non_contiguous_strike_ladder")

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

    def test_unclassified_contracts_report_zero_premium_and_zero_oi_reasons(self):
        previous = make_record("2026-11-16", "2026-11-24")
        current = make_record("2026-11-17", "2026-11-24", 1, 10)
        # One CE has unchanged premium; one PE has unchanged OI.
        for row in current["option_contracts"]["NIFTY"]["contracts"]:
            if row["strike"] == 24500 and row["side"] == "CE":
                row["close"] = 100.0
            if row["strike"] == 24550 and row["side"] == "PE":
                row["open_interest"] = 1000
        result = score_window(previous, current, "NIFTY", 24500, 5)
        self.assertEqual(result["matched_contracts"], 22)
        self.assertEqual(result["classified_contracts"], 20)
        self.assertEqual(result["classification_exclusions_by_reason"], {
            "ZERO_PREMIUM_CHANGE": 1, "ZERO_OI_CHANGE": 1
        })
        excluded = {(row["strike"], row["side"]): row for row in result["unclassified_contracts"]}
        self.assertEqual(excluded[(24500, "CE")]["reason"], "ZERO_PREMIUM_CHANGE")
        self.assertEqual(excluded[(24500, "CE")]["premium_change"], 0)
        self.assertEqual(excluded[(24550, "PE")]["reason"], "ZERO_OI_CHANGE")
        self.assertEqual(excluded[(24550, "PE")]["oi_change"], 0)
        self.assertTrue(all(row["signal_date"] == "2026-11-17" for row in excluded.values()))

    def test_distance_bands_split_contracts_and_keep_ce_pe_details(self):
        previous = make_record("2026-11-16", "2026-11-24")
        current = make_record("2026-11-17", "2026-11-24", 1, 10)
        result = score_window(previous, current, "NIFTY", 24500, 5)
        bands = result["distance_bands"]
        self.assertEqual(set(bands), {"ATM", "ATM_1_2", "ATM_3_5"})
        self.assertEqual(bands["ATM"]["matched_contracts"], 2)
        self.assertEqual(bands["ATM_1_2"]["matched_contracts"], 8)
        self.assertEqual(bands["ATM_3_5"]["matched_contracts"], 12)
        self.assertEqual(len(result["contract_details"]), 22)
        self.assertEqual(result["contract_details"][0]["distance_from_atm_steps"], 5)
        self.assertIn(result["contract_details"][0]["distance_band"], bands)
        self.assertEqual(bands["ATM"]["by_side"]["CE"]["classified_contracts"], 1)
        self.assertEqual(bands["ATM"]["by_side"]["PE"]["classified_contracts"], 1)

    def test_distance_band_summaries_are_reported_for_each_asset(self):
        previous = make_record("2026-11-16", "2026-11-24")
        signal = make_record("2026-11-17", "2026-11-24", 1, 100)
        oi = {"records": [previous, signal]}
        closes = {"records": [
            make_close("2026-11-16", 24500, 52000),
            make_close("2026-11-17", 24500, 52000),
            make_close("2026-11-18", 24400, 51900),
        ]}
        report = build_report(oi, closes)
        summary = report["by_asset"]["NIFTY"]["summary"]["atm_plus_minus_5"]
        self.assertIn("distance_atm", summary)
        self.assertIn("distance_atm_1_2", summary)
        self.assertIn("distance_atm_3_5", summary)
        self.assertNotIn("distance_atm_6_10", summary)

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
