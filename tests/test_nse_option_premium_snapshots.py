import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nse_option_premium_snapshots import parse_option_chain, update_archive


class OptionPremiumSnapshotTests(unittest.TestCase):
    def payload(self):
        return {
            "records": {
                "timestamp": "22-Nov-2026 10:10:00",
                "underlyingValue": 26100.5,
                "data": [
                    {
                        "expiryDate": "26-Nov-2026",
                        "strikePrice": 26100,
                        "PE": {"lastPrice": 112.5, "totalTradedVolume": 1200, "openInterest": 50000},
                        "CE": {"lastPrice": 98.25, "totalTradedVolume": 900, "openInterest": 45000},
                    },
                    {
                        "expiryDate": "03-Dec-2026",
                        "strikePrice": 26100,
                        "PE": {"lastPrice": 150, "totalTradedVolume": 100, "openInterest": 2000},
                    },
                    {
                        "expiryDate": "26-Nov-2026",
                        "strikePrice": 26200,
                        "PE": {"lastPrice": 0, "totalTradedVolume": 0, "openInterest": 0},
                    },
                ],
            }
        }

    def test_keeps_only_nearest_expiry_valid_ltp_points(self):
        result = parse_option_chain(
            self.payload(), "26-Nov-2026",
            fetched_at=dt.datetime(2026, 11, 22, 5, 0, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(result["expiry"], "26-Nov-2026")
        self.assertEqual([(x["side"], x["ltp"]) for x in result["points"]],
                         [("PE", 112.5), ("CE", 98.25)])
        self.assertEqual(result["underlying"], 26100.5)

    def test_rejects_missing_timestamp_or_empty_points(self):
        payload = self.payload()
        payload["records"]["timestamp"] = ""
        with self.assertRaises(ValueError):
            parse_option_chain(payload, "26-Nov-2026")
        payload = self.payload()
        payload["records"]["data"] = []
        with self.assertRaises(ValueError):
            parse_option_chain(payload, "26-Nov-2026")

    def test_archive_deduplicates_source_timestamp(self):
        snapshot = parse_option_chain(
            self.payload(), "26-Nov-2026",
            fetched_at=dt.datetime(2026, 11, 22, 5, 0, tzinfo=dt.timezone.utc),
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshots.json"
            self.assertTrue(update_archive(path, snapshot))
            self.assertFalse(update_archive(path, snapshot))


if __name__ == "__main__":
    unittest.main()
