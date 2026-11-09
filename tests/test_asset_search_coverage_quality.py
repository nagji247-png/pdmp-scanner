import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

from fetch_and_score import (
    _asset_search_direction,
    _asset_search_is_out_of_scope,
    fetch_asset_trends_shadow,
)


class AssetSearchCoverageQualityTests(unittest.TestCase):
    def test_index_lookup_phrases_are_neutral_not_unclassified(self):
        cases = [
            ("nifty 50", "NIFTY"),
            ("gift nifty", "NIFTY"),
            ("nifty share price", "NIFTY"),
            ("bse sensex", "SENSEX"),
            ("sensex share", "SENSEX"),
            ("bank nifty 50", "BANKNIFTY"),
        ]
        for term, asset in cases:
            with self.subTest(term=term, asset=asset):
                self.assertEqual(_asset_search_direction(term, asset), "neutral")

    def test_cross_asset_terms_are_out_of_scope_not_unclassified(self):
        cases = [
            ("sensex", "NIFTY"),
            ("nifty", "SENSEX"),
            ("nifty share price", "BANKNIFTY"),
            ("silver price today", "GOLD"),
            ("gold price today", "SILVER"),
        ]
        for term, asset in cases:
            with self.subTest(term=term, asset=asset):
                self.assertTrue(_asset_search_is_out_of_scope(term, asset))

    def test_bare_commodity_price_is_not_relabelled_as_neutral(self):
        self.assertIsNone(_asset_search_direction("gold price", "GOLD"))
        self.assertIsNone(_asset_search_direction("silver rate", "SILVER"))

    def test_batch_coverage_excludes_cross_asset_queries_without_extra_requests(self):
        rows = {
            "nifty": [
                ("nifty 50", 100), ("nifty share price", 40),
                ("nifty sideways", 20), ("nifty rally", 10),
                ("nifty crash", 5), ("sensex", 50),
            ],
            "sensex": [
                ("bse sensex", 100), ("sensex share", 40),
                ("sensex today", 20), ("sensex rally", 10),
                ("sensex crash", 5), ("nifty", 50),
            ],
            "bank nifty": [
                ("bank nifty 50", 100), ("bank nifty today", 40),
                ("bank nifty sideways", 20), ("bank nifty breakout", 10),
                ("bank nifty crash", 5), ("nifty share price", 50),
            ],
            "gold price": [
                ("gold price today", 100), ("gold stable", 40),
                ("gold price rise", 20), ("gold price fall", 10),
                ("silver price today", 50),
            ],
            "silver price": [
                ("silver price today", 100), ("silver stable", 40),
                ("silver price rise", 20), ("silver price fall", 10),
                ("gold price today", 50),
            ],
        }

        class FakeTrendReq:
            calls = 0

            def __init__(self, **kwargs):
                pass

            def build_payload(self, terms, **kwargs):
                FakeTrendReq.calls += 1

            def related_queries(self):
                return {
                    seed: {
                        "top": pd.DataFrame(
                            [{"query": term, "value": value} for term, value in values]
                        ),
                        "rising": pd.DataFrame(columns=["query", "value"]),
                    }
                    for seed, values in rows.items()
                }

            def interest_over_time(self):
                return pd.DataFrame(
                    {"interest": [100]},
                    index=pd.DatetimeIndex([pd.Timestamp.now(tz="UTC")]),
                )

        request_module = types.ModuleType("pytrends.request")
        request_module.TrendReq = FakeTrendReq
        package_module = types.ModuleType("pytrends")
        package_module.request = request_module
        before = FakeTrendReq.calls
        with patch.dict(sys.modules, {
            "pytrends": package_module,
            "pytrends.request": request_module,
        }):
            result = fetch_asset_trends_shadow()

        self.assertEqual(FakeTrendReq.calls - before, 1)
        self.assertEqual(set(result), {"NIFTY", "SENSEX", "BANKNIFTY", "GOLD", "SILVER"})
        for asset, snapshot in result.items():
            with self.subTest(asset=asset):
                self.assertTrue(snapshot["valid"], snapshot.get("reason"))
                self.assertEqual(snapshot["out_of_scope_queries"], 1)
                self.assertEqual(snapshot["in_scope_queries"], snapshot["classified_queries"])
                self.assertEqual(snapshot["classification_coverage_pct"], 100.0)
                self.assertEqual(snapshot["raw_queries"],
                                 snapshot["in_scope_queries"] + snapshot["out_of_scope_queries"])


if __name__ == "__main__":
    unittest.main()
