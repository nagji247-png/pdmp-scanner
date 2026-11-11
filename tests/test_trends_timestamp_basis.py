import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

import fetch_and_score


class TrendsTimestampBasisTests(unittest.TestCase):
    def test_hourly_trends_marks_validated_timestamp_as_source_observation(self):
        observed_at = pd.Timestamp("2026-11-11T04:00:00Z")

        class FakeTrendReq:
            def __init__(self, **kwargs):
                pass

            def build_payload(self, terms, **kwargs):
                pass

            def interest_over_time(self):
                return pd.DataFrame(
                    {
                        "nifty": [100],
                        "sensex": [100],
                    },
                    index=pd.DatetimeIndex([observed_at]),
                )

        request_module = types.ModuleType("pytrends.request")
        request_module.TrendReq = FakeTrendReq
        package_module = types.ModuleType("pytrends")
        package_module.request = request_module

        def fake_trends_request(_py, terms, timeframe="now 7-d"):
            return pd.DataFrame(
                {fetch_and_score.ANCHOR: [100], **{term: [25] for term in terms}},
                index=pd.DatetimeIndex([observed_at]),
            )

        with patch.dict(sys.modules, {
            "pytrends": package_module,
            "pytrends.request": request_module,
        }), patch(
            "fetch_and_score._trends_observation_time",
            return_value=observed_at.to_pydatetime(),
        ), patch(
            "fetch_and_score._trends_request",
            side_effect=fake_trends_request,
        ), patch(
            "fetch_and_score._ratio",
            return_value=(1.0, 1.0),
        ):
            result = fetch_and_score._trends_once(
                timeframe="now 1-d",
                recent_points=24,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["timestamp_basis"], "source_observation")
        self.assertEqual(result["source_data_time"], observed_at.isoformat())
        self.assertIsNone(result["retrieved_at"])


if __name__ == "__main__":
    unittest.main()
