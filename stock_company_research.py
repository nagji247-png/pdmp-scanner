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

from nse_xbrl import filing_xml_url, parse_financial_results_comparison, parse_shareholding_xbrl
from nse_integrated_xbrl import parse_integrated_financial_xbrl
from urllib.parse import urlparse

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


def filing_sort_key(row):
    raw = str(row.get("broadcastDate") or row.get("broadcast_Date") or row.get("broadcastTime") or row.get("date") or row.get("filingDate") or row.get("qe_Date") or row.get("quarterEndDate") or "")
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y", "%d-%b-%y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            # Keep the time component so same-day revised filings are ordered
            # by their actual broadcast timestamp, not API row order.
            return dt.datetime.strptime(raw, fmt)
        except ValueError:
            pass
    return dt.datetime.min


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
        "quote_timestamp": payload.get("timestamp") or info.get("lastUpdateTime") or price.get("lastUpdateTime") or payload.get("lastUpdateTime"),
        "quote_source": "NSE India public quote-equity API",
        "market_cap_source": "NSE India public quote-equity trade_info API" if market_cap is not None else None,
    }


def parse_shareholding(payload):
    if not isinstance(payload, list) or not payload:
        return None
    rows = [row for row in payload if isinstance(row, dict) and row.get("date")]
    def filing_date(row):
        for fmt in ("%d-%b-%Y", "%d-%b-%y"):
            try:
                return dt.datetime.strptime(str(row.get("date")), fmt).date()
            except ValueError:
                pass
        return dt.date.min
    rows.sort(key=filing_date, reverse=True)
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


def seed_nse_session(session):
    """Refresh ordinary NSE session cookies before retrying protected endpoints.

    This does not bypass Akamai challenges or use private credentials. If NSE
    requires a browser-issued challenge cookie, the request remains unavailable.
    """
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache",
    })
    session.get("https://www.nseindia.com", timeout=20)
    time.sleep(PAUSE_SECONDS)
    # NSE's own public client seeds this market-data page as well as the home page.
    session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=20)
    time.sleep(PAUSE_SECONDS)


def fetch_json(session, url, params, referer):
    last_response = None
    for attempt in range(3):
        response = session.get(url, params=params, headers={"Referer": referer}, timeout=25)
        last_response = response
        if response.status_code in (401, 403, 500) and attempt < 2:
            seed_nse_session(session)
            continue
        response.raise_for_status()
        return response.json()
    last_response.raise_for_status()


def fetch_archive_xml(session, url, referer):
    """Fetch a verified NSE XBRL archive URL with the same seeded session."""
    last_response = None
    for attempt in range(3):
        response = session.get(url, headers={"Referer": referer}, timeout=45)
        last_response = response
        if response.status_code in (401, 403, 500) and attempt < 2:
            seed_nse_session(session)
            continue
        response.raise_for_status()
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "html" in content_type or response.content[:100].lstrip().lower().startswith((b"<!doctype html", b"<html")):
            raise ValueError("NSE archive returned an HTML challenge/page instead of XBRL XML")
        return response.content
    last_response.raise_for_status()


def latest_integrated_filing(payload):
    """Return the newest filing row with a trusted NSE archive XBRL URL."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        # Only accept an explicit XBRL XML field. A generic attachmentFile
        # may point to a PDF/HTML document and must never be sent to the XML parser.
        url = row.get("xbrl") or row.get("xbrlFile")
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        parsed_url = urlparse(url)
        host = parsed_url.hostname or ""
        path = parsed_url.path.lower()
        if host not in ("nsearchives.nseindia.com", "www.nseindia.com", "nseindia.com"):
            continue
        if "/corporate/xbrl/" not in path or not path.endswith(".xml"):
            continue
        stamp = str(row.get("broadcastDate") or row.get("broadcast_Date") or row.get("broadcastTime") or row.get("date") or row.get("qe_Date") or "")
        candidates.append((filing_sort_key(row), row, url, stamp))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, row, url, stamp = candidates[0]
    return {"row": row, "url": url, "sort_date": stamp}


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def parsed_name_fallback(payload, symbol):
    info = payload.get("info") or payload.get("metadata") or {}
    return info.get("companyName") or payload.get("companyName") or symbol


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
    seed_nse_session(session)
    stocks = data.setdefault("stocks", {})
    success = 0
    for symbol in batch:
        page = "https://www.nseindia.com/get-quotes/equity?symbol=" + symbol
        try:
            quote = fetch_json(session, BASE + "/quote-equity", {"symbol": symbol}, page)
            time.sleep(PAUSE_SECONDS)
            trade = fetch_json(session, BASE + "/quote-equity", {"symbol": symbol, "section": "trade_info"}, page)
            time.sleep(PAUSE_SECONDS)
            financial_payload = fetch_json(
                session, BASE + "/results-comparision", {"index": "equities", "symbol": symbol},
                "https://www.nseindia.com/companies-listing/corporate-filings-financial-results?symbol=" + symbol,
            )
            financials = parse_financial_results_comparison(financial_payload)
            time.sleep(PAUSE_SECONDS)
            integrated_financials = None
            issuer = (quote.get("info") or quote.get("metadata") or {}).get("companyName") or parsed_name_fallback(quote, symbol)
            integrated_payload = fetch_json(
                session, BASE + "/integrated-filing-results",
                {"index": "equities", "symbol": symbol, "issuer": issuer,
                 "period_ended": "all", "type": "Integrated Filing- Financials",
                 "page": 1, "size": 10},
                "https://www.nseindia.com/companies-listing/corporate-integrated-filing",
            )
            filing = latest_integrated_filing(integrated_payload)
            if filing:
                xml_content = fetch_archive_xml(
                    session, filing["url"],
                    "https://www.nseindia.com/companies-listing/corporate-integrated-filing",
                )
                parsed_xbrl = parse_integrated_financial_xbrl(xml_content)
                if parsed_xbrl:
                    filing_row = filing["row"]
                    integrated_financials = {
                        "filing": {
                            "quarter_end": filing_row.get("quarterEndDate") or filing_row.get("qe_Date") or filing_row.get("to_date") or filing_row.get("periodEnded"),
                            "broadcast_date": filing_row.get("broadcastDate") or filing_row.get("broadcast_Date") or filing_row.get("broadcastTime"),
                            "audited": filing_row.get("audited"),
                            "consolidated": filing_row.get("consolidated"),
                            "submission_type": filing_row.get("typeOfSubmission") or filing_row.get("type_Sub"),
                            "url": filing["url"],
                        },
                        "parsed": parsed_xbrl,
                    }
                time.sleep(PAUSE_SECONDS)
            time.sleep(PAUSE_SECONDS)
            shareholding = fetch_json(
                session, BASE + "/corporate-share-holdings-master",
                {"index": "equities", "symbol": symbol},
                "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern?symbol=" + symbol + "&tabIndex=equity",
            )
            parsed = parse_company_quote(quote, trade)
            ownership = parse_shareholding(shareholding)
            # Prefer the filed XBRL document for institution-level ownership.
            # The summary endpoint alone exposes only promoter/public roll-ups.
            filings = shareholding if isinstance(shareholding, list) else (
                shareholding.get("data") if isinstance(shareholding, dict) else []
            )
            if isinstance(filings, list):
                dated = [row for row in filings if isinstance(row, dict) and row.get("xbrl")]
                dated.sort(key=filing_sort_key, reverse=True)
                if dated:
                    filing = dated[0]
                    xbrl_url = filing_xml_url(filing)
                    if xbrl_url:
                        xml_content = fetch_archive_xml(
                            session, xbrl_url,
                            "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern",
                        )
                        xbrl_ownership = parse_shareholding_xbrl(xml_content)
                        if xbrl_ownership:
                            ownership = dict(ownership or {})
                            ownership.update(xbrl_ownership)
                            ownership["as_of"] = filing.get("date") or ownership.get("as_of")
                            ownership["filing_url"] = xbrl_url
                            ownership["filing_type"] = "NSE SHP XBRL"
                        time.sleep(PAUSE_SECONDS)
            if not parsed.get("company_name") and not parsed.get("price") and not ownership and not integrated_financials:
                raise ValueError("NSE returned no usable company, quote, or shareholding fields")
            old = stocks.get(symbol) if isinstance(stocks.get(symbol), dict) else {}
            merged = dict(old)
            for key, value in parsed.items():
                if value is not None:
                    merged[key] = value
            if ownership:
                merged["shareholding"] = ownership
            if financials:
                merged["financials"] = financials
            if integrated_financials:
                merged["integrated_financials"] = integrated_financials
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
        "NSE public quote-equity, quarterly results comparison, Integrated Filing XBRL and Shareholding Pattern XBRL where available. "
        "Promoter/FII/DII/Public values are parsed from filed XBRL facts; unavailable facts "
        "remain missing. Integrated Filing parser currently maps a conservative subset; sector-specific taxonomy validation is ongoing."
    )
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved {success}/{len(batch)} symbols; cursor {start} -> {data['next_index']} of {len(symbols)}")


if __name__ == "__main__":
    main()
