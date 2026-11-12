import unittest

from component_scoring import build_component, combine_components
from provisional_component_scoring import (
    PROVISIONAL_WEIGHTS,
    client_marketwide_components,
    index_oi_balance_component,
    source_date_is_fresh,
)


class ProvisionalComponentScoringTests(unittest.TestCase):
    def test_source_date_freshness_rejects_stale_future_and_missing_dates(self):
        self.assertTrue(source_date_is_fresh("2026-11-08", "2026-11-11"))
        self.assertTrue(source_date_is_fresh("2026-11-11", "2026-11-11"))
        self.assertFalse(source_date_is_fresh("2026-11-06", "2026-11-11"))
        self.assertFalse(source_date_is_fresh("2026-11-12", "2026-11-11"))
        self.assertFalse(source_date_is_fresh(None, "2026-11-11"))

    def test_user_approved_weights_are_configured(self):
        self.assertEqual(PROVISIONAL_WEIGHTS, {
            "news": 15.0,
            "stock_basket": 20.0,
            "eod_oi": 15.0,
            "client_ce_pe": 15.0,
            "client_futures": 15.0,
            "search": 20.0,
        })
        self.assertEqual(sum(PROVISIONAL_WEIGHTS.values()), 100.0)

    def test_all_six_components_use_weighted_average(self):
        scores = {
            "news": 2,
            "stock_basket": 6,
            "eod_oi": 4,
            "client_ce_pe": -2,
            "client_futures": 5,
            "search": 3,
        }
        components = {
            name: build_component(score, name, "2026-11-06", PROVISIONAL_WEIGHTS[name])
            for name, score in scores.items()
        }
        result = combine_components(components, PROVISIONAL_WEIGHTS)
        self.assertEqual(result["score"], 3.15)
        self.assertEqual(result["included_components"], list(scores))
        self.assertEqual(result["weight_total"], 100.0)

    def test_missing_components_renormalize_available_weights(self):
        components = {
            "news": build_component(2, "News", "2026-11-06", PROVISIONAL_WEIGHTS["news"]),
            "stock_basket": build_component(8, "Official basket", "2026-11-06", PROVISIONAL_WEIGHTS["stock_basket"]),
        }
        result = combine_components(components, PROVISIONAL_WEIGHTS)
        self.assertEqual(result["score"], 5.43)
        self.assertEqual(result["included_components"], ["news", "stock_basket"])
        self.assertEqual(result["normalized_weights_pct"], {
            "news": 42.86, "stock_basket": 57.14
        })

    def test_nearest_expiry_oi_balance_averages_available_sessions(self):
        archive = {
            "records": [
                {
                    "date": "2026-11-04",
                    "symbols": {"NIFTY": {"by_expiry": {
                        "2026-11-05": {
                            "CE": {"open_interest": 100, "contracts": 10},
                            "PE": {"open_interest": 300, "contracts": 10},
                        },
                        "2026-11-26": {
                            "CE": {"open_interest": 900, "contracts": 10},
                            "PE": {"open_interest": 100, "contracts": 10},
                        },
                    }}},
                },
                {
                    "date": "2026-11-05",
                    "symbols": {"NIFTY": {"by_expiry": {
                        "2026-11-06": {
                            "CE": {"open_interest": 200, "contracts": 10},
                            "PE": {"open_interest": 200, "contracts": 10},
                        },
                    }}},
                },
                {
                    "date": "2026-11-06",
                    "symbols": {"NIFTY": {"by_expiry": {
                        "2026-11-23": {
                            "CE": {"open_interest": 100, "contracts": 10},
                            "PE": {"open_interest": 300, "contracts": 10},
                        },
                    }}},
                },
            ]
        }
        component = index_oi_balance_component(
            archive, "NIFTY", "2026-11-06", weight=PROVISIONAL_WEIGHTS["eod_oi"]
        )
        self.assertIsNotNone(component)
        self.assertEqual(component["score"], 3.33)
        self.assertEqual(component["source_date"], "2026-11-06")
        self.assertEqual(component["observations"], 3)
        self.assertEqual(component["session_dates"], [
            "2026-11-04", "2026-11-05", "2026-11-06"
        ])

    def test_oi_balance_rejects_missing_or_incomplete_contract_sides(self):
        archive = {"records": [{
            "date": "2026-11-06",
            "symbols": {"BANKNIFTY": {"by_expiry": {
                "2026-11-23": {
                    "CE": {"open_interest": 100, "contracts": 10},
                    "PE": {"open_interest": 100, "contracts": 0},
                },
            }}},
        }]}
        self.assertIsNone(index_oi_balance_component(
            archive, "BANKNIFTY", "2026-11-06"
        ))

    def test_oi_balance_rejects_stale_archive_even_when_old_rows_are_valid(self):
        archive = {"records": [{
            "date": "2026-11-06",
            "symbols": {"NIFTY": {"by_expiry": {
                "2026-11-26": {
                    "CE": {"open_interest": 100, "contracts": 10},
                    "PE": {"open_interest": 300, "contracts": 10},
                },
            }}},
        }]}
        self.assertIsNone(index_oi_balance_component(
            archive, "NIFTY", "2026-11-11",
            weight=PROVISIONAL_WEIGHTS["eod_oi"],
        ))

    def test_marketwide_client_ce_pe_quantity_score_is_separate_from_futures(self):
        evidence = {
            "ce_long": {"change": 10, "change_pct_prior_gross": 5.0, "contrarian_bias": "bearish"},
            "ce_short": {"change": 5, "change_pct_prior_gross": 5.0, "contrarian_bias": "bullish"},
            "pe_long": {"change": 4, "change_pct_prior_gross": 5.0, "contrarian_bias": "bullish"},
            "pe_short": {"change": 2, "change_pct_prior_gross": 5.0, "contrarian_bias": "bearish"},
            "futures_long": {"change": 4, "change_pct_prior_gross": 4.0, "contrarian_bias": "bearish"},
            "futures_short": {"change": 2, "change_pct_prior_gross": 2.0, "contrarian_bias": "bullish"},
        }
        result = client_marketwide_components({
            "available": True,
            "source": "NSE participant-wise OI",
            "source_date": "2026-11-06",
            "previous_date": "2026-11-05",
            "evidence_components": evidence,
        })
        self.assertEqual(set(result), {"client_ce_pe"})
        self.assertAlmostEqual(result["client_ce_pe"]["score"], 10.0 * 3 / 21, places=4)
        self.assertEqual(result["client_ce_pe"]["call_net_change"], 5)
        self.assertEqual(result["client_ce_pe"]["put_net_change"], -2)
        self.assertEqual(result["client_ce_pe"]["combined_net_change"], 3)
        self.assertEqual(result["client_ce_pe"]["directional_reading"], "bullish_client_positioning")
        self.assertIn("market-wide", result["client_ce_pe"]["scope"])
        self.assertTrue(result["client_ce_pe"]["not_validated_predictor"])

    def test_client_components_reject_stale_participant_report(self):
        evidence = {
            "ce_long": {"change_pct_prior_gross": 5.0, "contrarian_bias": "bearish"},
            "ce_short": {"change_pct_prior_gross": 5.0, "contrarian_bias": "bullish"},
            "pe_long": {"change_pct_prior_gross": 5.0, "contrarian_bias": "bullish"},
            "pe_short": {"change_pct_prior_gross": 5.0, "contrarian_bias": "bearish"},
            "futures_long": {"change_pct_prior_gross": 4.0, "contrarian_bias": "bearish"},
            "futures_short": {"change_pct_prior_gross": 2.0, "contrarian_bias": "bullish"},
        }
        self.assertEqual(client_marketwide_components({
            "available": True,
            "source": "NSE participant-wise OI",
            "source_date": "2026-11-06",
            "evidence_components": evidence,
        }, scan_date="2026-11-11"), {})

    def test_client_scores_require_all_fields_and_dated_marketwide_context(self):
        result = client_marketwide_components({
            "available": True,
            "source_date": "2026-11-06",
            "evidence_components": {
                "ce_long": {"change_pct_prior_gross": 2, "contrarian_bias": "bearish"},
            },
        })
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
