import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_marketlens_sector_csv import import_marketlens_csv


class MarketLensCsvImportTests(unittest.TestCase):
    def test_exact_match_and_duplicate_ticker_revoke_stale_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 1, "pending_count": 1, "note": ""},
                "stocks": {
                    "ABC": {"industry": None, "sector": None, "status": "pending_official_company_classification"},
                    "XYZ": {
                        "industry": "Banks",
                        "sector": "Financial Services",
                        "status": "verified_nse_marketlens_sector_match",
                        "verified_on": "2026-11-13",
                        "source": "older import",
                        "source_url": "https://marketlens.nseindia.com/screener",
                    },
                },
            }
            sector_map = {
                "stocks": {"XYZ": {"industry": "Banks", "sector": "Financial Services"}},
                "source": "", "source_url": "", "note": ""
            }
            master_path, map_path, csv_path = root / "master.json", root / "map.json", root / "marketlens.csv"
            master_path.write_text(json.dumps(master), encoding="utf-8")
            map_path.write_text(json.dumps(sector_map), encoding="utf-8")
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Company", "Sector", "Sub Sector"])
                writer.writeheader()
                writer.writerow({"Company": "ABC LIMITED ABC", "Sector": "IT - Software", "Sub Sector": "Information Technology"})
                writer.writerow({"Company": "XYZ LIMITED XYZ", "Sector": "Banks", "Sub Sector": "Financial Services"})
                writer.writerow({"Company": "XYZ LIMITED XYZ", "Sector": "Oil", "Sub Sector": "Energy"})
            result = import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")
            updated = json.loads(master_path.read_text(encoding="utf-8"))
            mapped = json.loads(map_path.read_text(encoding="utf-8"))
            self.assertEqual(result, {
                "csv_rows_mapped": 1,
                "ambiguous_symbols": ["XYZ"],
                "verified": 1,
                "pending": 1,
            })
            self.assertEqual(updated["stocks"]["ABC"]["sector"], "Information Technology")
            self.assertIsNone(updated["stocks"]["XYZ"]["sector"])
            self.assertEqual(updated["stocks"]["XYZ"]["status"], "pending_official_company_classification")
            self.assertEqual(set(mapped["stocks"]), {"ABC"})

    def test_existing_watchlist_mapping_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 1, "pending_count": 0, "note": ""},
                "stocks": {
                    "ABC": {"industry": "Banks", "sector": "Financial Services", "status": "verified_existing_mapping"}
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
            import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")
            updated = json.loads(master_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["stocks"]["ABC"]["sector"], "Financial Services")
            self.assertEqual(updated["stocks"]["ABC"]["status"], "verified_existing_mapping")

    def test_missing_or_unmatched_rows_revoke_old_marketlens_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 2, "pending_count": 1, "note": ""},
                "stocks": {
                    "MISSING": {
                        "industry": "Banks", "sector": "Financial Services",
                        "status": "verified_nse_marketlens_sector_match",
                    },
                    "UNMATCHED": {
                        "industry": "Power", "sector": "Power",
                        "status": "verified_nse_marketlens_sector_match",
                    },
                    "VALID": {
                        "industry": None, "sector": None,
                        "status": "pending_official_company_classification",
                    },
                },
            }
            sector_map = {
                "stocks": {
                    "MISSING": {"industry": "Banks", "sector": "Financial Services"},
                    "UNMATCHED": {"industry": "Power", "sector": "Power"},
                },
                "source": "", "source_url": "", "note": ""
            }
            master_path, map_path, csv_path = root / "master.json", root / "map.json", root / "marketlens.csv"
            master_path.write_text(json.dumps(master), encoding="utf-8")
            map_path.write_text(json.dumps(sector_map), encoding="utf-8")
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Company", "Sector", "Sub Sector"])
                writer.writeheader()
                writer.writerow({"Company": "UNMATCHED LIMITED UNMATCHED", "Sector": "Power", "Sub Sector": "Commodities"})
                writer.writerow({"Company": "VALID LIMITED VALID", "Sector": "IT - Software", "Sub Sector": "Information Technology"})
            result = import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")
            updated = json.loads(master_path.read_text(encoding="utf-8"))
            mapped = json.loads(map_path.read_text(encoding="utf-8"))
            self.assertEqual(result, {
                "csv_rows_mapped": 1,
                "ambiguous_symbols": [],
                "verified": 1,
                "pending": 2,
            })
            for symbol in ("MISSING", "UNMATCHED"):
                self.assertIsNone(updated["stocks"][symbol]["sector"])
                self.assertEqual(updated["stocks"][symbol]["status"], "pending_official_company_classification")
            self.assertEqual(set(mapped["stocks"]), {"VALID"})

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
