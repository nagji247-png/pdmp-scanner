#!/usr/bin/env python3
"""Incrementally cache public NSE company metadata and quarterly shareholding.

This runs once daily and touches a small batch only. It is intentionally separate
from the 30-minute PDMP scan to avoid multiplying NSE requests.
"""
import datetime as dt
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "nse-fo-stock-sector-master.json"
OUT = ROOT / "stock-company-data.json"
BATCH_SIZE = max(1, min(25, int(os.environ.get("STOCK_RESEARCH_BATCH_SIZE", "10"))))
PAUSE_SECONDS = 1.2
BASE = "https://www.nseindia.com/api"


def number(value):
    if value in (None, "", "-", "—", "–"):
        return None
    try:
        result = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def pick(obj, *keys):
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def parse_company_quote(payload, trade_payload=None):
    if not isinstance(payload, dict):
        return {}
    info = payload.get("info") or payload.get("metadata") or {}
    industry = payload.get("industryInfo") or {}
    price = payload.get("priceInfo") or {}
    security = payload.get("securityInfo") or {}
    trade = pick(trade_payload or {}, "marketDeptOrderBook", "tradeInfo") or {}
    market_cap = number(trade.get("totalMarketCap"))
    if market_cap is None:
        market_cap = number(trade.get("marketCap"))
    return {
        "company_name": info.get("companyName") or info.get("company") or payload.get("companyName"),
        "isin": info.get("isin"),
        "industry": industry.get("industry") or industry.get("basicIndustry"),
        "nse_sector": industry.get("sector"),
        "macro_sector": industry.get("macro"),
        "price": number(price.get("lastPrice")),
        "change_pct": number(price.get("pChange")),
        "market_cap_cr": market_cap,
        "face_value": number(security.get("faceValue")),
        "quote_source": "NSE India public quote-equity API",
        "market_cap_source": "NSE India public quote-equity trade_info API" if market_cap is not None else None,
    }


def parse_shareholding(payload):
    if not isinstance(payload, list) or not payload:
        return None
    rows = [row for row in payload if isinstance(row, dict) and row.get("date")]
    rows.sort(key=lambda row: str(row.get("date")), reverse=True)
    if not rows:
        return None

    def pct(row, key):
        return number(row.get(key))

    latest, previous = rows[0], rows[1] if len(rows) > 1 else {}
    latest_date = latest.get("date")
    return {
        "as_of": latest_date,
        "promoter_pct": pct(latest, "pr_and_prgrp"),
        "public_pct": pct(latest, "public_val"),
        "employee_trust_pct": pct(latest, "employeeTrusts"),
        "previous_as_of": previous.get("date"),
        "previous_promoter_pct": pct(previous, "pr_and_prgrp"),
        "previous_public_pct": pct(previous, "public_val"),
        "promoter_change_pp": (
            round(pct(latest, "pr_and_prgrp") - pct(previous, "pr_and_prgrp"), 4)
            if pct(latest, "pr_and_prgrp") is not None and pct(previous, "pr_and_prgrp") is not None else None
        ),
        "public_change_pp": (
            round(pct(latest, "public_val") - pct(previous, "public_val"), 4)
            if pct(latest, "public_val") is not None and pct(previous, "public_val") is not None else None
        ),
        "source": "NSE India Corporate Filings · Shareholding Pattern",
    }


def fetch_json(session, url, params, referer):
    response = session.get(url, params=params, headers={"Referer": referer}, timeout=20)
    response.raise_for_status()
    return response.json()


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def main():
    master = load_json(MASTER, {})
    symbols = sorted((master.get("stocks") or {}).keys())
    if not symbols:
        raise SystemExit("Verified NSE F&O stock master is empty; refusing to publish")
    data = load_json(OUT, {"schema_version": 1, "updated_at": None, "next_index": 0, "stocks": {}})
    if data.get("last_batch_date") == dt.datetime.now(dt.timezone.utc).date().isoformat():
        print("Research batch already ran today; no repeat NSE requests")
        return

    start = int(data.get("next_index") or 0) % len(symbols)
    batch = [symbols[(start + offset) % len(symbols)] for offset in range(min(BATCH_SIZE, len(symbols)))]
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Cache-Control": "no-cache",
    })
    session.get("https://www.nseindia.com", timeout=20).raise_for_status()
    time.sleep(PAUSE_SECONDS)
    stocks = data.setdefault("stocks", {})
    success = 0
    for symbol in batch:
        page = "https://www.nseindia.com/get-quotes/equity?symbol=" + symbol
        try:
            quote = fetch_json(session, BASE + "/quote-equity", {"symbol": symbol}, page)
            time.sleep(PAUSE_SECONDS)
            trade = fetch_json(session, BASE + "/quote-equity", {"symbol": symbol, "section": "trade_info"}, page)
            time.sleep(PAUSE_SECONDS)
            shareholding = fetch_json(
                session, BASE + "/corporate-share-holdings-master",
                {"index": "equities", "symbol": symbol},
                "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern?symbol=" + symbol + "&tabIndex=equity",
            )
            parsed = parse_company_quote(quote, trade)
            ownership = parse_shareholding(shareholding)
            if not parsed.get("company_name") and not parsed.get("price") and not ownership:
                raise ValueError("NSE returned no usable company, quote, or shareholding fields")
            old = stocks.get(symbol) if isinstance(stocks.get(symbol), dict) else {}
            merged = dict(old)
            for key, value in parsed.items():
                if value is not None:
                    merged[key] = value
            if ownership:
                merged["shareholding"] = ownership
            merged["checked_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            stocks[symbol] = merged
            success += 1
            print(f"{symbol}: updated company/quote" + (" + shareholding" if ownership else " · shareholding unavailable"))
        except Exception as exc:
            print(f"{symbol}: unavailable ({str(exc)[:180]}); previous cache retained")
        time.sleep(PAUSE_SECONDS)

    data["schema_version"] = 1
    data["universe_count"] = len(symbols)
    data["last_batch_date"] = dt.datetime.now(dt.timezone.utc).date().isoformat()
    data["next_index"] = (start + len(batch)) % len(symbols)
    data["last_batch"] = {"symbols": batch, "success": success, "attempted": len(batch)}
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    data["source_note"] = (
        "NSE public quote-equity and quarterly shareholding filings. "
        "FII/DII breakdown, business description, valuation ratios and financial statements "
        "are intentionally not inferred from aggregate promoter/public data."
    )
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved {success}/{len(batch)} symbols; cursor {start} -> {data['next_index']} of {len(symbols)}")


if __name__ == "__main__":
    main()
