import json
import tempfile
import unittest
from pathlib import Path

from run_mcx_oi_forward_evaluation import build_report, write_json_atomic


def session(day, gold_close, gold_oi, silver_close, silver_oi):
    return {"date": day, "contract_rows": [
        {"Symbol": "GOLD", "ExpiryDate": "04DEC2026", "Close": gold_close, "OpenInterest": gold_oi},
        {"Symbol": "SILVER", "ExpiryDate": "04DEC2026", "Close": silver_close, "OpenInterest": silver_oi},
    ]}


class MCXForwardReportTests(unittest.TestCase):
    def test_report_stays_research_only_until_both_symbols_meet_threshold(self):
        archive = {"records": [
            session("2026-11-02", 100, 10, 200, 20),
            session("2026-11-03", 102, 12, 202, 22),
            session("2026-11-04", 103, 13, 203, 23),
            session("2026-11-05", 104, 14, 204, 24),
            session("2026-11-06", 105, 15, 205, 25),
        ]}
        report = build_report(archive)
        self.assertEqual(report["archive_sessions"], 5)
        self.assertEqual(report["evaluation"]["status"], "insufficient_sample")
        self.assertEqual(report["evaluation"]["signal_sessions_by_symbol"], {"GOLD": 3, "SILVER": 3})
        self.assertFalse(report["included_in_asset_final"])
        self.assertFalse(report["trading_signal"])
        self.assertFalse(report["evaluation"]["included_in_asset_final"])

    def test_atomic_report_write_is_valid_json(self):
        report = build_report({"records": []})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            write_json_atomic(path, report)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["archive_sessions"], 0)
            self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
