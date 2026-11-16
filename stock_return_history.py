#!/usr/bin/env python3
"""Fetch conservative one-year NSE price returns for the latest company-cache batch.

One historical request per stock and one per distinct benchmark. The result is
research-only display data; it never feeds PDMP final scores or trade decisions.
Returns are unadjusted price returns (no dividends, splits or bonus adjustment).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import time
from pathlib import Path

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
DATA_PATH = Path("stock-company-data.json")
MASTER_PATH = Path("nse-fo-stock-sector-master.json")
BASE = "https://www.nseindia.com"
STOCK_HISTORY_PATH = "/api/historicalOR/generateSecurityWiseHistoricalData"
INDEX_HISTORY_PATH = "/api/historicalOR/indicesHistory"
PAUSE_SECONDS = 1.2
MAX_STALE_DAYS = 7
MAX_BASE_DATE_GAP_DAYS = 10
HISTORY_LOOKBACK_DAYS = 380

# Only exact, defensible sector-to-index mappings. Broad or adjacent sectors
# intentionally remain unmapped rather than receiving a misleading proxy.
SECTOR_INDEX = {
    "Automobile and Auto Components": "NIFTY AUTO",
    "Chemicals": "NIFTY CHEMICALS",
    "Consumer Durables": "NIFTY CONSUMER DURABLES",
    "Fast Moving Consumer Goods": "NIFTY FMCG",
    "Financial Services": "NIFTY FINANCIAL SERVICES",
    "Healthcare": "NIFTY HEALTHCARE INDEX",
    "Information Technology": "NIFTY IT",
    "Metals & Mining": "NIFTY METAL",
    "Oil, Gas & Consumable Fuels": "NIFTY OIL & GAS",
    "Realty": "NIFTY REALTY",
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
    if result <= 0 or result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def norm_header(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


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


def parse_index_history(payload, expected_index=None):
    if not isinstance(payload, dict):
        raise ValueError("NSE index history response is not an object")
    data = payload.get("data")
    rows = data if isinstance(data, list) else (
        data.get("indexCloseOnlineRecords") if isinstance(data, dict) else None
    )
    if not isinstance(rows, list):
        rows = payload.get("indexCloseOnlineRecords")
    if not isinstance(rows, list) or not rows:
        raise ValueError("NSE index history has no dated data rows")
    expected_name = str(expected_index or "").upper().strip()
    accepted_names = {
        "NIFTY FINANCIAL SERVICES": {"NIFTY FINANCIAL SERVICES", "NIFTY FIN SERVICE"},
        "NIFTY HEALTHCARE INDEX": {"NIFTY HEALTHCARE", "NIFTY HEALTHCARE INDEX"},
    }.get(expected_name, {expected_name} if expected_name else set())
    result = {}
    observed_names = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("NSE index history contains a malformed row")
        index_name = first_value(row, ("EOD_INDEX_NAME", "Index Name", "indexName"))
        if index_name:
            normalized_name = " ".join(str(index_name).upper().split())
            observed_names.add(normalized_name)
            if accepted_names and normalized_name not in accepted_names:
                raise ValueError(f"NSE index response name mismatch: {normalized_name} != {expected_name}")
        day_raw = first_value(row, ("EOD_TIMESTAMP", "TIMESTAMP", "HistoricalDate", "Date"))
        close_raw = first_value(row, ("EOD_CLOSE_INDEX_VAL", "CLOSE_INDEX_VAL", "CLOSE", "Close"))
        if not day_raw or close_raw in (None, ""):
            raise ValueError("NSE index history row missing date or close")
        day = parse_date(day_raw)
        close = number(close_raw)
        if close is None:
            raise ValueError(f"NSE index history has invalid close on {day}")
        if day in result:
            raise ValueError(f"NSE index history duplicate date: {day}")
        result[day] = close
    if len(observed_names) > 1:
        raise ValueError("NSE index history contains mixed index names")
    if not result:
        raise ValueError("NSE index history contains no valid dated closes")
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


def seed_session(session):
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/csv, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Cache-Control": "no-cache",
    })
    # NSE may return HTTP 403 for the HTML bootstrap while still issuing
    # session cookies; always make the one official report-page request too.
    # The historical data request itself remains a single no-retry attempt.
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


def fetch_index_history(session, index_name, start_date, end_date):
    params = {
        "indexType": index_name,
        "from": start_date.strftime("%d-%m-%Y"),
        "to": end_date.strftime("%d-%m-%Y"),
    }
    response = session.get(
        BASE + INDEX_HISTORY_PATH, params=params,
        headers={"Referer": BASE + "/reports-indices-historical-index-data"},
        timeout=(10, 45),
    )
    if response.status_code != 200 or not response.content:
        raise RuntimeError(f"NSE index history HTTP {response.status_code}: {index_name}")
    return parse_index_history(response.json(), expected_index=index_name), response.url


def load_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DATA_PATH))
    parser.add_argument("--master", default=str(MASTER_PATH))
    parser.add_argument("--today", help="IST date YYYY-MM-DD for deterministic testing")
    args = parser.parse_args()

    data = load_json(args.data, None)
    master = load_json(args.master, None)
    if not isinstance(data, dict) or not isinstance(data.get("stocks"), dict):
        raise SystemExit("Stock company cache missing or invalid; refusing write")
    if not isinstance(master, dict) or not isinstance(master.get("stocks"), dict):
        raise SystemExit("Verified NSE stock master missing or invalid; refusing write")

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(IST).date()
    performance_state = data.get("performance_history") or {}
    if performance_state.get("last_batch_date") == today.isoformat():
        print("Historical returns already refreshed today; no repeat NSE requests")
        return 0

    batch = data.get("last_batch") or {}
    symbols = [str(x).strip().upper() for x in batch.get("symbols", []) if str(x).strip()]
    symbols = list(dict.fromkeys(symbols))[:10]
    if not symbols:
        print("No latest stock batch; historical return refresh skipped")
        return 0

    start_date = today - dt.timedelta(days=HISTORY_LOOKBACK_DAYS)
    stocks = data["stocks"]
    successful_rows = {}
    stock_urls = {}
    session = requests.Session()
    try:
        seed_session(session)
    except Exception as exc:
        print(f"NSE history session unavailable: {type(exc).__name__}: {str(exc)[:160]}")
        return 0

    for symbol in symbols:
        try:
            rows, url = fetch_stock_history(session, symbol, start_date, today)
            successful_rows[symbol] = rows
            stock_urls[symbol] = url
            print(f"{symbol}: captured {len(rows)} NSE EQ historical closes")
        except Exception as exc:
            print(f"{symbol}: historical return unavailable: {type(exc).__name__}: {str(exc)[:160]}")
        time.sleep(PAUSE_SECONDS)

    stock_periods = {}
    needed_indices = {"NIFTY 50"}
    for symbol, rows in successful_rows.items():
        period = calculate_price_return(rows, today=today)
        if not period:
            print(f"{symbol}: one-year price return withheld (insufficient or stale history)")
            continue
        sector = (master["stocks"].get(symbol) or {}).get("sector") or (stocks.get(symbol) or {}).get("sector")
        index_name = SECTOR_INDEX.get(str(sector or ""))
        stock_periods[symbol] = (period, sector, index_name)
        if index_name:
            needed_indices.add(index_name)

    index_rows = {}
    index_urls = {}
    for index_name in sorted(needed_indices):
        try:
            rows, url = fetch_index_history(session, index_name, start_date, today)
            index_rows[index_name] = rows
            index_urls[index_name] = url
            print(f"{index_name}: captured {len(rows)} official index closes")
        except Exception as exc:
            print(f"{index_name}: benchmark return unavailable: {type(exc).__name__}: {str(exc)[:160]}")
        time.sleep(PAUSE_SECONDS)

    updated = 0
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for symbol, (period, sector, index_name) in stock_periods.items():
        stock_return = dict(period)
        stock_return.update({
            "source": "NSE official historical security-wise price-volume data",
            "source_url": stock_urls[symbol],
        })
        sector_return = None
        if index_name and index_name in index_rows:
            sector_return = calculate_return_for_same_dates(
                index_rows[index_name], period["start_date"], period["end_date"]
            )
            if sector_return:
                sector_return.update({
                    "index": index_name,
                    "source": "NSE official historical index data",
                    "source_url": index_urls[index_name],
                })
        market_return = None
        if "NIFTY 50" in index_rows:
            market_return = calculate_return_for_same_dates(
                index_rows["NIFTY 50"], period["start_date"], period["end_date"]
            )
            if market_return:
                market_return.update({
                    "index": "NIFTY 50",
                    "source": "NSE official historical index data",
                    "source_url": index_urls["NIFTY 50"],
                })
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
            "source_note": "NSE historical closes; same trading-date window for stock, sector index and NIFTY 50. Price return only; dividends and corporate actions are not adjusted.",
            "checked_at": fetched_at,
        }
        current = stocks.get(symbol)
        if isinstance(current, dict):
            current["performance_1y"] = record
            updated += 1
            print(f"{symbol}: saved 1Y stock/sector/market performance (sector={'available' if sector_return else 'unavailable'}, market={'available' if market_return else 'unavailable'})")

    data["performance_history"] = {
        "source": "NSE official historical security-wise and index history endpoints",
        "updated_at": fetched_at,
        "last_batch_date": today.isoformat(),
        "last_batch_symbols": symbols,
        "last_batch_updated": updated,
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
        "stock_history_success": len(successful_rows),
        "performance_updated": updated,
        "index_benchmarks_attempted": len(needed_indices),
        "research_only": True,
        "score_eligible": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
