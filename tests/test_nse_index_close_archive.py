import csv
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import nse_index_close_archive as archive


class NSEIndexCloseArchiveTests(unittest.TestCase):
    def csv_payload(self, rows=None):
        rows = rows or [
            ["Nifty 50", "16-11-2026", "25000", "25200", "24900", "25100", "100", "0.40", "1000", "100", "20", "4", "1"],
            ["Nifty Auto", "16-11-2026", "20000", "20200", "19900", "20100", "100", "0.50", "1000", "100", "30", "5", "0.8"],
            ["Nifty IT", "16-11-2026", "40000", "40200", "39900", "40100", "100", "0.25", "1000", "100", "25", "6", "0.5"],
        ]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Index Name", "Index Date", "Open", "High", "Low", "Closing", "Points Change", "Change(%)", "Volume", "Turnover", "P/E", "P/B", "Div Yield"])
        writer.writerows(rows)
        return output.getvalue()

    def test_parser_extracts_multiple_index_closes_for_exact_date(self):
        rows = archive.parse_index_snapshot_csv(
            self.csv_payload(), "2026-11-16", min_rows=3
        )
        self.assertEqual(rows["Nifty 50"], 25100.0)
        self.assertEqual(rows["Nifty Auto"], 20100.0)
        self.assertEqual(len(rows), 3)

    def test_parser_rejects_wrong_date_duplicate_name_and_bad_close(self):
        with self.assertRaisesRegex(ValueError, "date mismatch"):
            archive.parse_index_snapshot_csv(
                self.csv_payload([["Nifty 50", "15-11-2026", "1", "2", "1", "2", "0", "0", "1", "1", "1", "1", "1"]]),
                "2026-11-16", min_rows=1
            )
        with self.assertRaisesRegex(ValueError, "duplicate/invalid"):
            archive.parse_index_snapshot_csv(
                self.csv_payload([
                    ["Nifty 50", "16-11-2026", "1", "2", "1", "2", "0", "0", "1", "1", "1", "1", "1"],
                    ["NIFTY 50", "16-11-2026", "1", "2", "1", "2", "0", "0", "1", "1", "1", "1", "1"],
                ]),
                "2026-11-16", min_rows=1
            )
        with self.assertRaisesRegex(ValueError, "invalid close"):
            archive.parse_index_snapshot_csv(
                self.csv_payload([["Nifty 50", "16-11-2026", "1", "2", "1", "—", "0", "0", "1", "1", "1", "1", "1"]]),
                "2026-11-16", min_rows=1
            )

    def test_parser_accepts_daily_snapshot_close_and_date_header_aliases(self):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Index Name", "Date", "Open", "High", "Low", "Close"])
        writer.writerow(["Nifty 50", "16-11-2026", "25000", "25200", "24900", "25100"])
        writer.writerow(["Nifty Auto", "16-11-2026", "20000", "20200", "19900", "20100"])
        writer.writerow(["Nifty IT", "16-11-2026", "40000", "40200", "39900", "40100"])
        rows = archive.parse_index_snapshot_csv(output.getvalue(), "2026-11-16", min_rows=3)
        self.assertEqual(rows["Nifty 50"], 25100.0)

    def test_parser_rejects_html_wrong_headers_and_small_files(self):
        with self.assertRaisesRegex(ValueError, "HTML/JSON"):
            archive.parse_index_snapshot_csv("<html>blocked</html>", "2026-11-16")
        with self.assertRaisesRegex(ValueError, "missing columns"):
            archive.parse_index_snapshot_csv("Symbol,Close\nABC,100\n", "2026-11-16")
        with self.assertRaisesRegex(ValueError, "implausibly small"):
            archive.parse_index_snapshot_csv(
                self.csv_payload([["Nifty 50", "16-11-2026", "1", "2", "1", "2", "0", "0", "1", "1", "1", "1", "1"]]),
                "2026-11-16"
            )

    def test_archive_is_idempotent_and_rejects_changed_source_file(self):
        data = self.csv_payload()
        indices = archive.parse_index_snapshot_csv(data, "2026-11-16", min_rows=3)
        target = {"records": []}
        self.assertTrue(archive.append_session(
            target, "2026-11-16", "https://nsearchives.nseindia.com/content/indices/ind_close_all_16112026.csv",
            data.encode(), indices, "2026-11-16T14:30:00Z"
        ))
        self.assertFalse(archive.append_session(
            target, "2026-11-16", "https://nsearchives.nseindia.com/content/indices/ind_close_all_16112026.csv",
            data.encode(), indices, "2026-11-16T14:31:00Z"
        ))
        self.assertEqual(len(target["records"]), 1)
        self.assertFalse(target["records"][0]["score_eligible"])
        with self.assertRaisesRegex(ValueError, "different NSE index snapshot"):
            archive.append_session(
                target, "2026-11-16", "https://nsearchives.nseindia.com/content/indices/ind_close_all_16112026.csv",
                b"different", indices, "2026-11-16T14:32:00Z"
            )

    def test_fetch_uses_one_official_request_without_retry(self):
        session = Mock()
        response = Mock(status_code=200, content=self.csv_payload().encode())
        session.get.return_value = response
        payload, url = archive.fetch_official_index_snapshot(
            dt.date(2026, 11, 16), session=session
        )
        self.assertEqual(payload, response.content)
        self.assertEqual(session.get.call_count, 1)
        self.assertIn("/content/indices/ind_close_all_16112026.csv", url)

    def test_existing_session_and_holidays_skip_without_network(self):
        calendar = {
            "holidays": [{"date": "2026-11-10", "name": "Diwali-Balipratipada"}],
            "special_sessions": {"2026-11-08": {"name": "Diwali Muhurat Trading"}},
        }
        with patch.object(archive, "fetch_official_index_snapshot") as fetch:
            holiday = archive.capture_one({"records": []}, "2026-11-10", calendar=calendar)
            weekend = archive.capture_one({"records": []}, "2026-11-15", calendar=calendar)
            special = archive.capture_one({"records": []}, "2026-11-08", calendar=calendar)
            self.assertEqual(holiday["status"], "skipped_non_session")
            self.assertEqual(weekend["status"], "skipped_non_session")
            self.assertEqual(special["status"], "unavailable")
            fetch.assert_called_once()

        data = {"records": [{"date": "2026-11-16"}]}
        with patch.object(archive, "fetch_official_index_snapshot") as fetch:
            result = archive.capture_one(data, "2026-11-16")
            self.assertEqual(result["status"], "already_captured")
            fetch.assert_not_called()

    def test_current_day_404_still_allows_historical_backfill_but_transient_failure_stops(self):
        self.assertTrue(archive.should_continue_backfill_after_current("skipped_missing_file"))
        self.assertTrue(archive.should_continue_backfill_after_current("skipped_non_session"))
        self.assertFalse(archive.should_continue_backfill_after_current("unavailable"))

    def test_backfill_cursor_moves_back_bounded_calendar_days(self):
        dates = archive.build_backfill_dates(
            dt.date(2026, 11, 15), dt.date(2026, 11, 16), 14
        )
        self.assertEqual(len(dates), 14)
        self.assertEqual(dates[0], dt.date(2026, 11, 15))
        self.assertEqual(dates[-1], dt.date(2026, 11, 2))
        self.assertEqual(
            dates[-1] - dt.timedelta(days=1), dt.date(2026, 11, 1)
        )
        self.assertLessEqual(
            len(archive.build_backfill_dates(
                dt.date(2025, 11, 15), dt.date(2026, 11, 16), 31
            )), 31
        )

    def test_write_archive_uses_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            archive.write_archive(path, {"records": [], "updated_at": "now"})
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text())["updated_at"], "now")
            self.assertFalse(Path(str(path) + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
