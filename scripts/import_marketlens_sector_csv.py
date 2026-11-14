#!/usr/bin/env python3
"""Import official NSE MarketLens rows into the F&O sector research master.

MarketLens 'Sector' labels can correspond to either the NSE Indices Industry
or Basic Industry tier. Each exact label is crosswalked to its parent NSE
Indices Sector / NSDL FPI sector. The MarketLens 'Sub Sector' macro-economic
label is checked independently. Ambiguous or unknown rows fail closed; no
company is classified from its name alone.
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
NSE_CLASSIFICATION_URL = "https://www.niftyindices.com/docs/default-source/default-document-library/industry-classification/nse-indices_industry-classification-structure-2023-07.pdf"
FPI_DATA = ROOT / "fpi-sector-data.json"

# MarketLens 'Sector' labels may be Industry- or Basic-Industry-level names.
# Map only explicit labels to their parent NSE Indices Sector / NSDL FPI sector.
NSE_MARKETLENS_LABEL_TO_FPI_SECTOR = {
    "Aerospace & Defense": "Capital Goods",
    "Agricultural Food & other Products": "Fast Moving Consumer Goods",
    "Agricultural, Commercial & Construction Vehicles": "Capital Goods",
    "Auto Components": "Automobile and Auto Components",
    "Automobiles": "Automobile and Auto Components",
    "Passenger Cars & Utility Vehicles": "Automobile and Auto Components",
    "2/3 Wheelers": "Automobile and Auto Components",
    "Banks": "Financial Services",
    "Beverages": "Fast Moving Consumer Goods",
    "Capital Markets": "Financial Services",
    "Cement & Cement Products": "Construction Materials",
    "Chemicals & Petrochemicals": "Chemicals",
    "Construction": "Construction",
    "Civil Construction": "Construction",
    "Consumable Fuels": "Oil, Gas & Consumable Fuels",
    "Consumer Durables": "Consumer Durables",
    "Gems, Jewellery And Watches": "Consumer Durables",
    "Diversified FMCG": "Fast Moving Consumer Goods",
    "Electrical Equipment": "Capital Goods",
    "Ferrous Metals": "Metals & Mining",
    "Iron & Steel": "Metals & Mining",
    "Finance": "Financial Services",
    "Financial Technology (Fintech)": "Financial Services",
    "Fertilizers & Agrochemicals": "Chemicals",
    "Food Products": "Fast Moving Consumer Goods",
    "Packaged Foods": "Fast Moving Consumer Goods",
    "Gas": "Oil, Gas & Consumable Fuels",
    "Healthcare Services": "Healthcare",
    "IT - Software": "Information Technology",
    "IT - Services": "Information Technology",
    "Computers - Software & Consulting": "Information Technology",
    "Industrial Products": "Capital Goods",
    "Insurance": "Financial Services",
    "Life Insurance": "Financial Services",
    "Public Sector Bank": "Financial Services",
    "Private Sector Bank": "Financial Services",
    "Leisure Services": "Consumer Services",
    "Metals & Minerals Trading": "Metals & Mining",
    "Non - Ferrous Metals": "Metals & Mining",
    "Oil": "Oil, Gas & Consumable Fuels",
    "Petroleum Products": "Oil, Gas & Consumable Fuels",
    "Refineries & Marketing": "Oil, Gas & Consumable Fuels",
    "Pharmaceuticals & Biotechnology": "Healthcare",
    "Power": "Power",
    "Power - Transmission": "Power",
    "Realty": "Realty",
    "Retailing": "Consumer Services",
    "E-Retail/ E-Commerce": "Consumer Services",
    "Telecom - Services": "Telecommunication",
    "Transport Infrastructure": "Services",
    "Transport Services": "Services",
    "Commodity Chemicals": "Chemicals",
    "Specialty Chemicals": "Chemicals",
    "Carbon Black": "Chemicals",
    "Dyes And Pigments": "Chemicals",
    "Explosives": "Chemicals",
    "Petrochemicals": "Chemicals",
    "Printing Inks": "Chemicals",
    "Trading - Chemicals": "Chemicals",
    "Industrial Gases": "Chemicals",
    "Fertilizers": "Chemicals",
    "Pesticides & Agrochemicals": "Chemicals",
    "Other Construction Materials": "Construction Materials",
    "Ferro & Silica Manganese": "Metals & Mining",
    "Pig Iron": "Metals & Mining",
    "Sponge Iron": "Metals & Mining",
    "Aluminium": "Metals & Mining",
    "Copper": "Metals & Mining",
    "Zinc": "Metals & Mining",
    "Precious Metals": "Metals & Mining",
    "Diversified Metals": "Metals & Mining",
    "Industrial Minerals": "Metals & Mining",
    "Trading - Metals": "Metals & Mining",
    "Trading - Minerals": "Metals & Mining",
    "Paper & Paper Products": "Forest Materials",
    "Forest Products": "Forest Materials",
    "Jute & Jute Products": "Forest Materials",
    "Auto Dealer": "Automobile and Auto Components",
    "Auto Components & Equipments": "Automobile and Auto Components",
    "Tyres & Rubber Products": "Automobile and Auto Components",
    "Trading - Auto Components": "Automobile and Auto Components",
    "Cycles": "Consumer Durables",
    "Consumer Electronics": "Consumer Durables",
    "Furniture, Home Furnishing": "Consumer Durables",
    "Ceramics": "Consumer Durables",
    "Granites & Marbles": "Consumer Durables",
    "Glass - Consumer": "Consumer Durables",
    "Household Appliances": "Consumer Durables",
    "Houseware": "Consumer Durables",
    "Leather And Leather Products": "Consumer Durables",
    "Leisure Products": "Consumer Durables",
    "Plastic Products - Consumer": "Consumer Durables",
    "Plywood Boards/ Laminates": "Consumer Durables",
    "Sanitary Ware": "Consumer Durables",
    "Paints": "Consumer Durables",
    "Diversified consumer products": "Consumer Durables",
    "Footwear": "Consumer Durables",
    "Textiles & Apparels": "Textiles",
    "Garments & Apparels": "Textiles",
    "Other Textile Products": "Textiles",
    "Trading - Textile Products": "Textiles",
    "Advertising & Media Agencies": "Media, Entertainment & Publication",
    "Electronic Media": "Media, Entertainment & Publication",
    "Web based media and service": "Media, Entertainment & Publication",
    "Print Media": "Media, Entertainment & Publication",
    "Film Production, Distribution & Exhibition": "Media, Entertainment & Publication",
    "Digital Entertainment": "Media, Entertainment & Publication",
    "Media & Entertainment": "Media, Entertainment & Publication",
    "TV Broadcasting & Software Production": "Media, Entertainment & Publication",
    "Printing & Publication": "Media, Entertainment & Publication",
    "Residential, Commercial Projects": "Realty",
    "Real Estate related services": "Realty",
    "Real Estate Investment Trusts (REITs)": "Realty",
    "Hotels & Resorts": "Consumer Services",
    "Restaurants": "Consumer Services",
    "Amusement Parks/ Other Recreation": "Consumer Services",
    "Wellness": "Consumer Services",
    "Tour, Travel Related Services": "Consumer Services",
    "Education": "Consumer Services",
    "E-Learning": "Consumer Services",
    "Food Storage Facilities": "Consumer Services",
    "Other Consumer Services": "Consumer Services",
    "Speciality Retail": "Consumer Services",
    "Pharmacy Retail": "Consumer Services",
    "Diversified Retail": "Consumer Services",
    "Internet & Catalogue Retail": "Consumer Services",
    "Distributors": "Consumer Services",
    "Gas Transmission/Marketing": "Oil, Gas & Consumable Fuels",
    "LPG/CNG/PNG/LNG Supplier": "Oil, Gas & Consumable Fuels",
    "Trading - Gas": "Oil, Gas & Consumable Fuels",
    "Oil Exploration & Production": "Oil, Gas & Consumable Fuels",
    "Offshore Support Solution Drilling": "Oil, Gas & Consumable Fuels",
    "Oil Storage & Transportation": "Oil, Gas & Consumable Fuels",
    "Oil Equipment & Services": "Oil, Gas & Consumable Fuels",
    "Lubricants": "Oil, Gas & Consumable Fuels",
    "Coal": "Oil, Gas & Consumable Fuels",
    "Trading - Coal": "Oil, Gas & Consumable Fuels",
    "Edible Oil": "Fast Moving Consumer Goods",
    "Sugar": "Fast Moving Consumer Goods",
    "Tea & Coffee": "Fast Moving Consumer Goods",
    "Other Agricultural Products": "Fast Moving Consumer Goods",
    "Breweries & Distilleries": "Fast Moving Consumer Goods",
    "Other Beverages": "Fast Moving Consumer Goods",
    "Cigarettes & Tobacco Products": "Fast Moving Consumer Goods",
    "Animal Feed": "Fast Moving Consumer Goods",
    "Dairy Products": "Fast Moving Consumer Goods",
    "Other Food Products": "Fast Moving Consumer Goods",
    "Seafood": "Fast Moving Consumer Goods",
    "Meat Products including Poultry": "Fast Moving Consumer Goods",
    "Personal Care": "Fast Moving Consumer Goods",
    "Household Products": "Fast Moving Consumer Goods",
    "Stationary": "Fast Moving Consumer Goods",
    "Financial Institution": "Financial Services",
    "Housing Finance Company": "Financial Services",
    "Investment Company": "Financial Services",
    "Other Financial Services Holding Company": "Financial Services",
    "Microfinance Institutions": "Financial Services",
    "Securitisation": "Financial Services",
    "Other Bank": "Financial Services",
    "Asset Management Company": "Financial Services",
    "Depositories, Clearing Houses and Other Intermediaries": "Financial Services",
    "Financial Products Distributor": "Financial Services",
    "Ratings": "Financial Services",
    "Exchange and Data Platform": "Financial Services",
    "Stockbroking & Allied": "Financial Services",
    "Other Capital Market related Services": "Financial Services",
    "General Insurance": "Financial Services",
    "Other Insurance Companies": "Financial Services",
    "Insurance Distributors": "Financial Services",
    "Biotechnology": "Healthcare",
    "Medical Equipment & Supplies": "Healthcare",
    "Hospital": "Healthcare",
    "Healthcare Service Provider": "Healthcare",
    "Healthcare Research, Analytics & Technology": "Healthcare",
    "Tractors": "Capital Goods",
    "Commercial Vehicles": "Capital Goods",
    "Construction Vehicles": "Capital Goods",
    "Dealers–Commercial Vehicles, Tractors, Construction Vehicles": "Capital Goods",
    "Heavy Electrical Equipment": "Capital Goods",
    "Other Electrical Equipment": "Capital Goods",
    "Industrial Manufacturing": "Capital Goods",
    "Railway Wagons": "Capital Goods",
    "Ship Building & Allied Services": "Capital Goods",
    "Cables - Electricals": "Capital Goods",
    "Castings & Forgings": "Capital Goods",
    "Packaging": "Capital Goods",
    "Plastic Products - Industrial": "Capital Goods",
    "Rubber": "Capital Goods",
    "Other Industrial Products": "Capital Goods",
    "Glass - Industrial": "Capital Goods",
    "Aluminium, Copper & Zinc Products": "Capital Goods",
    "Iron & Steel Products": "Capital Goods",
    "Abrasives & Bearings": "Capital Goods",
    "Compressors, Pumps & Diesel Engines": "Capital Goods",
    "Electrodes & Refractories": "Capital Goods",
    "Software Products": "Information Technology",
    "IT Enabled Services": "Information Technology",
    "Computers Hardware & Equipments": "Information Technology",
    "Dredging": "Services",
    "Airline": "Services",
    "Logistics Solution Provider": "Services",
    "Railways": "Services",
    "Road Transport": "Services",
    "Shipping": "Services",
    "Transport Related Services": "Services",
    "Airport & Airport services": "Services",
    "Port & Port services": "Services",
    "Road Assets–Toll, Annuity, Hybrid-Annuity": "Services",
    "Trading & Distributors": "Services",
    "Consulting Services": "Services",
    "Data Processing Services": "Services",
    "Diversified Commercial Services": "Services",
    "Business Process Outsourcing (BPO)/ Knowledge Process Outsourcing (KPO)": "Services",
    "Urban Local Bodies": "Services",
    "Development Authority": "Services",
    "Telecom - Cellular & Fixed line services": "Telecommunication",
    "Telecom - Infrastructure": "Telecommunication",
    "Other Telecom Services": "Telecommunication",
    "Telecom - Equipment & Accessories": "Telecommunication",
    "Power Generation": "Power",
    "Integrated Power Utilities": "Power",
    "Power Trading": "Power",
    "Power Distribution": "Power",
    "Water Supply & Management": "Utilities",
    "Waste Management": "Utilities",
    "Emergency Services": "Utilities",
    "Multi Utilities": "Utilities",
    "Other Utilities": "Utilities",
}

# The MarketLens 'Sub Sector' must agree with the macro-economic parent of
# the mapped NSE Indices Sector. Unrecognised labels (for example 'M&M') fail
# closed rather than being guessed.
MACRO_SECTOR_BY_FPI_SECTOR = {
    "Automobile and Auto Components": "Consumer Discretionary",
    "Capital Goods": "Industrials",
    "Chemicals": "Commodities",
    "Construction": "Industrials",
    "Construction Materials": "Commodities",
    "Consumer Durables": "Consumer Discretionary",
    "Consumer Services": "Consumer Discretionary",
    "Diversified": "Diversified",
    "Fast Moving Consumer Goods": "Fast Moving Consumer Goods",
    "Financial Services": "Financial Services",
    "Forest Materials": "Commodities",
    "Healthcare": "Healthcare",
    "Information Technology": "Information Technology",
    "Media, Entertainment & Publication": "Consumer Discretionary",
    "Metals & Mining": "Commodities",
    "Oil, Gas & Consumable Fuels": "Energy",
    "Power": "Utilities",
    "Realty": "Consumer Discretionary",
    "Services": "Services",
    "Telecommunication": "Telecommunication",
    "Textiles": "Consumer Discretionary",
    "Utilities": "Utilities",
}


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
        macro_sector_col = headers.get("subsector")
        if not all((company_col, industry_col, macro_sector_col)):
            raise ValueError("CSV must contain Company, Sector and Sub Sector columns")

        for row in reader:
            symbol = symbol_from_company(row.get(company_col, ""), universe)
            if not symbol:
                continue
            rows_by_symbol.setdefault(symbol, []).append({
                "industry": (row.get(industry_col) or "").strip(),
                "macro_sector": (row.get(macro_sector_col) or "").strip(),
            })

    imported = {}
    ambiguous = []
    rejected = []
    for symbol, rows in rows_by_symbol.items():
        # Multiple rows for one ticker are not silently resolved by row order.
        if len(rows) != 1:
            ambiguous.append(symbol)
            continue
        industry, macro_sector = rows[0]["industry"], rows[0]["macro_sector"]
        fpi_sector = NSE_MARKETLENS_LABEL_TO_FPI_SECTOR.get(industry)
        expected_macro = MACRO_SECTOR_BY_FPI_SECTOR.get(fpi_sector or "")
        if (
            industry
            and fpi_sector in allowed
            and expected_macro
            and macro_sector == expected_macro
        ):
            imported[symbol] = {
                "industry": industry,
                "sector": fpi_sector,
                "macro_sector": macro_sector,
                "status": "verified_nse_marketlens_industry_crosswalk",
                "verified_on": verified_on,
                "source": (
                    "NSE MarketLens official screener CSV; Sector industry label "
                    "mapped through NSE Indices Industry Classification Structure "
                    "to NSDL FPI Sector; Sub Sector macro label independently matched"
                ),
                "source_url": MARKETLENS_URL,
                "classification_reference_url": NSE_CLASSIFICATION_URL,
            }
        else:
            rejected.append(symbol)

    for symbol in universe:
        current = master["stocks"][symbol]
        if current.get("status") == "verified_existing_mapping":
            # Preserve the original, separately verified watchlist evidence.
            continue
        if symbol in imported:
            master["stocks"][symbol] = imported[symbol]
        else:
            # A fresh export supersedes prior MarketLens imports. Missing,
            # unmatched, duplicate and macro-inconsistent rows fail closed.
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
        "Verified rows are supported by the seven separately verified original "
        "watchlist mappings or by official NSE MarketLens CSV company rows. "
        "For MarketLens rows, the Sector industry label is crosswalked to the "
        "NSDL FPI 22-sector taxonomy using NSE Indices Industry Classification; "
        "the Sub Sector macro-economic label must independently agree. "
        "Duplicate, missing, unrecognised or macro-inconsistent rows remain pending."
    )
    stock_map["source"] = (
        "NSE MarketLens Industry label crosswalked to NSE Indices Sector / "
        "NSDL FPI 22-sector taxonomy"
    )
    stock_map["source_url"] = MARKETLENS_URL
    stock_map["note"] = (
        f"{len(verified)} verified F&O company mappings. MarketLens company "
        "industry labels are mapped through the NSE Indices classification "
        "structure and macro-sector cross-checked. This research master does "
        "not add dashboard cards or expand the watchlist; only currently rendered "
        "stock cards can display tags. Pending symbols produce no tag."
    )
    stock_map["stocks"] = verified

    master_path.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    map_path.write_text(json.dumps(stock_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "csv_rows_mapped": len(imported),
        "ambiguous_symbols": sorted(ambiguous),
        "rejected_symbols": sorted(rejected),
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
