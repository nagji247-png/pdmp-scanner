#!/usr/bin/env python3
"""Research-only next-session option premium EOD OHLC audit from NSE UDiFF.

Matches the exact option contracts selected by the existing ATM +/-5/+/-10
OI study to the next official NSE session's contract OHLC. Daily high/low
shows the session's price range, NOT which level traded first. Never changes
production scores or dashboard data.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import requests

from atm_option_window_backtest import build_report

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TRINETRA-Research-Audit/1.0)",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Referer": "https://www.nseindia.com/all-reports-derivatives",
}
SYMBOLS = {"NIFTY", "BANKNIFTY"}
WINDOWS = ("atm_plus_minus_5", "atm_plus_minus_10")


def number(value, field, allow_zero=True):
    text = str(value if value is not None else "").strip().replace(",", "")
    try:
        out = float(text)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"invalid {field}: {text!r}")
    if not math.isfinite(out) or out < 0 or (not allow_zero and out == 0):
        raise ValueError(f"out-of-range {field}: {text!r}")
    return out


def fetch_bhavcopy(day, session):
    stamp = day.replace("-", "")
    filename = f"BhavCopy_NSE_FO_0_0_0_{stamp}_F_0000.csv.zip"
    errors = []
    for host in ("https://archives.nseindia.com/content/fo/",
                 "https://nsearchives.nseindia.com/content/fo/"):
        url = host + filename
        try:
            response = session.get(url, headers=HEADERS, timeout=(15, 60))
            if response.status_code == 200 and response.content:
                with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                    names = [n for n in zf.namelist()
                             if n.lower().endswith(".csv") and not n.startswith("__MACOSX/")]
                    if len(names) != 1:
                        raise ValueError(f"unexpected CSV members: {names}")
                    with zf.open(names[0]) as raw:
                        rows = list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")))
                return rows, url, hashlib.sha256(response.content).hexdigest()
            errors.append(f"{url}: HTTP {response.status_code}")
        except Exception as exc:
            errors.append(f"{url}: {str(exc)[:180]}")
    raise RuntimeError("official NSE UDiFF fetch failed: " + " | ".join(errors))


def extract_contracts(rows, day, needed):
    found = {}
    for row in rows:
        if str(row.get("FinInstrmTp") or "").strip().upper() != "IDO":
            continue
        symbol = str(row.get("TckrSymb") or "").strip().upper()
        if symbol not in SYMBOLS:
            continue
        biz = str(row.get("BizDt") or "").strip()[:10]
        if biz != day:
            continue
        expiry = str(row.get("XpryDt") or "").strip()[:10]
        side = str(row.get("OptnTp") or "").strip().upper()
        try:
            strike = round(number(row.get("StrkPric"), "StrkPric", False), 4)
        except ValueError:
            continue
        key = (symbol, expiry, strike, side)
        if key not in needed:
            continue
        if key in found:
            raise ValueError(f"duplicate exact contract row for {day}: {key}")
        found[key] = {
            "open": number(row.get("OpnPric"), "OpnPric"),
            "high": number(row.get("HghPric"), "HghPric"),
            "low": number(row.get("LwPric"), "LwPric"),
            "close": number(row.get("ClsPric"), "ClsPric"),
            "volume": number(row.get("TtlTradgVol"), "TtlTradgVol"),
            "open_interest": number(row.get("OpnIntrst"), "OpnIntrst"),
        }
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oi-archive", default="nse_index_option_oi.json")
    parser.add_argument("--close-archive", default="nse_index_close_archive.json")
    parser.add_argument("--csv-out", default="nse_next_session_option_ohlc_rows.csv")
    parser.add_argument("--json-out", default="nse_next_session_option_ohlc_summary.json")
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.delay_seconds < 2 or not math.isfinite(args.delay_seconds):
        parser.error("--delay-seconds must be at least 2")

    oi = json.loads(Path(args.oi_archive).read_text(encoding="utf-8"))
    closes = json.loads(Path(args.close_archive).read_text(encoding="utf-8"))
    report = build_report(oi, closes)

    # One record per unique next-session date, with exact contracts required by
    # the existing signal report. Window duplicates are retained in output rows.
    requests_by_day = defaultdict(dict)
    expected_rows = []
    for symbol, asset in report["by_asset"].items():
        if symbol not in SYMBOLS:
            continue
        for obs in asset["observations"]:
            signal_day, next_day = obs["signal_date"], obs["next_session_date"]
            for window in WINDOWS:
                result = obs["windows"].get(window, {})
                if not result.get("available"):
                    continue
                signal = result.get("signal")
                for contract in result.get("contract_details", []):
                    key = (symbol, contract["expiry"], round(float(contract["strike"]), 4),
                           str(contract["side"]).upper())
                    requests_by_day[next_day][key] = True
                    expected_rows.append({
                        "index": symbol, "signal_date": signal_day,
                        "next_session_date": next_day, "window": window,
                        "oi_signal": signal, "expiry": key[1], "strike": key[2],
                        "side": key[3], "distance_from_atm_steps": contract.get("distance_from_atm_steps"),
                        "distance_band": contract.get("distance_band"),
                        "classified_in_oi_signal": bool(contract.get("classified")),
                        "contract_oi_direction": contract.get("direction"),
                        "signal_day_premium_close": float(contract["current_premium"]),
                        "signal_day_oi_change": contract.get("oi_change"),
                    })

    session = requests.Session()
    cache = {}
    fetch_log = []
    dates = sorted(requests_by_day)
    for i, day in enumerate(dates):
        rows, url, digest = fetch_bhavcopy(day, session)
        found = extract_contracts(rows, day, set(requests_by_day[day]))
        cache[day] = found
        fetch_log.append({"date": day, "source_url": url, "sha256": digest,
                          "requested_unique_contracts": len(requests_by_day[day]),
                          "matched_contracts": len(found),
                          "missing_contracts": len(requests_by_day[day]) - len(found)})
        if i + 1 < len(dates):
            time.sleep(args.delay_seconds)

    output = []
    missing = []
    for item in expected_rows:
        key = (item["index"], item["expiry"], item["strike"], item["side"])
        market = cache[item["next_session_date"]].get(key)
        if market is None:
            missing.append({**item, "missing_reason": "exact_contract_not_found_in_next_session_bhavcopy"})
            continue
        ref = item["signal_day_premium_close"]
        row = {**item, **{f"next_session_{k}": v for k, v in market.items()}}
        row["open_change_pct_from_signal_close"] = round(100 * (market["open"] / ref - 1), 4) if ref else None
        row["high_change_pct_from_signal_close"] = round(100 * (market["high"] / ref - 1), 4) if ref else None
        row["low_change_pct_from_signal_close"] = round(100 * (market["low"] / ref - 1), 4) if ref else None
        row["close_change_pct_from_signal_close"] = round(100 * (market["close"] / ref - 1), 4) if ref else None
        output.append(row)

    fields = list(dict.fromkeys(k for row in output + missing for k in row))
    with Path(args.csv_out).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output + missing)

    summary = {
        "status": "exploratory_only",
        "source": "NSE official F&O UDiFF Common Bhavcopy Final",
        "method": "Exact same index, expiry, strike and CE/PE contract matched from signal-day OI report to next official session bhavcopy",
        "scope": "NIFTY and BANKNIFTY; ATM +/-5 and +/-10 windows; next-session option daily OHLC",
        "next_session_dates_requested": len(dates),
        "expected_contract_window_rows": len(expected_rows),
        "matched_contract_window_rows": len(output),
        "missing_contract_window_rows": len(missing),
        "match_coverage_pct": round(100 * len(output) / len(expected_rows), 2) if expected_rows else None,
        "daily_high_low_limit": "OHLC gives daily range only; it cannot establish whether a premium target or stop was reached first intraday",
        "production_score_changed": False,
        "eligible_for_live_score": False,
        "fetch_log": fetch_log,
        "missing_contracts": missing,
    }
    Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("fetch_log", "missing_contracts")}, indent=2))


if __name__ == "__main__":
    main()
