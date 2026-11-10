#!/usr/bin/env python3
"""Read-only verification of official NIFTY 50 daily OHLC against NSE participant OI dates.

The public Nifty Indices historical-data page exposes daily Date/Open/High/Low/Close
records. Its backing POST method is undocumented; this client is isolated research
code and does not change the production backtest or any live score.
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
HISTORICAL_PAGE_URL = "https://www.niftyindices.com/reports/historical-data"
OHLC_URL = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
DEFAULT_INDEX_NAME = "NIFTY 50"
REQUEST_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.niftyindices.com",
    "Referer": HISTORICAL_PAGE_URL,
    "User-Agent": "Mozilla/5.0 (compatible; PDMP-Research/1.0)",
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
    """Parse the ASP.NET response, whose d member is usually a JSON string."""
    if not isinstance(payload, dict) or "d" not in payload:
        raise ValueError("official OHLC response is missing the d field")
    raw = payload["d"]
    if raw is None or raw is False:
        return []
    if isinstance(raw, str):
        if raw.strip().lower() in ("", "false", "[]"):
            return []
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("official OHLC d field is not valid JSON") from exc
    if not isinstance(raw, list):
        raise ValueError("official OHLC d field is not a list")
    if any(not isinstance(row, dict) for row in raw):
        raise ValueError("official OHLC response contains a non-object row")
    return raw


def _parse_source_date(value: object) -> dt.date:
    if not isinstance(value, str):
        raise ValueError("official OHLC row has no valid date")
    for fmt in ("%d %b %Y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported official OHLC date: {value!r}")


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
    """Normalize official rows and reject duplicate, out-of-range or invalid OHLC."""
    prices: dict[str, dict[str, float]] = {}
    for position, row in enumerate(rows, start=1):
        source_name = row.get("INDEX_NAME") or row.get("Index Name") or row.get("indexName")
        if source_name and str(source_name).strip().upper() != index_name.strip().upper():
            raise ValueError(
                f"row {position}: index name mismatch {source_name!r} != {index_name!r}"
            )
        raw_date = (
            row.get("HistoricalDate")
            or row.get("DATE")
            or row.get("Date")
            or row.get("date")
        )
        session_date = _parse_source_date(raw_date)
        if session_date < start or session_date > end:
            raise ValueError(f"row {position}: date outside requested range: {session_date}")
        date_key = session_date.isoformat()
        if date_key in prices:
            raise ValueError(f"duplicate official OHLC date: {date_key}")
        values = {
            "open": _positive_finite(row.get("OPEN", row.get("Open")), "open"),
            "high": _positive_finite(row.get("HIGH", row.get("High")), "high"),
            "low": _positive_finite(row.get("LOW", row.get("Low")), "low"),
            "close": _positive_finite(row.get("CLOSE", row.get("Close")), "close"),
        }
        if (
            values["high"] < values["low"]
            or not values["low"] <= values["open"] <= values["high"]
            or not values["low"] <= values["close"] <= values["high"]
        ):
            raise ValueError(f"row {position}: inconsistent OHLC range for {date_key}")
        prices[date_key] = values
    if not prices:
        raise ValueError("official NIFTY Indices endpoint returned no OHLC rows")
    return dict(sorted(prices.items()))


def fetch_official_ohlc(
    index_name: str,
    start: dt.date,
    end: dt.date,
    session=None,
    sleep_fn=time.sleep,
) -> tuple[dict[str, dict[str, float]], int]:
    """Fetch the public Nifty Indices historical OHLC endpoint in <=365-day chunks."""
    client = session or requests.Session()
    page = client.get(HISTORICAL_PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    page.raise_for_status()  # seed the same-site session before the data request

    chunks = list(date_chunks(start, end, max_days=365))
    combined: dict[str, dict[str, float]] = {}
    for number, (chunk_start, chunk_end) in enumerate(chunks):
        cinfo = (
            f"{{'name':'{index_name}','startDate':'{chunk_start.strftime('%d %b %Y')}',"
            f"'endDate':'{chunk_end.strftime('%d %b %Y')}',"
            f"'indexName':'{index_name}'}}"
        )
        response = client.post(
            OHLC_URL,
            data=json.dumps({"cinfo": cinfo}),
            headers=REQUEST_HEADERS,
            timeout=45,
        )
        response.raise_for_status()
        rows = parse_api_response(response.json())
        normalized = normalize_ohlc_rows(rows, index_name, chunk_start, chunk_end)
        overlap = set(combined).intersection(normalized)
        if overlap:
            raise ValueError("duplicate official OHLC dates across chunks: " + ", ".join(sorted(overlap)))
        combined.update(normalized)
        if number + 1 < len(chunks):
            sleep_fn(0.75)

    if not combined:
        raise ValueError("official NIFTY Indices endpoint returned no OHLC history")
    return dict(sorted(combined.items())), 1 + len(chunks)


def build_alignment_report(
    oi_dates: list[str],
    official_prices: dict[str, dict[str, float]],
    start: dt.date,
    end: dt.date,
) -> dict:
    """Compare the OI trading dates with official price sessions without filling gaps."""
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
        "source": "NSE Indices official Historical Index Data portal",
        "source_page": HISTORICAL_PAGE_URL,
        "source_endpoint": OHLC_URL,
        "source_note": (
            "The official page exposes daily Date/Open/High/Low/Close CSV data. "
            "This isolated verifier uses the page's undocumented backing POST method; "
            "it does not alter the production backtest or live scores."
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
    parser.add_argument("--out", type=Path, default=ROOT / "official_niftyindices_ohlc_audit.json")
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
        raise SystemExit("official NIFTY 50 OHLC date alignment is incomplete")


if __name__ == "__main__":
    main()
