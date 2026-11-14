import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_marketlens_sector_csv import import_marketlens_csv


class MarketLensCsvImportTests(unittest.TestCase):
    def test_exact_fpi_sector_matches_are_imported_and_ambiguous_rows_stay_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 0, "pending_count": 2, "note": ""},
                "stocks": {
                    "ABC": {"industry": None, "sector": None, "status": "pending_official_company_classification"},
                    "XYZ": {"industry": None, "sector": None, "status": "pending_official_company_classification"},
                },
            }
            sector_map = {"stocks": {}, "source": "", "source_url": "", "note": ""}
            master_path, map_path, csv_path = root / "master.json", root / "map.json", root / "marketlens.csv"
            master_path.write_text(json.dumps(master), encoding="utf-8")
            map_path.write_text(json.dumps(sector_map), encoding="utf-8")
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Company", "Sector", "Sub Sector"])
                writer.writeheader()
                writer.writerow({"Company": "ABC LIMITED ABC", "Sector": "IT - Software", "Sub Sector": "Information Technology"})
                writer.writerow({"Company": "XYZ LIMITED XYZ", "Sector": "Energy", "Sub Sector": "Energy"})
            result = import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")
            updated = json.loads(master_path.read_text(encoding="utf-8"))
            mapped = json.loads(map_path.read_text(encoding="utf-8"))
            self.assertEqual(result, {"csv_rows_mapped": 1, "verified": 1, "pending": 1})
            self.assertEqual(updated["stocks"]["ABC"]["sector"], "Information Technology")
            self.assertEqual(updated["stocks"]["XYZ"]["sector"], None)
            self.assertEqual(set(mapped["stocks"]), {"ABC"})

    def test_missing_required_columns_fails_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master_path, map_path, csv_path = root / "master.json", root / "map.json", root / "bad.csv"
            master_path.write_text(json.dumps({"classification": {}, "stocks": {}}), encoding="utf-8")
            map_path.write_text(json.dumps({"stocks": {}}), encoding="utf-8")
            csv_path.write_text("Company,Sub Sector\nABC,Information Technology\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")


if __name__ == "__main__":
    unittest.main()
