#!/usr/bin/env python3
"""Capture NSE stock 1Y price returns and compare them with archived NSE index closes.

Stock history is fetched only for the latest 10-stock research batch. Sector and
NIFTY 50 comparisons are recalculated locally from the official NSE daily index
close archive, so archive backfill never multiplies live index API requests.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import re
import time
from pathlib import Path

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
DATA_PATH = Path("stock-company-data.json")
MASTER_PATH = Path("nse-fo-stock-sector-master.json")
INDEX_ARCHIVE_PATH = Path("nse_index_close_archive.json")
BATCH_SIZE = 10
BASE = "https://www.nseindia.com"
STOCK_HISTORY_PATH = "/api/historicalOR/generateSecurityWiseHistoricalData"
PAUSE_SECONDS = 1.2
MAX_STALE_DAYS = 7
MAX_BASE_DATE_GAP_DAYS = 10
HISTORY_LOOKBACK_DAYS = 365
BENCHMARK_SOURCE_VERSION = "NSE official Daily Snapshot index archive · 260 sessions v1"

# Only exact NSE sector classifications with a matching Nifty sector index.
SECTOR_INDEX = {
    "Automobile and Auto Components": "NIFTY AUTO",
    "Capital Goods": "NIFTY CAPITAL GOODS",
    "Chemicals": "NIFTY CHEMICALS",
    "Consumer Durables": "NIFTY CONSUMER DURABLES",
    "Consumer Services": "NIFTY CONSUMER SERVICES",
    "Fast Moving Consumer Goods": "NIFTY FMCG",
    "Financial Services": "NIFTY FINANCIAL SERVICES",
    "Healthcare": "NIFTY HEALTHCARE",
    "Information Technology": "NIFTY IT",
    "Metals & Mining": "NIFTY METAL",
    "Oil, Gas & Consumable Fuels": "NIFTY OIL AND GAS INDEX",
    "Power": "NIFTY POWER",
    "Realty": "NIFTY REALTY",
    "Telecommunication": "NIFTY TELECOMMUNICATIONS",
}

# Daily Snapshot names can use short display labels; aliases are explicit.
INDEX_ARCHIVE_ALIASES = {
    "NIFTY 50": {"NIFTY50"},
    "NIFTY AUTO": {"NIFTYAUTO"},
    "NIFTY CAPITAL GOODS": {"NIFTYCAPITALGOODS"},
    "NIFTY CHEMICALS": {"NIFTYCHEMICALS"},
    "NIFTY CONSUMER DURABLES": {"NIFTYCONSUMERDURABLES", "NIFTYCONSRDURBL"},
    "NIFTY CONSUMER SERVICES": {"NIFTYCONSUMERSERVICES"},
    "NIFTY FINANCIAL SERVICES": {"NIFTYFINANCIALSERVICES", "NIFTYFINSERVICE"},
    "NIFTY FMCG": {"NIFTYFMCG"},
    "NIFTY HEALTHCARE": {"NIFTYHEALTHCARE", "NIFTYHEALTHCAREINDEX"},
    "NIFTY IT": {"NIFTYIT"},
    "NIFTY METAL": {"NIFTYMETAL"},
    "NIFTY OIL AND GAS INDEX": {"NIFTYOILGAS", "NIFTYOILANDGASINDEX"},
    "NIFTY POWER": {"NIFTYPOWER"},
    "NIFTY REALTY": {"NIFTYREALTY"},
    "NIFTY TELECOMMUNICATIONS": {"NIFTYTELECOM", "NIFTYTELECOMMUNICATIONS"},
}


def parse_date(value):
    raw = str(value or "").strip()
    for fmt in ("%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid historical date: {raw!r}")


def number(value):
    raw = str(value if value is not None else "").strip().replace(",", "").replace("₹", "")
    if not raw or raw in ("-", "—", "NA", "N/A", "null"):
        return None
    try:
        result = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 and result == result and result not in (float("inf"), float("-inf")) else None


def norm_header(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def index_key(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def first_value(row, aliases):
    normalized = {norm_header(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(norm_header(alias))
        if value not in (None, ""):
            return value
    return None


def parse_stock_history_csv(payload, symbol):
    if not isinstance(payload, (bytes, bytearray, str)) or not payload:
        raise ValueError("empty NSE stock history response")
    raw = payload.decode("utf-8-sig", errors="replace") if isinstance(payload, (bytes, bytearray)) else payload
    if raw.lstrip().startswith(("<", "{", "[")):
        raise ValueError("NSE stock history returned HTML/JSON instead of CSV")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise ValueError("NSE stock history CSV header missing")
    required = {"date", "symbol", "series"}
    headers = {norm_header(item) for item in reader.fieldnames}
    if not required.issubset(headers):
        raise ValueError("NSE stock history CSV missing Date, Symbol or Series")
    result = {}
    for row in reader:
        row_symbol = str(first_value(row, ("Symbol",)) or "").strip().upper()
        series = str(first_value(row, ("Series",)) or "").strip().upper()
        if row_symbol != symbol.upper() or series != "EQ":
            continue
        day = parse_date(first_value(row, ("Date", "mTIMESTAMP", "Timestamp")))
        close = number(first_value(row, ("Close Price", "Close", "ClsPric")))
        if close is None:
            raise ValueError(f"NSE stock history has invalid close for {symbol} on {day}")
        if day in result:
            raise ValueError(f"NSE stock history duplicate EQ date for {symbol}: {day}")
        result[day] = close
    if not result:
        raise ValueError(f"NSE stock history has no EQ rows for {symbol}")
    return result


def calculate_price_return(rows, today=None):
    if not isinstance(rows, dict) or len(rows) < 2:
        return None
    today = today or dt.datetime.now(IST).date()
    dates = sorted(rows)
    end_date = dates[-1]
    if (today - end_date).days > MAX_STALE_DAYS:
        return None
    target = end_date - dt.timedelta(days=365)
    candidates = [day for day in dates if day >= target]
    if not candidates:
        return None
    start_date = candidates[0]
    if (start_date - target).days > MAX_BASE_DATE_GAP_DAYS:
        return None
    start_close, end_close = rows[start_date], rows[end_date]
    if start_close <= 0 or end_close <= 0:
        return None
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": (end_date - start_date).days,
        "start_close": round(start_close, 6),
        "end_close": round(end_close, 6),
        "return_pct": round((end_close / start_close - 1) * 100, 4),
        "method": "unadjusted_price_return",
        "corporate_actions_adjusted": False,
        "dividends_included": False,
    }


def cached_stock_period(stock_return):
    if not isinstance(stock_return, dict):
        return None
    try:
        start_day = parse_date(stock_return.get("start_date"))
        end_day = parse_date(stock_return.get("end_date"))
        start_close = number(stock_return.get("start_close"))
        end_close = number(stock_return.get("end_close"))
        pct = float(stock_return.get("return_pct"))
    except (TypeError, ValueError):
        return None
    if (
        (end_day - start_day).days < 350
        or start_close is None
        or end_close is None
        or not math.isfinite(pct)
    ):
        return None
    return {
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "days": (end_day - start_day).days,
        "start_close": round(start_close, 6),
        "end_close": round(end_close, 6),
        "return_pct": round(pct, 4),
        "method": "unadjusted_price_return",
        "corporate_actions_adjusted": False,
        "dividends_included": False,
    }


def build_index_series(index_archive, index_name):
    aliases = INDEX_ARCHIVE_ALIASES.get(index_name, {index_key(index_name)})
    series = {}
    sources = {}
    for record in index_archive.get("records", []):
        if not isinstance(record, dict):
            continue
        try:
            day = parse_date(record.get("date"))
        except ValueError:
            continue
        values = record.get("indices") or {}
        matches = [
            (raw_name, value)
            for raw_name, value in values.items()
            if index_key(raw_name) in aliases
        ]
        if len(matches) > 1:
            raise ValueError(f"ambiguous NSE index archive mapping for {index_name} on {day}")
        if not matches:
            continue
        close = number(matches[0][1])
        if close is None:
            continue
        if day in series:
            raise ValueError(f"duplicate NSE index archive date for {index_name}: {day}")
        series[day] = close
        sources[day] = record.get("source_url")
    return series, sources


def calculate_return_for_same_dates(rows, start_date, end_date):
    if not isinstance(rows, dict):
        return None
    start = parse_date(start_date)
    end = parse_date(end_date)
    if start not in rows or end not in rows:
        return None
    start_close, end_close = rows[start], rows[end]
    if start_close <= 0 or end_close <= 0:
        return None
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "start_close": round(start_close, 6),
        "end_close": round(end_close, 6),
        "return_pct": round((end_close / start_close - 1) * 100, 4),
        "method": "unadjusted_price_return",
        "corporate_actions_adjusted": False,
        "dividends_included": False,
    }


def calculate_archived_benchmark_return(index_archive, index_name, start_date, end_date):
    series, sources = build_index_series(index_archive, index_name)
    result = calculate_return_for_same_dates(series, start_date, end_date)
    if not result:
        return None
    start_day = parse_date(start_date)
    end_day = parse_date(end_date)
    result.update({
        "index": index_name,
        "source": "NSE official Daily Snapshot (ind_close_all)",
        "start_source_url": sources.get(start_day),
        "end_source_url": sources.get(end_day),
    })
    return result


def seed_session(session):
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/csv, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Cache-Control": "no-cache",
    })
    session.get(BASE + "/", timeout=20)
    time.sleep(PAUSE_SECONDS)
    session.get(BASE + "/report-detail/eq_security", timeout=20)
    time.sleep(PAUSE_SECONDS)


def fetch_stock_history(session, symbol, start_date, end_date):
    params = {
        "from": start_date.strftime("%d-%m-%Y"),
        "to": end_date.strftime("%d-%m-%Y"),
        "symbol": symbol,
        "type": "priceVolumeDeliverable",
        "series": "EQ",
        "csv": "true",
    }
    response = session.get(
        BASE + STOCK_HISTORY_PATH, params=params,
        headers={"Referer": BASE + "/report-detail/eq_security"},
        timeout=(10, 45),
    )
    if response.status_code != 200 or not response.content:
        raise RuntimeError(f"NSE stock history HTTP {response.status_code}")
    rows = parse_stock_history_csv(response.content, symbol)
    return rows, response.url


def load_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DATA_PATH))
    parser.add_argument("--master", default=str(MASTER_PATH))
    parser.add_argument("--index-archive", default=str(INDEX_ARCHIVE_PATH))
    parser.add_argument("--today", help="IST date YYYY-MM-DD for deterministic testing")
    args = parser.parse_args()

    data = load_json(args.data, None)
    master = load_json(args.master, None)
    index_archive = load_json(args.index_archive, {"records": [], "updated_at": None})
    if not isinstance(data, dict) or not isinstance(data.get("stocks"), dict):
        raise SystemExit("Stock company cache missing or invalid; refusing write")
    if not isinstance(master, dict) or not isinstance(master.get("stocks"), dict):
        raise SystemExit("Verified NSE stock master missing or invalid; refusing write")
    if not isinstance(index_archive, dict) or not isinstance(index_archive.get("records"), list):
        raise SystemExit("NSE index close archive invalid; refusing overwrite")

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(IST).date()
    archive_updated_at = index_archive.get("updated_at")
    performance_state = data.get("performance_history") or {}
    if (
        performance_state.get("last_batch_date") == today.isoformat()
        and performance_state.get("benchmark_source") == BENCHMARK_SOURCE_VERSION
        and performance_state.get("index_archive_updated_at") == archive_updated_at
    ):
        print("Historical returns already refreshed against this NSE index archive; no repeat NSE requests")
        return 0

    batch = data.get("last_batch") or {}
    symbols = [str(x).strip().upper() for x in batch.get("symbols", []) if str(x).strip()]
    symbols = list(dict.fromkeys(symbols))[:BATCH_SIZE]
    stocks = data["stocks"]
    cached_symbols = [
        symbol for symbol, record in stocks.items()
        if isinstance(record, dict) and cached_stock_period((record.get("performance_1y") or {}).get("stock_return"))
    ]
    if not symbols and not cached_symbols:
        print("No stock batch or cached one-year stock returns; refresh skipped")
        return 0

    start_date = today - dt.timedelta(days=HISTORY_LOOKBACK_DAYS)
    successful_rows = {}
    stock_urls = {}
    stock_periods = {}
    session = requests.Session()
    stock_session_ready = None

    # Refresh the latest company-research batch; old stock returns are reused.
    for symbol in symbols:
        current = stocks.get(symbol) if isinstance(stocks.get(symbol), dict) else {}
        existing = current.get("performance_1y") or {}
        existing_stock = existing.get("stock_return") or {}
        period = None
        try:
            end_day = parse_date(existing_stock.get("end_date"))
            if (today - end_day).days <= MAX_STALE_DAYS:
                period = cached_stock_period(existing_stock)
                if period:
                    stock_urls[symbol] = existing_stock.get("source_url")
                    print(f"{symbol}: reusing fresh NSE one-year stock return")
        except (TypeError, ValueError):
            period = None

        sector = (master["stocks"].get(symbol) or {}).get("sector") or current.get("sector")
        index_name = SECTOR_INDEX.get(str(sector or ""))
        if period is None:
            if stock_session_ready is None:
                try:
                    seed_session(session)
                    stock_session_ready = True
                except Exception as exc:
                    stock_session_ready = False
                    print(f"NSE stock history session unavailable: {type(exc).__name__}: {str(exc)[:160]}")
            if stock_session_ready:
                try:
                    rows, url = fetch_stock_history(session, symbol, start_date, today)
                    successful_rows[symbol] = rows
                    period = calculate_price_return(rows, today=today)
                    stock_urls[symbol] = url
                    print(f"{symbol}: captured {len(rows)} NSE EQ historical closes")
                except Exception as exc:
                    print(f"{symbol}: historical return unavailable: {type(exc).__name__}: {str(exc)[:160]}")
                time.sleep(PAUSE_SECONDS)
        if period:
            stock_periods[symbol] = (period, sector, index_name)

    # Recalculate archived benchmarks for every cached stock return. This is local
    # work only; it does not make one live request per stock or per index.
    for symbol, current in stocks.items():
        if symbol in stock_periods or not isinstance(current, dict):
            continue
        existing_stock = ((current.get("performance_1y") or {}).get("stock_return") or {})
        period = cached_stock_period(existing_stock)
        if not period:
            continue
        sector = (master["stocks"].get(symbol) or {}).get("sector") or current.get("sector")
        index_name = SECTOR_INDEX.get(str(sector or ""))
        stock_periods[symbol] = (period, sector, index_name)
        stock_urls[symbol] = existing_stock.get("source_url")

    updated = 0
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    index_archive_dates = [
        parse_date(row["date"]) for row in index_archive.get("records", [])
        if isinstance(row, dict) and row.get("date")
    ]
    index_archive_as_of = max(index_archive_dates).isoformat() if index_archive_dates else None
    for symbol, (period, sector, index_name) in stock_periods.items():
        stock_return = dict(period)
        stock_return.update({
            "source": "NSE official historical security-wise price-volume data",
            "source_url": stock_urls.get(symbol),
        })
        sector_return = (
            calculate_archived_benchmark_return(
                index_archive, index_name, period["start_date"], period["end_date"]
            ) if index_name else None
        )
        market_return = calculate_archived_benchmark_return(
            index_archive, "NIFTY 50", period["start_date"], period["end_date"]
        )
        record = {
            "as_of": period["end_date"],
            "start_date": period["start_date"],
            "end_date": period["end_date"],
            "stock_return": stock_return,
            "sector": sector,
            "sector_index": index_name,
            "sector_return": sector_return,
            "market_index": "NIFTY 50",
            "market_return": market_return,
            "method": "unadjusted_price_return",
            "corporate_actions_adjusted": False,
            "dividends_included": False,
            "source_note": "NSE official stock historical closes + NSE official Daily Snapshot index closes; same trading-date window. Unadjusted price return only; dividends and corporate actions are not adjusted.",
            "index_archive_as_of": index_archive_as_of,
            "index_archive_sessions": len(index_archive.get("records", [])),
            "index_archive_updated_at": archive_updated_at,
            "benchmark_source": BENCHMARK_SOURCE_VERSION,
            "checked_at": fetched_at,
        }
        current = stocks.get(symbol)
        if isinstance(current, dict):
            current["performance_1y"] = record
            updated += 1
            print(f"{symbol}: saved 1Y returns (sector={'available' if sector_return else 'unavailable'}, market={'available' if market_return else 'unavailable'}, archive_sessions={len(index_archive.get('records', []))})")

    data["performance_history"] = {
        "source": "NSE official stock history + NSE Daily Snapshot index close archive",
        "benchmark_source": BENCHMARK_SOURCE_VERSION,
        "updated_at": fetched_at,
        "last_batch_date": today.isoformat(),
        "last_batch_symbols": symbols,
        "last_batch_updated": updated,
        "index_archive_updated_at": archive_updated_at,
        "index_archive_sessions": len(index_archive.get("records", [])),
        "research_only": True,
        "score_eligible": False,
    }
    Path(args.data).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "ok",
        "attempted_symbols": len(symbols),
        "stock_history_fetched": len(successful_rows),
        "stock_periods_ready": len(stock_periods),
        "performance_updated": updated,
        "index_archive_sessions": len(index_archive.get("records", [])),
        "index_archive_as_of": index_archive_as_of,
        "research_only": True,
        "score_eligible": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
