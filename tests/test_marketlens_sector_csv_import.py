import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_marketlens_sector_csv import import_marketlens_csv


class MarketLensCsvImportTests(unittest.TestCase):
    def test_industry_crosswalk_and_duplicate_ticker_revoke_stale_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 1, "pending_count": 1, "note": ""},
                "stocks": {
                    "ABC": {"industry": None, "sector": None, "status": "pending_official_company_classification"},
                    "XYZ": {
                        "industry": "Banks",
                        "sector": "Financial Services",
                        "status": "verified_nse_marketlens_industry_crosswalk",
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
                "rejected_symbols": [],
                "verified": 1,
                "pending": 1,
            })
            self.assertEqual(updated["stocks"]["ABC"]["industry"], "IT - Software")
            self.assertEqual(updated["stocks"]["ABC"]["sector"], "Information Technology")
            self.assertEqual(updated["stocks"]["ABC"]["status"], "verified_nse_marketlens_industry_crosswalk")
            self.assertIsNone(updated["stocks"]["XYZ"]["sector"])
            self.assertEqual(updated["stocks"]["XYZ"]["status"], "pending_official_company_classification")
            self.assertEqual(set(mapped["stocks"]), {"ABC"})

    def test_energy_industry_crosswalk_and_unknown_macro_alias_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 0, "pending_count": 2, "note": ""},
                "stocks": {
                    "ABC": {"industry": None, "sector": None, "status": "pending_official_company_classification"},
                    "DEF": {"industry": None, "sector": None, "status": "pending_official_company_classification"},
                },
            }
            sector_map = {"stocks": {}, "source": "", "source_url": "", "note": ""}
            master_path, map_path, csv_path = root / "master.json", root / "map.json", root / "marketlens.csv"
            master_path.write_text(json.dumps(master), encoding="utf-8")
            map_path.write_text(json.dumps(sector_map), encoding="utf-8")
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Company", "Sector", "Sub Sector"])
                writer.writeheader()
                writer.writerow({"Company": "ABC LIMITED ABC", "Sector": "Petroleum Products", "Sub Sector": "Energy"})
                writer.writerow({"Company": "DEF LIMITED DEF", "Sector": "Automobiles", "Sub Sector": "M&M"})
            result = import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")
            updated = json.loads(master_path.read_text(encoding="utf-8"))
            self.assertEqual(result, {
                "csv_rows_mapped": 1,
                "ambiguous_symbols": [],
                "rejected_symbols": ["DEF"],
                "verified": 1,
                "pending": 1,
            })
            self.assertEqual(updated["stocks"]["ABC"]["sector"], "Oil, Gas & Consumable Fuels")
            self.assertEqual(updated["stocks"]["ABC"]["industry"], "Petroleum Products")
            self.assertEqual(updated["stocks"]["ABC"]["macro_sector"], "Energy")
            self.assertIsNone(updated["stocks"]["DEF"]["sector"])

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

    def test_missing_or_macro_mismatched_rows_revoke_old_marketlens_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 2, "pending_count": 1, "note": ""},
                "stocks": {
                    "MISSING": {
                        "industry": "Banks", "sector": "Financial Services",
                        "status": "verified_nse_marketlens_industry_crosswalk",
                    },
                    "UNMATCHED": {
                        "industry": "Power", "sector": "Power",
                        "status": "verified_nse_marketlens_industry_crosswalk",
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
                "rejected_symbols": ["UNMATCHED"],
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


    def test_all_new_marketlens_crosswalk_labels_and_macro_sectors(self):
        cases = {
            "FORCEMOT": ("Automobiles", "Automobile and Auto Components", "Consumer Discretionary"),
            "TATAELXSI": ("IT - Software", "Information Technology", "Information Technology"),
            "DATAPATTNS": ("Aerospace & Defense", "Capital Goods", "Industrials"),
            "AMBER": ("Consumer Durables", "Consumer Durables", "Consumer Discretionary"),
            "CUB": ("Banks", "Financial Services", "Financial Services"),
            "NBCC": ("Construction", "Construction", "Industrials"),
            "CAMS": ("Capital Markets", "Financial Services", "Financial Services"),
            "KFINTECH": ("Capital Markets", "Financial Services", "Financial Services"),
            "PGEL": ("Consumer Durables", "Consumer Durables", "Consumer Discretionary"),
            "KPITTECH": ("IT - Software", "Information Technology", "Information Technology"),
            "CROMPTON": ("Consumer Durables", "Consumer Durables", "Consumer Discretionary"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stocks = {
                symbol: {"industry": None, "sector": None, "status": "pending_official_company_classification"}
                for symbol in cases
            }
            master = {"classification": {"verified_count": 0, "pending_count": len(cases), "note": ""}, "stocks": stocks}
            sector_map = {"stocks": {}, "source": "", "source_url": "", "note": ""}
            master_path, map_path, csv_path = root / "master.json", root / "map.json", root / "marketlens.csv"
            master_path.write_text(json.dumps(master), encoding="utf-8")
            map_path.write_text(json.dumps(sector_map), encoding="utf-8")
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Company", "Sector", "Sub Sector"])
                writer.writeheader()
                for symbol, (industry, _sector, macro) in cases.items():
                    writer.writerow({"Company": f"TEST COMPANY {symbol}", "Sector": industry, "Sub Sector": macro})
            result = import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")
            updated = json.loads(master_path.read_text(encoding="utf-8"))
            self.assertEqual(result["csv_rows_mapped"], len(cases))
            self.assertEqual(result["verified"], len(cases))
            self.assertEqual(result["pending"], 0)
            for symbol, (industry, sector, macro) in cases.items():
                self.assertEqual(updated["stocks"][symbol]["industry"], industry)
                self.assertEqual(updated["stocks"][symbol]["sector"], sector)
                self.assertEqual(updated["stocks"][symbol]["macro_sector"], macro)
                self.assertEqual(updated["stocks"][symbol]["status"], "verified_nse_marketlens_industry_crosswalk")



    def test_industry_and_basic_industry_labels_follow_official_parent_sector(self):
        cases = {
            "PIIND": ("Fertilizers & Agrochemicals", "Chemicals", "Commodities"),
            "SAGILITY": ("IT - Services", "Information Technology", "Information Technology"),
            "TCS": ("Computers - Software & Consulting", "Information Technology", "Information Technology"),
            "LICI": ("Life Insurance", "Financial Services", "Financial Services"),
            "LT": ("Civil Construction", "Construction", "Industrials"),
            "POWERGRID": ("Power - Transmission", "Power", "Utilities"),
            "HINDALCO": ("Iron & Steel", "Metals & Mining", "Commodities"),
            "MARUTI": ("Passenger Cars & Utility Vehicles", "Automobile and Auto Components", "Consumer Discretionary"),
            "TITAN": ("Gems, Jewellery And Watches", "Consumer Durables", "Consumer Discretionary"),
            "DMART": ("E-Retail/ E-Commerce", "Consumer Services", "Consumer Discretionary"),
            "NESTLEIND": ("Packaged Foods", "Fast Moving Consumer Goods", "Fast Moving Consumer Goods"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 0, "pending_count": len(cases), "note": ""},
                "stocks": {
                    symbol: {"industry": None, "sector": None, "status": "pending_official_company_classification"}
                    for symbol in cases
                },
            }
            sector_map = {"stocks": {}, "source": "", "source_url": "", "note": ""}
            master_path, map_path, csv_path = root / "master.json", root / "map.json", root / "marketlens.csv"
            master_path.write_text(json.dumps(master), encoding="utf-8")
            map_path.write_text(json.dumps(sector_map), encoding="utf-8")
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Company", "Sector", "Sub Sector"])
                writer.writeheader()
                for symbol, (label, _sector, macro) in cases.items():
                    writer.writerow({"Company": f"TEST COMPANY {symbol}", "Sector": label, "Sub Sector": macro})
            result = import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")
            updated = json.loads(master_path.read_text(encoding="utf-8"))
            self.assertEqual(result["csv_rows_mapped"], len(cases))
            self.assertEqual(result["verified"], len(cases))
            self.assertEqual(result["pending"], 0)
            for symbol, (label, sector, macro) in cases.items():
                self.assertEqual(updated["stocks"][symbol]["industry"], label)
                self.assertEqual(updated["stocks"][symbol]["sector"], sector)
                self.assertEqual(updated["stocks"][symbol]["macro_sector"], macro)



    def test_official_nse_basic_industry_labels_resolve_to_parent_sector(self):
        cases = {
            "ABC": ("Commodity Chemicals", "Chemicals", "Commodities"),
            "DEF": ("Auto Components & Equipments", "Automobile and Auto Components", "Consumer Discretionary"),
            "GHI": ("Speciality Retail", "Consumer Services", "Consumer Discretionary"),
            "JKL": ("Gas Transmission/Marketing", "Oil, Gas & Consumable Fuels", "Energy"),
            "MNO": ("NBFC", "Financial Services", "Financial Services"),
            "PQR": ("Industrial Manufacturing", "Capital Goods", "Industrials"),
            "STU": ("Ship Building & Allied Services", "Capital Goods", "Industrials"),
            "VWX": ("IT Enabled Services", "Information Technology", "Information Technology"),
            "YZA": ("Airline", "Services", "Services"),
            "BCD": ("Power Generation", "Power", "Utilities"),
            "EFG": ("Water Supply & Management", "Utilities", "Utilities"),
            "HIJ": ("Telecom - Infrastructure", "Telecommunication", "Telecommunication"),
            "KLM": ("Paper & Paper Products", "Forest Materials", "Commodities"),
            "NOP": ("Dairy Products", "Fast Moving Consumer Goods", "Fast Moving Consumer Goods"),
            "QRS": ("Medical Equipment & Supplies", "Healthcare", "Healthcare"),
            "TUV": ("Securitisation", "Financial Services", "Financial Services"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = {
                "classification": {"verified_count": 0, "pending_count": len(cases), "note": ""},
                "stocks": {
                    symbol: {"industry": None, "sector": None, "status": "pending_official_company_classification"}
                    for symbol in cases
                },
            }
            sector_map = {"stocks": {}, "source": "", "source_url": "", "note": ""}
            master_path, map_path, csv_path = root / "master.json", root / "map.json", root / "marketlens.csv"
            master_path.write_text(json.dumps(master), encoding="utf-8")
            map_path.write_text(json.dumps(sector_map), encoding="utf-8")
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Company", "Sector", "Sub Sector"])
                writer.writeheader()
                for symbol, (label, _sector, macro) in cases.items():
                    writer.writerow({"Company": f"TEST COMPANY {symbol}", "Sector": label, "Sub Sector": macro})
            result = import_marketlens_csv(csv_path, master_path, map_path, "2026-11-14")
            updated = json.loads(master_path.read_text(encoding="utf-8"))
            self.assertEqual(result["csv_rows_mapped"], len(cases))
            self.assertEqual(result["verified"], len(cases))
            self.assertEqual(result["pending"], 0)
            for symbol, (label, sector, macro) in cases.items():
                self.assertEqual(updated["stocks"][symbol]["industry"], label)
                self.assertEqual(updated["stocks"][symbol]["sector"], sector)
                self.assertEqual(updated["stocks"][symbol]["macro_sector"], macro)



if __name__ == "__main__":
    unittest.main()
