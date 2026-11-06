import unittest
from datetime import datetime, timezone

from component_scoring import (
    build_component,
    clamp_score,
    combine_components,
    client_oi_context,
    is_fresh_timestamp,
    search_component_from_snapshot,
)


class ComponentScoringHelperTests(unittest.TestCase):
    def test_clamp_and_reject_non_finite_values(self):
        self.assertEqual(clamp_score(15), 10.0)
        self.assertEqual(clamp_score(-15), -10.0)
        self.assertIsNone(clamp_score(None))
        self.assertIsNone(clamp_score(float("nan")))
        self.assertIsNone(clamp_score(float("inf")))

    def test_only_verified_components_enter_renormalized_final(self):
        news = build_component(6, "Google News RSS", "2026-11-06", 40)
        result = combine_components({"news": news, "search": None, "eod_oi": None})
        self.assertEqual(result["score"], 6.0)
        self.assertEqual(result["included_components"], ["news"])
        self.assertEqual(result["normalized_weights_pct"], {"news": 100.0})

    def test_weighted_mean_uses_only_present_components(self):
        news = build_component(10, "Google News RSS", "2026-11-06", 40)
        search = build_component(-10, "Google Trends", "2026-11-06", 40)
        result = combine_components({"news": news, "search": search})
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["normalized_weights_pct"], {"news": 50.0, "search": 50.0})

    def test_stale_and_wrong_timeframe_search_are_rejected(self):
        now = datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)
        self.assertTrue(is_fresh_timestamp("2026-11-06T01:00:00Z", now, 120))
        self.assertFalse(is_fresh_timestamp("2026-11-05T23:00:00Z", now, 120))
        snapshot = {
            "valid": True, "timeframe": "now 7-d",
            "source_data_time": "2026-11-06T01:00:00Z",
            "neutral_aware_score": 5, "directional_bull_pct": 50,
        }
        component, reason = search_component_from_snapshot(snapshot, now_utc=now)
        self.assertIsNone(component)
        self.assertIn("now 1-d", reason)

    def test_neutral_only_search_is_diagnostic_not_a_zero_score(self):
        snapshot = {
            "valid": True, "timeframe": "now 1-d",
            "source_data_time": "2026-11-06T01:00:00Z",
            "neutral_aware_score": 0, "directional_bull_pct": None,
        }
        component, reason = search_component_from_snapshot(
            snapshot, now_utc=datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)
        )
        self.assertIsNone(component)
        self.assertIn("directional evidence", reason)

    def test_client_oi_is_market_wide_context_not_asset_final(self):
        context = client_oi_context(
            {"ok": True, "stale": False, "date": "2026-11-05"},
            {"ok": True, "prev_date": "2026-11-04", "by_group": {"CLIENT": {
                "index_call_long": 11, "index_call_short": -12,
                "index_put_long": 13, "index_put_short": -14,
                "future_index_long": 15, "future_index_short": -16,
            }}},
        )
        self.assertTrue(context["available"])
        self.assertFalse(context["included_in_asset_final"])
        self.assertEqual(context["ce_build_up"]["call_long_change"], 11)
        self.assertEqual(context["pe_build_up"]["put_short_change"], -14)
        self.assertIn("not index-specific", context["scope"])


    def test_nse_udiff_index_option_oi_is_separate_and_fail_closed(self):
        from component_scoring import aggregate_nse_udiff_index_option_oi

        rows = [
            {"FinInstrmTp": "OPTIDX", "TckrSymb": "NIFTY", "BizDt": "2026-11-05",
             "XpryDt": "2026-11-10", "OptnTp": "CE", "OpnIntrst": "1000",
             "ChngInOpnIntrst": "125"},
            {"FinInstrmTp": "OPTIDX", "TckrSymb": "NIFTY", "BizDt": "2026-11-05",
             "XpryDt": "2026-11-10", "OptnTp": "PE", "OpnIntrst": "1500",
             "ChngInOpnIntrst": "-75"},
            {"FinInstrmTp": "OPTIDX", "TckrSymb": "BANKNIFTY", "BizDt": "2026-11-05",
             "XpryDt": "2026-11-10", "OptnTp": "CE", "OpnIntrst": "9000",
             "ChngInOpnIntrst": "900"},
        ]
        result = aggregate_nse_udiff_index_option_oi(rows, "NIFTY", "2026-11-05")
        self.assertTrue(result["available"])
        self.assertFalse(result["included_in_asset_final"])
        self.assertEqual(result["call"]["open_interest"], 1000)
        self.assertEqual(result["call"]["change_in_oi"], 125)
        self.assertEqual(result["put"]["open_interest"], 1500)
        self.assertEqual(result["put"]["change_in_oi"], -75)
        self.assertEqual(result["matched_contract_rows"], 2)
        self.assertEqual(result["symbol"], "NIFTY")

    def test_nse_udiff_oi_rejects_missing_side_and_bad_date(self):
        from component_scoring import aggregate_nse_udiff_index_option_oi

        rows = [
            {"FinInstrmTp": "OPTIDX", "TckrSymb": "SENSEX", "BizDt": "2026-11-05",
             "XpryDt": "2026-11-12", "OptnTp": "CE", "OpnIntrst": "500",
             "ChngInOpnIntrst": "50"},
            {"FinInstrmTp": "OPTIDX", "TckrSymb": "SENSEX", "BizDt": "2026-11-04",
             "XpryDt": "2026-11-12", "OptnTp": "PE", "OpnIntrst": "700",
             "ChngInOpnIntrst": "70"},
        ]
        result = aggregate_nse_udiff_index_option_oi(rows, "SENSEX", "2026-11-05")
        self.assertFalse(result["available"])
        self.assertFalse(result["included_in_asset_final"])
        self.assertIsNotNone(result["reason"])
        self.assertIn("trade_date_mismatch_or_missing", result["validation_warnings"])


    def test_mcx_public_bhavcopy_compares_exact_contract(self):
        from component_scoring import compare_mcx_bhavcopy_contract_oi
        now = [{"InstrumentName":"FUTCOM", "Symbol":"GOLD", "DateDisplay":"05 Nov 2026", "ExpiryDate":"04DEC2026", "OptionType":"-", "OpenInterest":15716, "Close":144095}]
        before = [{"InstrumentName":"FUTCOM", "Symbol":"GOLD", "DateDisplay":"04 Nov 2026", "ExpiryDate":"04DEC2026", "OptionType":"-", "OpenInterest":16095, "Close":143234}]
        result = compare_mcx_bhavcopy_contract_oi(now, before, "GOLD", "2026-11-05", "2026-11-04", "2026-12-04")
        self.assertTrue(result["available"])
        self.assertFalse(result["included_in_asset_final"])
        self.assertEqual(result["change_in_oi_lots"], -379)
        self.assertEqual(result["change_in_close"], 861.0)
        self.assertEqual(result["price_oi_regime"], "price_up_oi_down")

    def test_mcx_public_bhavcopy_rejects_duplicate_contract_rows(self):
        from component_scoring import compare_mcx_bhavcopy_contract_oi
        row = {"InstrumentName":"FUTCOM", "Symbol":"SILVER", "DateDisplay":"05 Nov 2026", "ExpiryDate":"04DEC2026", "OptionType":"-", "OpenInterest":100, "Close":180000}
        prior = [{"InstrumentName":"FUTCOM", "Symbol":"SILVER", "DateDisplay":"04 Nov 2026", "ExpiryDate":"04DEC2026", "OptionType":"-", "OpenInterest":120, "Close":181000}]
        result = compare_mcx_bhavcopy_contract_oi([row, dict(row)], prior, "SILVER", "2026-11-05", "2026-11-04", "2026-12-04")
        self.assertFalse(result["available"])
        self.assertFalse(result["included_in_asset_final"])
    def test_mcx_udiff_futures_oi_requires_exact_symbol_expiry_date_and_fields(self):
        from component_scoring import aggregate_mcx_udiff_commodity_futures_oi

        rows = [
            {"Sgmt": "CO", "Src": "MCX", "FinInstrmTp": "FUTCOM",
             "TckrSymb": "GOLD", "BizDt": "2026-11-05", "XpryDt": "2026-12-05",
             "OpnIntrst": "12500", "ChngInOpnIntrst": "850", "ClsPric": "154000"},
            {"Sgmt": "CO", "Src": "MCX", "FinInstrmTp": "FUTCOM",
             "TckrSymb": "SILVER", "BizDt": "2026-11-05", "XpryDt": "2026-12-05",
             "OpnIntrst": "99999", "ChngInOpnIntrst": "-10", "ClsPric": "180000"},
            {"Sgmt": "CO", "Src": "MCX", "FinInstrmTp": "FUTCOM",
             "TckrSymb": "GOLD", "BizDt": "2026-11-05", "XpryDt": "2027-01-05",
             "OpnIntrst": "77777", "ChngInOpnIntrst": "20", "ClsPric": "155000"},
        ]
        result = aggregate_mcx_udiff_commodity_futures_oi(
            rows, "GOLD", "2026-11-05", "2026-12-05"
        )
        self.assertTrue(result["available"])
        self.assertFalse(result["included_in_asset_final"])
        self.assertFalse(result["coverage_validated"])
        self.assertEqual(result["open_interest"], 12500)
        self.assertEqual(result["change_in_oi"], 850)
        self.assertEqual(result["close"], 154000.0)
        self.assertEqual(result["matched_contract_rows"], 1)

    def test_mcx_udiff_futures_oi_rejects_duplicate_or_incomplete_exact_rows(self):
        from component_scoring import aggregate_mcx_udiff_commodity_futures_oi

        base = {"Sgmt": "CO", "Src": "MCX", "FinInstrmTp": "FUTCOM",
                "TckrSymb": "SILVER", "BizDt": "2026-11-05", "XpryDt": "2026-12-05",
                "OpnIntrst": "500", "ChngInOpnIntrst": "50", "ClsPric": "180000"}
        duplicate = aggregate_mcx_udiff_commodity_futures_oi(
            [base, dict(base)], "SILVER", "2026-11-05", "2026-12-05"
        )
        self.assertFalse(duplicate["available"])
        self.assertFalse(duplicate["included_in_asset_final"])
        incomplete = dict(base)
        incomplete["ChngInOpnIntrst"] = ""
        rejected = aggregate_mcx_udiff_commodity_futures_oi(
            [incomplete], "SILVER", "2026-11-05", "2026-12-05"
        )
        self.assertFalse(rejected["available"])
        self.assertIsNotNone(rejected["reason"])


if __name__ == "__main__":
    unittest.main()
