import csv
import io
import unittest
from unittest.mock import Mock

from bse_sensex_close_archive import (
    URL, fetch_sensex_history, parse_sensex_history_csv,
)


def csv_payload(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["Date", "Open", "High", "Low", "Close"])
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


class BseSensexCloseArchiveTests(unittest.TestCase):
    def test_parses_official_dated_closes(self):
        parsed = parse_sensex_history_csv(csv_payload([
            {"Date": "12/11/2026", "Open": "84000", "High": "84500", "Low": "83800", "Close": "84200.5"},
            {"Date": "13/11/2026", "Open": "84200", "High": "84600", "Low": "84100", "Close": "84400"},
        ]), "2026-11-12", "2026-11-13")
        self.assertEqual(parsed, {
            "2026-11-12": 84200.5,
            "2026-11-13": 84400.0,
        })

    def test_rejects_missing_date_or_close_columns(self):
        with self.assertRaisesRegex(ValueError, "missing Date/Close"):
            parse_sensex_history_csv(b"Date,Open\n12/11/2026,100\n", "2026-11-12", "2026-11-13")

    def test_rejects_wrong_date_range(self):
        with self.assertRaisesRegex(ValueError, "outside requested range"):
            parse_sensex_history_csv(csv_payload([
                {"Date": "11/11/2026", "Open": "1", "High": "2", "Low": "1", "Close": "1.5"},
            ]), "2026-11-12", "2026-11-13")

    def test_rejects_invalid_close(self):
        with self.assertRaisesRegex(ValueError, "invalid BSE SENSEX close"):
            parse_sensex_history_csv(csv_payload([
                {"Date": "12/11/2026", "Open": "1", "High": "2", "Low": "1", "Close": "0"},
            ]), "2026-11-12", "2026-11-13")

    def test_rejects_duplicate_dates(self):
        row = {"Date": "12/11/2026", "Open": "1", "High": "2", "Low": "1", "Close": "1.5"}
        with self.assertRaisesRegex(ValueError, "duplicate BSE SENSEX"):
            parse_sensex_history_csv(csv_payload([row, row]), "2026-11-12", "2026-11-13")

    def test_fetch_uses_one_official_bse_range_request(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, content=b"csv", url="https://api.bseindia.com/example")
        body, url = fetch_sensex_history("2026-11-12", "2026-11-17", session=session)
        self.assertEqual(body, b"csv")
        self.assertEqual(url, "https://api.bseindia.com/example")
        args, kwargs = session.get.call_args
        self.assertEqual(args[0], URL)
        self.assertEqual(kwargs["params"], {
            "strIndex": "SENSEX",
            "dtFromDate": "12/11/2026",
            "dtToDate": "17/11/2026",
            "period": "D",
        })
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.get.call_args_list[0].args[0], "https://www.bseindia.com/indices/IndexArchiveData.html")
        self.assertEqual(session.get.call_args_list[1].args[0], URL)

    def test_http_error_does_not_retry(self):
        session = Mock()
        session.get.return_value = Mock(status_code=403, content=b"")
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            fetch_sensex_history("2026-11-12", "2026-11-17", session=session)
        self.assertEqual(session.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
