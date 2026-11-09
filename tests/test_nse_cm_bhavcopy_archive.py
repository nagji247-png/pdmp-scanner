import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import nse_cm_bhavcopy_archive as cm


class NSECashBhavcopyArchiveTests(unittest.TestCase):
    def row(self, **overrides):
        value = {
            "Sgmt": "CM", "Src": "NSE", "FinInstrmTp": "STK",
            "TckrSymb": "RELIANCE", "SctySrs": "EQ", "ISIN": "INE002A01018",
            "TradDt": "2026-11-06", "BizDt": "2026-11-06", "OpnPric": "1400", "HghPric": "1420",
            "LwPric": "1390", "ClsPric": "1410", "PrvsClsgPric": "1405",
            "TtlTradgVol": "100000",
        }
        value.update(overrides)
        return value

    def test_normalizes_eq_rows_and_excludes_non_eq_rows(self):
        rows = [
            self.row(),
            self.row(TckrSymb="HDFCBANK", ISIN="INE040A01034"),
            self.row(TckrSymb="NIFTY", SctySrs="INDEX", ISIN=""),
            self.row(TckrSymb="ABC", SctySrs="BE", ISIN="INE000A01000"),
        ]
        result = cm.normalize_equity_rows(rows, "2026-11-06", min_rows=1)
        self.assertEqual([x["symbol"] for x in result], ["HDFCBANK", "RELIANCE"])
        self.assertEqual(result[1]["previous_close"], 1405)
        self.assertFalse(any("included_in_asset_final" in x for x in result))

    def test_wrong_date_duplicate_missing_identity_and_bad_ohlc_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "date mismatch"):
            cm.normalize_equity_rows([self.row(TradDt="2026-11-05")], "2026-11-06", min_rows=1)
        with self.assertRaisesRegex(ValueError, "duplicate EQ"):
            cm.normalize_equity_rows([self.row(), self.row()], "2026-11-06", min_rows=1)
        with self.assertRaisesRegex(ValueError, "symbol or ISIN"):
            cm.normalize_equity_rows([self.row(ISIN="")], "2026-11-06", min_rows=1)
        with self.assertRaisesRegex(ValueError, "inconsistent OHLC"):
            cm.normalize_equity_rows([self.row(HghPric="1395")], "2026-11-06", min_rows=1)

    def test_zip_decoder_requires_exactly_one_csv_and_all_required_columns(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("cm.csv", ",".join(sorted(cm.REQUIRED_COLUMNS)) + "\n")
        self.assertEqual(cm.decode_cm_udiff_zip(buffer.getvalue()), [])
        with self.assertRaisesRegex(ValueError, "valid ZIP"):
            cm.decode_cm_udiff_zip(b"not zip")
        bad = io.BytesIO()
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("cm.csv", "TckrSymb,ClsPric\n")
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            cm.decode_cm_udiff_zip(bad.getvalue())

    def test_archive_is_idempotent_and_rejects_changed_source_file(self):
        archive = {"records": []}
        rows = cm.normalize_equity_rows([self.row()], "2026-11-06", min_rows=1)
        self.assertTrue(cm.append_session(
            archive, "2026-11-06", "https://archives.nseindia.com/test.zip",
            b"zipbytes", rows, "2026-11-06T14:00:00Z"))
        self.assertFalse(cm.append_session(
            archive, "2026-11-06", "https://archives.nseindia.com/test.zip",
            b"zipbytes", rows, "2026-11-06T14:01:00Z"))
        self.assertEqual(len(archive["records"]), 1)
        self.assertFalse(archive["included_in_asset_final"])
        with self.assertRaisesRegex(ValueError, "different CM file"):
            cm.append_session(
                archive, "2026-11-06", "https://archives.nseindia.com/test.zip",
                b"different", rows, "2026-11-06T14:02:00Z")

    def test_existing_date_skips_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.json"
            path.write_text(json.dumps({"records": [{"date": "2026-11-06"}]}), encoding="utf-8")
            with patch("sys.argv", ["nse_cm_bhavcopy_archive.py", "--date", "2026-11-06",
                                    "--archive", str(path)]):
                with patch.object(cm, "fetch_official_cm_bhavcopy") as fetch:
                    self.assertEqual(cm.main(), 0)
                    fetch.assert_not_called()

    def test_fetch_uses_exactly_one_official_request_without_mirror_retry(self):
        from unittest.mock import Mock
        session = Mock()
        session.get.return_value = Mock(status_code=200, content=b"zip")
        payload, url = cm.fetch_official_cm_bhavcopy("2026-11-06", session=session)
        self.assertEqual(payload, b"zip")
        self.assertEqual(session.get.call_count, 1)
        self.assertIn("nsearchives.nseindia.com/content/cm/", url)


    def test_exchange_holiday_skips_without_network_and_special_session_is_allowed(self):
        calendar = {
            "holidays": [{"date": "2026-11-10", "name": "Diwali-Balipratipada"}],
            "special_sessions": {"2026-11-08": {"name": "Diwali Muhurat Trading"}},
        }
        with patch.object(cm, "fetch_official_cm_bhavcopy") as fetch:
            result = cm.capture_one({"records": []}, "2026-11-10", calendar=calendar)
            self.assertEqual(result["status"], "skipped_non_session")
            self.assertEqual(result["date_attempts"], 0)
            fetch.assert_not_called()
        self.assertTrue(cm.is_exchange_session("2026-11-08", calendar))
        self.assertTrue(cm.is_exchange_session("2026-11-09", calendar))

    def test_small_or_empty_equity_universe_rejected(self):
        with self.assertRaisesRegex(ValueError, "implausibly small"):
            cm.normalize_equity_rows([self.row()], "2026-11-06")


if __name__ == "__main__":
    unittest.main()
