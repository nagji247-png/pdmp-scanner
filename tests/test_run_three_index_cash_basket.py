import tempfile
import unittest
from pathlib import Path

from run_three_index_cash_basket import append_diagnostic, load_json


class ThreeIndexDiagnosticArchiveTests(unittest.TestCase):
    def test_appends_dated_diagnostic_without_score_eligibility(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostics.json"
            result = {
                "date": "2026-11-09",
                "status": "withheld_incomplete",
                "indices": {},
                "all_three_complete": False,
                "score_eligible": False,
                "research_only": True,
            }
            self.assertTrue(append_diagnostic(path, result))
            saved = load_json(path, {})
            self.assertEqual(len(saved["records"]), 1)
            self.assertFalse(saved["score_eligible"])
            self.assertFalse(saved["records"][0]["all_three_complete"])

    def test_idempotent_same_date_record_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostics.json"
            result = {"date": "2026-11-09", "status": "withheld_incomplete"}
            self.assertTrue(append_diagnostic(path, result))
            self.assertFalse(append_diagnostic(path, result))
            self.assertEqual(len(load_json(path, {})["records"]), 1)

    def test_changed_same_date_record_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostics.json"
            append_diagnostic(path, {"date": "2026-11-09", "status": "withheld_incomplete"})
            with self.assertRaisesRegex(ValueError, "refusing overwrite"):
                append_diagnostic(path, {"date": "2026-11-09", "status": "complete_diagnostic"})


if __name__ == "__main__":
    unittest.main()
