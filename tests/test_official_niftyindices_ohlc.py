import datetime as dt
import json
import unittest
from unittest.mock import Mock

import verify_official_niftyindices_ohlc as official


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def source_row(day, open_value="100.00", high="105.00", low="95.00", close="102.00"):
    return {
        "INDEX_NAME": "NIFTY 50",
        "HistoricalDate": day,
        "OPEN": open_value,
        "HIGH": high,
        "LOW": low,
        "CLOSE": close,
    }


class OfficialNiftyIndicesOHLCTests(unittest.TestCase):
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

    def test_parse_api_response_double_encoded_rows(self):
        rows = [source_row("09 Nov 2026")]
        parsed = official.parse_api_response({"d": json.dumps(rows)})
        self.assertEqual(parsed, rows)

    def test_parse_api_response_empty_and_invalid(self):
        self.assertEqual(official.parse_api_response({"d": "false"}), [])
        self.assertEqual(official.parse_api_response({"d": "[]"}), [])
        with self.assertRaisesRegex(ValueError, "missing the d field"):
            official.parse_api_response({})
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            official.parse_api_response({"d": "not-json"})

    def test_normalize_ohlc_rows(self):
        rows = [
            source_row("09 Nov 2026"),
            source_row("06 Nov 2026", "99.00", "103.00", "98.00", "101.00"),
        ]
        prices = official.normalize_ohlc_rows(
            rows, "NIFTY 50", dt.date(2026, 11, 1), dt.date(2026, 11, 9)
        )
        self.assertEqual(list(prices), ["2026-11-06", "2026-11-09"])
        self.assertEqual(prices["2026-11-09"]["close"], 102.0)

    def test_normalize_rejects_duplicate_dates(self):
        rows = [source_row("09 Nov 2026"), source_row("09 Nov 2026")]
        with self.assertRaisesRegex(ValueError, "duplicate official OHLC date"):
            official.normalize_ohlc_rows(
                rows, "NIFTY 50", dt.date(2026, 11, 1), dt.date(2026, 11, 9)
            )

    def test_normalize_rejects_wrong_index_and_inconsistent_ohlc(self):
        wrong = source_row("09 Nov 2026")
        wrong["INDEX_NAME"] = "NIFTY BANK"
        with self.assertRaisesRegex(ValueError, "index name mismatch"):
            official.normalize_ohlc_rows(
                [wrong], "NIFTY 50", dt.date(2026, 11, 1), dt.date(2026, 11, 9)
            )
        invalid = source_row("09 Nov 2026", "110", "105", "95", "102")
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

    def test_fetch_seeds_page_and_splits_long_date_range(self):
        session = Mock()
        session.get.return_value = FakeResponse()
        session.post.side_effect = [
            FakeResponse({"d": json.dumps([source_row("01 Jan 2025")])}),
            FakeResponse({"d": json.dumps([source_row("01 Jan 2026")])}),
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
        self.assertEqual(len(session.post.call_args_list), 2)
        self.assertEqual(len(prices), 2)
        self.assertEqual(sleeps, [0.75])


if __name__ == "__main__":
    unittest.main()
