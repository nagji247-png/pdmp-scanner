#!/usr/bin/env python3
"""Read-only verification of official NSE NIFTY 50 OHLC against participant OI dates.

This isolated research verifier uses NSE's public historical-index JSON endpoint.
It does not change the production backtest, data archive, dashboard or live score.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
from pathlib import Path

import requests

import backtest_participant_oi as participant_backtest

ROOT = Path(__file__).resolve().parent
DEFAULT_ARCHIVE = ROOT / "participant_oi_history.json"
COOKIE_SEED_URL = "https://www.nseindia.com/option-chain"
HISTORICAL_PAGE_URL = "https://www.nseindia.com/reports-indices-historical-index-data"
OHLC_URL = "https://www.nseindia.com/api/historicalOR/indicesHistory"
DEFAULT_INDEX_NAME = "NIFTY 50"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Referer": HISTORICAL_PAGE_URL,
}


def date_chunks(start: dt.date, end: dt.date, max_days: int = 365):
    """Yield contiguous inclusive date ranges no longer than max_days."""
    if not isinstance(start, dt.date) or not isinstance(end, dt.date):
        raise TypeError("start and end must be dates")
    if start > end:
        raise ValueError("start date must not be after end date")
    if not isinstance(max_days, int) or isinstance(max_days, bool) or max_days < 1:
        raise ValueError("max_days must be a positive integer")
    current = start
    while current <= end:
        chunk_end = min(current + dt.timedelta(days=max_days - 1), end)
        yield current, chunk_end
        current = chunk_end + dt.timedelta(days=1)


def parse_api_response(payload: object) -> list[dict]:
    """Parse the NSE historical index response's data array."""
    if not isinstance(payload, dict) or "data" not in payload:
        raise ValueError("NSE historical index response is missing the data field")
    rows = payload["data"]
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError("NSE historical index data field is not a list")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("NSE historical index response contains a non-object row")
    return rows


def _parse_source_date(value: object) -> dt.date:
    if not isinstance(value, str):
        raise ValueError("NSE historical index row has no valid EOD_TIMESTAMP")
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value.strip().upper(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported NSE historical index date: {value!r}")


def _positive_finite(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field} value: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"invalid {field} value: {value!r}")
    return number


def normalize_ohlc_rows(
    rows: list[dict],
    index_name: str,
    start: dt.date,
    end: dt.date,
) -> dict[str, dict[str, float]]:
    """Normalize NSE rows and reject duplicate, out-of-range or invalid OHLC."""
    prices: dict[str, dict[str, float]] = {}
    for position, row in enumerate(rows, start=1):
        source_name = row.get("EOD_INDEX_NAME") or row.get("indexType")
        if source_name and str(source_name).strip().upper() != index_name.strip().upper():
            raise ValueError(
                f"row {position}: index name mismatch {source_name!r} != {index_name!r}"
            )
        session_date = _parse_source_date(row.get("EOD_TIMESTAMP"))
        if session_date < start or session_date > end:
            raise ValueError(f"row {position}: date outside requested range: {session_date}")
        date_key = session_date.isoformat()
        if date_key in prices:
            raise ValueError(f"duplicate official NSE OHLC date: {date_key}")
        values = {
            "open": _positive_finite(row.get("EOD_OPEN_INDEX_VAL"), "open"),
            "high": _positive_finite(row.get("EOD_HIGH_INDEX_VAL"), "high"),
            "low": _positive_finite(row.get("EOD_LOW_INDEX_VAL"), "low"),
            "close": _positive_finite(row.get("EOD_CLOSE_INDEX_VAL"), "close"),
        }
        if (
            values["high"] < values["low"]
            or not values["low"] <= values["open"] <= values["high"]
            or not values["low"] <= values["close"] <= values["high"]
        ):
            raise ValueError(f"row {position}: inconsistent OHLC range for {date_key}")
        prices[date_key] = values
    if not prices:
        raise ValueError("NSE historical index endpoint returned no OHLC rows")
    return dict(sorted(prices.items()))


def fetch_official_ohlc(
    index_name: str,
    start: dt.date,
    end: dt.date,
    session=None,
    sleep_fn=time.sleep,
) -> tuple[dict[str, dict[str, float]], int]:
    """Fetch NSE historical index OHLC in contiguous <=365-day requests."""
    client = session or requests.Session()
    seed = client.get(COOKIE_SEED_URL, headers=REQUEST_HEADERS, timeout=20)
    seed.raise_for_status()

    chunks = list(date_chunks(start, end, max_days=365))
    combined: dict[str, dict[str, float]] = {}
    sleep_fn(0.75)
    for number, (chunk_start, chunk_end) in enumerate(chunks):
        response = client.get(
            OHLC_URL,
            params={
                "indexType": index_name.upper(),
                "from": chunk_start.strftime("%d-%m-%Y"),
                "to": chunk_end.strftime("%d-%m-%Y"),
                "csv": True,
            },
            headers=REQUEST_HEADERS,
            timeout=45,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            content_type = getattr(response, "headers", {}).get("Content-Type", "unknown")
            body_prefix = getattr(response, "text", "")[:180].replace("\n", " ")
            raise RuntimeError(
                "NSE historical index endpoint returned non-JSON "
                f"(content-type={content_type!r}, body-prefix={body_prefix!r})"
            ) from exc
        rows = parse_api_response(payload)
        normalized = normalize_ohlc_rows(rows, index_name, chunk_start, chunk_end)
        overlap = set(combined).intersection(normalized)
        if overlap:
            raise ValueError("duplicate official NSE OHLC dates across chunks: " + ", ".join(sorted(overlap)))
        combined.update(normalized)
        if number + 1 < len(chunks):
            sleep_fn(0.75)

    if not combined:
        raise ValueError("NSE historical index endpoint returned no OHLC history")
    return dict(sorted(combined.items())), 1 + len(chunks)


def build_alignment_report(
    oi_dates: list[str],
    official_prices: dict[str, dict[str, float]],
    start: dt.date,
    end: dt.date,
) -> dict:
    """Compare OI trading dates with official NSE price sessions without filling gaps."""
    if len(oi_dates) != len(set(oi_dates)):
        raise ValueError("duplicate OI dates supplied to alignment audit")
    in_range_oi = sorted(
        value for value in oi_dates
        if start.isoformat() <= value <= end.isoformat()
    )
    official_dates = sorted(
        value for value in official_prices
        if start.isoformat() <= value <= end.isoformat()
    )
    oi_set, official_set = set(in_range_oi), set(official_dates)
    matched = sorted(oi_set & official_set)
    missing_oi = sorted(official_set - oi_set)
    oi_without_price = sorted(oi_set - official_set)
    match_pct = round(len(matched) / len(in_range_oi) * 100.0, 2) if in_range_oi else 0.0
    exact_session_match = not missing_oi and not oi_without_price and bool(official_dates)
    return {
        "oi_sessions_in_requested_range": len(in_range_oi),
        "official_ohlc_sessions": len(official_dates),
        "matched_sessions": len(matched),
        "oi_dates_without_official_price": len(oi_without_price),
        "oi_dates_without_official_price_sample": oi_without_price[:20],
        "official_sessions_missing_from_oi": len(missing_oi),
        "official_sessions_missing_from_oi_sample": missing_oi[:20],
        "oi_to_official_price_match_pct": match_pct,
        "aligned_first_date": matched[0] if matched else None,
        "aligned_last_date": matched[-1] if matched else None,
        "exact_session_calendar_match": exact_session_match,
    }


def run_audit(
    archive_path: Path = DEFAULT_ARCHIVE,
    index_name: str = DEFAULT_INDEX_NAME,
    start: dt.date | None = None,
    end: dt.date | None = None,
    session=None,
    sleep_fn=time.sleep,
) -> dict:
    payload = json.loads(archive_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("participant OI archive root must be an object")
    oi_records, archive_validation = participant_backtest.validate_oi_records(
        payload.get("records", [])
    )
    first = dt.date.fromisoformat(oi_records[0]["date"])
    last = dt.date.fromisoformat(oi_records[-1]["date"])
    start = start or first
    end = end or last
    if start > end:
        raise ValueError("start date must not be after end date")

    official_prices, provider_calls = fetch_official_ohlc(
        index_name, start, end, session=session, sleep_fn=sleep_fn
    )
    alignment = build_alignment_report(
        [row["date"] for row in oi_records], official_prices, start, end
    )
    status = "validated" if alignment["exact_session_calendar_match"] else "incomplete"
    return {
        "schema_version": 1,
        "status": status,
        "source": "NSE India official Historical Index Data",
        "source_page": HISTORICAL_PAGE_URL,
        "source_endpoint": OHLC_URL,
        "source_note": (
            "The official NSE historical-index page exposes downloadable daily "
            "Date/Open/High/Low/Close data. This verifier uses the page's public "
            "historical-index JSON endpoint with a standard cookie-backed session; "
            "it does not bypass access controls or alter production scores."
        ),
        "index_name": index_name,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "archive_validation": archive_validation,
        "alignment": alignment,
        "official_ohlc_sample": {
            "first": next(iter(official_prices.items())),
            "last": next(reversed(official_prices.items())),
        },
        "provider_calls": provider_calls,
        "production_backtest_changed": False,
        "live_score_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME)
    parser.add_argument("--start", type=dt.date.fromisoformat)
    parser.add_argument("--end", type=dt.date.fromisoformat)
    parser.add_argument("--out", type=Path, default=ROOT / "official_nse_index_ohlc_audit.json")
    args = parser.parse_args()

    report = run_audit(
        archive_path=args.archive,
        index_name=args.index_name,
        start=args.start,
        end=args.end,
    )
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "index_name": report["index_name"],
        "oi_sessions": report["alignment"]["oi_sessions_in_requested_range"],
        "official_ohlc_sessions": report["alignment"]["official_ohlc_sessions"],
        "matched_sessions": report["alignment"]["matched_sessions"],
        "oi_dates_without_official_price": report["alignment"]["oi_dates_without_official_price"],
        "official_sessions_missing_from_oi": report["alignment"]["official_sessions_missing_from_oi"],
        "match_pct": report["alignment"]["oi_to_official_price_match_pct"],
        "provider_calls": report["provider_calls"],
        "production_backtest_changed": False,
        "live_score_changed": False,
    }, ensure_ascii=False))
    if report["status"] != "validated":
        raise SystemExit("official NSE NIFTY 50 OHLC date alignment is incomplete")


if __name__ == "__main__":
    main()
