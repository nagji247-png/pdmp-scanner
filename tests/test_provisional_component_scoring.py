import unittest

from provisional_component_scoring import (
    PROVISIONAL_WEIGHTS,
    client_marketwide_components,
    index_oi_balance_component,
)


class ProvisionalComponentScoringTests(unittest.TestCase):
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

    def test_marketwide_client_ce_pe_and_futures_scores_are_separate(self):
        evidence = {
            "ce_long": {"change_pct_prior_gross": 5.0, "contrarian_bias": "bearish"},
            "ce_short": {"change_pct_prior_gross": 5.0, "contrarian_bias": "bullish"},
            "pe_long": {"change_pct_prior_gross": 5.0, "contrarian_bias": "bullish"},
            "pe_short": {"change_pct_prior_gross": 5.0, "contrarian_bias": "bearish"},
            "futures_long": {"change_pct_prior_gross": 4.0, "contrarian_bias": "bearish"},
            "futures_short": {"change_pct_prior_gross": 2.0, "contrarian_bias": "bullish"},
        }
        result = client_marketwide_components({
            "available": True,
            "source": "NSE participant-wise OI",
            "source_date": "2026-11-06",
            "previous_date": "2026-11-05",
            "evidence_components": evidence,
        })
        self.assertEqual(set(result), {"client_ce_pe", "client_futures"})
        self.assertEqual(result["client_ce_pe"]["score"], 0.0)
        self.assertEqual(result["client_futures"]["score"], -1.0)
        self.assertIn("market-wide", result["client_ce_pe"]["scope"])
        self.assertEqual(result["client_futures"]["source_date"], "2026-11-06")

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
