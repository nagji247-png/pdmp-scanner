#!/usr/bin/env python3
"""Import an official NSE MarketLens CSV into the F&O sector research master.

Only exact matches between MarketLens 'Sub Sector' and the NSDL FPI 22-sector
taxonomy are accepted. Duplicate ticker rows are treated as ambiguous and fail
closed instead of silently allowing the last row to win.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_DEFAULT = ROOT / "nse-fo-stock-sector-master.json"
MAP_DEFAULT = ROOT / "fpi-stock-sector-map.json"
MARKETLENS_URL = "https://marketlens.nseindia.com/screener"
FPI_DATA = ROOT / "fpi-sector-data.json"


def allowed_fpi_sectors() -> set[str]:
    data = json.loads(FPI_DATA.read_text(encoding="utf-8"))
    return {item["name"] for item in data["history"][0]["sectors"]}


def normalized_headers(headers):
    return {"".join(ch for ch in (h or "").lower() if ch.isalnum()): h for h in headers}


def symbol_from_company(value: str, universe: set[str]) -> str | None:
    value = (value or "").strip().upper()
    # Match the full ticker suffix, including symbols containing '&' or '-'.
    for symbol in sorted(universe, key=len, reverse=True):
        if value == symbol or value.endswith(" " + symbol):
            return symbol
    return None


def import_marketlens_csv(csv_path: Path, master_path: Path, map_path: Path,
                          verified_on: str | None = None) -> dict:
    master = json.loads(master_path.read_text(encoding="utf-8"))
    stock_map = json.loads(map_path.read_text(encoding="utf-8"))
    universe = set(master["stocks"])
    allowed = allowed_fpi_sectors()
    verified_on = verified_on or date.today().isoformat()

    rows_by_symbol = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = normalized_headers(reader.fieldnames or [])
        company_col = headers.get("company") or headers.get("stock")
        industry_col = headers.get("sector")
        fpi_sector_col = headers.get("subsector")
        if not all((company_col, industry_col, fpi_sector_col)):
            raise ValueError("CSV must contain Company, Sector and Sub Sector columns")

        for row in reader:
            symbol = symbol_from_company(row.get(company_col, ""), universe)
            if not symbol:
                continue
            rows_by_symbol.setdefault(symbol, []).append({
                "industry": (row.get(industry_col) or "").strip(),
                "sector": (row.get(fpi_sector_col) or "").strip(),
            })

    imported = {}
    ambiguous = []
    for symbol, rows in rows_by_symbol.items():
        # Multiple rows for one ticker are not silently resolved by row order.
        if len(rows) != 1:
            ambiguous.append(symbol)
            continue
        industry, sector = rows[0]["industry"], rows[0]["sector"]
        if industry and sector in allowed:
            imported[symbol] = {
                "industry": industry,
                "sector": sector,
                "status": "verified_nse_marketlens_sector_match",
                "verified_on": verified_on,
                "source": "NSE MarketLens official screener CSV; Sub Sector exactly matches NSDL FPI sector label",
                "source_url": MARKETLENS_URL,
            }

    for symbol in universe:
        if symbol in imported:
            # Keep the original, separately verified watchlist evidence intact.
            if master["stocks"][symbol].get("status") != "verified_existing_mapping":
                master["stocks"][symbol] = imported[symbol]
        elif master["stocks"][symbol].get("status") == "pending_official_company_classification":
            master["stocks"][symbol] = {
                "industry": None,
                "sector": None,
                "status": "pending_official_company_classification",
            }

    verified = {
        symbol: {"industry": record["industry"], "sector": record["sector"]}
        for symbol, record in master["stocks"].items()
        if record.get("status") != "pending_official_company_classification"
        and record.get("sector") in allowed
        and record.get("industry")
    }
    pending_count = sum(
        record.get("status") == "pending_official_company_classification"
        for record in master["stocks"].values()
    )
    master["classification"]["verified_count"] = len(verified)
    master["classification"]["pending_count"] = pending_count
    master["classification"]["note"] = (
        "Verified rows are supported by official NSE MarketLens CSV records whose "
        "Sub Sector exactly matches one of the NSDL FPI 22-sector labels. "
        "Duplicate, unmatched or ambiguous rows remain pending and fail closed."
    )
    stock_map["source"] = "NSE MarketLens company industry labels joined to NSDL FPI 22-sector labels"
    stock_map["source_url"] = MARKETLENS_URL
    stock_map["note"] = (
        f"{len(verified)} verified F&O company mappings. This research master does "
        "not add dashboard cards or expand the watchlist; only currently rendered "
        "stock cards can display tags. Pending symbols produce no tag."
    )
    stock_map["stocks"] = verified

    master_path.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    map_path.write_text(json.dumps(stock_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "csv_rows_mapped": len(imported),
        "ambiguous_symbols": sorted(ambiguous),
        "verified": len(verified),
        "pending": pending_count,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="Official NSE MarketLens CSV export")
    parser.add_argument("--master", type=Path, default=MASTER_DEFAULT)
    parser.add_argument("--map", type=Path, default=MAP_DEFAULT)
    parser.add_argument("--verified-on")
    args = parser.parse_args()
    result = import_marketlens_csv(args.csv, args.master, args.map, args.verified_on)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
