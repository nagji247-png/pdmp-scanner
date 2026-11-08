import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import nse_index_option_oi_archive as nse_archive

from component_scoring import aggregate_nse_udiff_index_option_oi
from nse_index_option_oi_archive import (
    aggregate_udiff_rows,
    append_archive,
    decode_udiff_zip,
    write_archive_atomic,
)


class NSEIndexOptionOIArchiveTests(unittest.TestCase):
    def rows(self):
        base = {
            "Sgmt": "FO", "Src": "NSE", "FinInstrmTp": "IDO",
            "BizDt": "2026-11-06", "XpryDt": "2026-11-26",
            "StrkPric": "25000.00", "OpnIntrst": "1000",
            "ChngInOpnIntrst": "125",
        }
        return [
            {**base, "TckrSymb": "NIFTY", "OptnTp": "CE"},
            {**base, "TckrSymb": "NIFTY", "OptnTp": "PE",
             "StrkPric": "25050", "OpnIntrst": "2000", "ChngInOpnIntrst": "-50"},
            {**base, "TckrSymb": "BANKNIFTY", "OptnTp": "CE"},
            {**base, "TckrSymb": "BANKNIFTY", "OptnTp": "PE",
             "StrkPric": "25100", "OpnIntrst": "3000", "ChngInOpnIntrst": "75"},
        ]

    def test_exact_symbol_date_expiry_and_both_sides_are_aggregated(self):
        result = aggregate_udiff_rows(self.rows(), "2026-11-06")
        self.assertEqual(result["NIFTY"]["contract_rows"], 2)
        self.assertEqual(result["NIFTY"]["by_expiry"]["2026-11-26"]["CE"]["open_interest"], 1000)
        self.assertEqual(result["NIFTY"]["by_expiry"]["2026-11-26"]["PE"]["change_in_oi"], -50)
        self.assertEqual(result["BANKNIFTY"]["by_expiry"]["2026-11-26"]["PE"]["open_interest"], 3000)
        self.assertFalse(result["NIFTY"]["coverage_validated"])
        self.assertFalse(result["NIFTY"]["included_in_asset_final"])

    def test_non_index_options_and_other_symbols_are_ignored(self):
        rows = self.rows() + [
            {**self.rows()[0], "FinInstrmTp": "STO", "TckrSymb": "NIFTY"},
            {**self.rows()[0], "TckrSymb": "FINNIFTY"},
        ]
        result = aggregate_udiff_rows(rows, "2026-11-06")
        self.assertEqual(result["NIFTY"]["contract_rows"], 2)
        self.assertEqual(result["BANKNIFTY"]["contract_rows"], 2)

    def test_wrong_trade_date_fails_closed(self):
        rows = self.rows()
        rows[0] = {**rows[0], "BizDt": "2026-11-05"}
        with self.assertRaisesRegex(ValueError, "trade date mismatch"):
            aggregate_udiff_rows(rows, "2026-11-06")

    def test_missing_one_option_side_fails_closed(self):
        rows = [row for row in self.rows() if not (
            row["TckrSymb"] == "NIFTY" and row["OptnTp"] == "PE"
        )]
        with self.assertRaisesRegex(ValueError, "missing CE or PE"):
            aggregate_udiff_rows(rows, "2026-11-06")

    def test_duplicate_contract_and_malformed_oi_fail_closed(self):
        rows = self.rows()
        with self.assertRaisesRegex(ValueError, "duplicate option contract"):
            aggregate_udiff_rows(rows + [rows[0]], "2026-11-06")
        malformed = self.rows()
        malformed[0] = {**malformed[0], "OpnIntrst": ""}
        with self.assertRaisesRegex(ValueError, "missing OpnIntrst"):
            aggregate_udiff_rows(malformed, "2026-11-06")

    def test_invalid_expired_contract_or_wrong_segment_fail_closed(self):
        expired = self.rows()
        expired[0] = {**expired[0], "XpryDt": "2026-11-05"}
        with self.assertRaisesRegex(ValueError, "expired contract"):
            aggregate_udiff_rows(expired, "2026-11-06")
        wrong_segment = self.rows()
        wrong_segment[0] = {**wrong_segment[0], "Sgmt": "CM"}
        with self.assertRaisesRegex(ValueError, "unexpected segment"):
            aggregate_udiff_rows(wrong_segment, "2026-11-06")

    def test_zip_decoder_requires_one_csv_and_expected_columns(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "bhav.csv",
                ",".join(["FinInstrmTp", "TckrSymb", "BizDt", "XpryDt", "OptnTp", "StrkPric", "OpnIntrst", "ChngInOpnIntrst"]) + chr(10),
            )
        self.assertEqual(decode_udiff_zip(payload.getvalue()), [])
        with self.assertRaisesRegex(ValueError, "valid ZIP"):
            decode_udiff_zip(b"not a zip")

    def test_archive_append_is_idempotent_and_rejects_changed_file(self):
        archive = {"records": []}
        symbols = aggregate_udiff_rows(self.rows(), "2026-11-06")
        payload = b"official test zip bytes"
        self.assertTrue(append_archive(
            archive, "2026-11-06", "https://archives.nseindia.com/test.zip",
            payload, symbols, "2026-11-06T14:00:00Z"
        ))
        self.assertFalse(append_archive(
            archive, "2026-11-06", "https://archives.nseindia.com/test.zip",
            payload, symbols, "2026-11-06T14:01:00Z"
        ))
        self.assertEqual(len(archive["records"]), 1)
        self.assertTrue(archive["research_only"])
        self.assertFalse(archive["included_in_asset_final"])
        with self.assertRaisesRegex(ValueError, "different file"):
            append_archive(
                archive, "2026-11-06", "https://archives.nseindia.com/test.zip",
                b"changed bytes", symbols, "2026-11-06T14:02:00Z"
            )


    def test_atomic_archive_write_persists_complete_json_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nse_index_option_oi.json"
            expected = {"schema_version": 1, "records": [{"date": "2026-11-06"}]}
            write_archive_atomic(path, expected)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)
            self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())

    def test_existing_date_skips_download_entirely(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nse_index_option_oi.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "records": [{"date": "2026-11-06"}],
            }), encoding="utf-8")
            with patch("sys.argv", [
                "nse_index_option_oi_archive.py",
                "--date", "2026-11-06",
                "--archive", str(path),
            ]):
                with patch.object(nse_archive, "fetch_official_bhavcopy") as fetch:
                    self.assertEqual(nse_archive.main(), 0)
                    fetch.assert_not_called()

    def test_bounded_backfill_caps_dates_skips_weekends_and_uses_mocked_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nse_index_option_oi.json"
            with patch("sys.argv", [
                "nse_index_option_oi_archive.py",
                "--from-date", "2026-11-02", "--to-date", "2026-11-08",
                "--max-sessions", "3", "--delay-seconds", "2", "--archive", str(path),
            ]):
                with patch.object(nse_archive, "capture_one") as capture:
                    capture.side_effect = [
                        {"date": "2026-11-02", "status": "captured"},
                        {"date": "2026-11-03", "status": "captured"},
                        {"date": "2026-11-04", "status": "captured"},
                    ]
                    with patch.object(nse_archive.time, "sleep") as sleep:
                        self.assertEqual(nse_archive.main(), 0)
                    self.assertEqual([call.args[1].isoformat() for call in capture.call_args_list],
                                     ["2026-11-02", "2026-11-03", "2026-11-04"])
                    self.assertEqual(sleep.call_count, 2)

    def test_backfill_rejects_unbounded_or_fast_request_settings(self):
        with patch("sys.argv", ["nse_index_option_oi_archive.py",
                                "--from-date", "2026-11-02", "--to-date", "2026-11-06",
                                "--max-sessions", "6"]):
            with self.assertRaises(SystemExit):
                nse_archive.main()
        with patch("sys.argv", ["nse_index_option_oi_archive.py",
                                "--from-date", "2026-11-02", "--to-date", "2026-11-06",
                                "--delay-seconds", "0"]):
            with self.assertRaises(SystemExit):
                nse_archive.main()


class ExistingNSEIndexOIComponentAggregationTests(unittest.TestCase):
    def test_exact_symbol_and_date_aggregate_both_option_sides(self):
        common = {
            "FinInstrmTp": "IDO", "TckrSymb": "NIFTY",
            "BizDt": "2026-11-06", "XpryDt": "2026-11-26",
            "OpnIntrst": "1000", "ChngInOpnIntrst": "125",
        }
        rows = [
            {**common, "OptnTp": "CE"},
            {**common, "OptnTp": "PE", "OpnIntrst": "2000", "ChngInOpnIntrst": "-50"},
        ]
        result = aggregate_nse_udiff_index_option_oi(rows, "NIFTY", "2026-11-06")
        self.assertTrue(result["available"])
        self.assertFalse(result["included_in_asset_final"])
        self.assertFalse(result["coverage_validated"])
        self.assertEqual(result["call"]["open_interest"], 1000)
        self.assertEqual(result["put"]["change_in_oi"], -50)

    def test_wrong_date_missing_side_and_malformed_rows_fail_closed(self):
        common = {
            "FinInstrmTp": "IDO", "TckrSymb": "NIFTY",
            "BizDt": "2026-11-06", "XpryDt": "2026-11-26",
            "OpnIntrst": "1000", "ChngInOpnIntrst": "125",
        }
        rows = [{**common, "OptnTp": "CE"}, {**common, "OptnTp": "PE"}]
        wrong_date = [{**rows[0], "BizDt": "2026-11-05"}, rows[1]]
        self.assertFalse(aggregate_nse_udiff_index_option_oi(
            wrong_date, "NIFTY", "2026-11-06")["available"])
        self.assertFalse(aggregate_nse_udiff_index_option_oi(
            rows[:1], "NIFTY", "2026-11-06")["available"])
        malformed = [rows[0], {**rows[1], "OpnIntrst": "", "XpryDt": ""}]
        self.assertFalse(aggregate_nse_udiff_index_option_oi(
            malformed, "NIFTY", "2026-11-06")["available"])


if __name__ == "__main__":
    unittest.main()
