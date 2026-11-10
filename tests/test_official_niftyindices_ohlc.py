import datetime as dt
import unittest
from unittest.mock import Mock

import verify_official_niftyindices_ohlc as official


class FakeResponse:
    def __init__(self, payload=None, text="", headers=None):
        self.payload = payload
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def source_row(day, open_value=100.0, high=105.0, low=95.0, close=102.0):
    return {
        "EOD_INDEX_NAME": "NIFTY 50",
        "EOD_TIMESTAMP": day,
        "EOD_OPEN_INDEX_VAL": open_value,
        "EOD_HIGH_INDEX_VAL": high,
        "EOD_LOW_INDEX_VAL": low,
        "EOD_CLOSE_INDEX_VAL": close,
    }


class OfficialNSEIndexOHLCTests(unittest.TestCase):
    def test_date_chunks_are_contiguous_and_within_365_days(self):
        start = dt.date(2025, 10, 31)
        end = dt.date(2026, 11, 9)
        chunks = list(official.date_chunks(start, end))
        self.assertEqual(chunks[0], (dt.date(2025, 10, 31), dt.date(2026, 10, 30)))
        self.assertEqual(chunks[1], (dt.date(2026, 10, 31), dt.date(2026, 11, 9)))
        self.assertTrue(all((right - left).days + 1 <= 365 for left, right in chunks))
        self.assertEqual(chunks[0][1] + dt.timedelta(days=1), chunks[1][0])

    def test_date_chunks_reject_invalid_ranges(self):
        with self.assertRaises(ValueError):
            list(official.date_chunks(dt.date(2026, 2, 2), dt.date(2026, 2, 1)))
        with self.assertRaises(ValueError):
            list(official.date_chunks(dt.date(2026, 1, 1), dt.date(2026, 1, 2), 0))

    def test_parse_api_response(self):
        rows = [source_row("09-NOV-2026")]
        self.assertEqual(official.parse_api_response({"data": rows}), rows)
        self.assertEqual(official.parse_api_response({"data": []}), [])
        with self.assertRaisesRegex(ValueError, "missing the data field"):
            official.parse_api_response({})
        with self.assertRaisesRegex(ValueError, "not a list"):
            official.parse_api_response({"data": {"rows": []}})

    def test_normalize_ohlc_rows(self):
        rows = [
            source_row("09-NOV-2026"),
            source_row("06-NOV-2026", 99.0, 103.0, 98.0, 101.0),
        ]
        prices = official.normalize_ohlc_rows(
            rows, "NIFTY 50", dt.date(2026, 11, 1), dt.date(2026, 11, 9)
        )
        self.assertEqual(list(prices), ["2026-11-06", "2026-11-09"])
        self.assertEqual(prices["2026-11-09"]["close"], 102.0)

    def test_normalize_rejects_duplicate_dates(self):
        rows = [source_row("09-NOV-2026"), source_row("09-NOV-2026")]
        with self.assertRaisesRegex(ValueError, "duplicate official NSE OHLC date"):
            official.normalize_ohlc_rows(
                rows, "NIFTY 50", dt.date(2026, 11, 1), dt.date(2026, 11, 9)
            )

    def test_normalize_rejects_wrong_index_and_inconsistent_ohlc(self):
        wrong = source_row("09-NOV-2026")
        wrong["EOD_INDEX_NAME"] = "NIFTY BANK"
        with self.assertRaisesRegex(ValueError, "index name mismatch"):
            official.normalize_ohlc_rows(
                [wrong], "NIFTY 50", dt.date(2026, 11, 1), dt.date(2026, 11, 9)
            )
        invalid = source_row("09-NOV-2026", 110.0, 105.0, 95.0, 102.0)
        with self.assertRaisesRegex(ValueError, "inconsistent OHLC"):
            official.normalize_ohlc_rows(
                [invalid], "NIFTY 50", dt.date(2026, 11, 1), dt.date(2026, 11, 9)
            )

    def test_alignment_reports_missing_and_unmatched_dates(self):
        prices = {
            "2026-11-05": {"open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0},
            "2026-11-06": {"open": 101.0, "high": 106.0, "low": 99.0, "close": 104.0},
        }
        report = official.build_alignment_report(
            ["2026-11-05", "2026-11-07"],
            prices,
            dt.date(2026, 11, 5),
            dt.date(2026, 11, 7),
        )
        self.assertEqual(report["matched_sessions"], 1)
        self.assertEqual(report["oi_dates_without_official_price"], 1)
        self.assertEqual(report["official_sessions_missing_from_oi"], 1)
        self.assertFalse(report["exact_session_calendar_match"])
        self.assertEqual(report["official_sessions_missing_from_oi_sample"], ["2026-11-06"])

    def test_fetch_seeds_session_and_splits_long_date_range(self):
        session = Mock()
        session.get.side_effect = [
            FakeResponse(),
            FakeResponse({"data": [source_row("01-JAN-2025")]}),
            FakeResponse({"data": [source_row("01-JAN-2026")]}),
        ]
        sleeps = []
        prices, calls = official.fetch_official_ohlc(
            "NIFTY 50",
            dt.date(2025, 1, 1),
            dt.date(2026, 1, 1),
            session=session,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(calls, 3)
        self.assertEqual(len(session.get.call_args_list), 3)
        self.assertEqual(len(prices), 2)
        self.assertEqual(sleeps, [0.75, 0.75])
        self.assertEqual(
            session.get.call_args_list[1].kwargs["params"]["indexType"], "NIFTY 50"
        )

    def test_alignment_rejects_duplicate_oi_dates(self):
        with self.assertRaisesRegex(ValueError, "duplicate OI dates"):
            official.build_alignment_report(
                ["2026-11-05", "2026-11-05"],
                {"2026-11-05": {"open": 100, "high": 105, "low": 95, "close": 102}},
                dt.date(2026, 11, 5),
                dt.date(2026, 11, 5),
            )


if __name__ == "__main__":
    unittest.main()
