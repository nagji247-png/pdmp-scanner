#!/usr/bin/env python3
"""Audit point-in-time News + Google Trends + NSE participant OI snapshots.

This is a read-only research gate. It never fetches market data and never assigns
or changes a live score.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
IST = ZoneInfo("Asia/Kolkata")
INDEXES = ("NIFTY", "SENSEX", "BANKNIFTY")
PARTICIPANTS = ("FII", "DII", "PRO", "CLIENT")
OI_FIELDS = (
    "future_index_long", "future_index_short",
    "index_call_long", "index_call_short",
    "index_put_long", "index_put_short",
    "future_stock_long", "future_stock_short",
    "stock_call_long", "stock_call_short",
    "stock_put_long", "stock_put_short",
)
TRENDS_FIELDS = (
    "crowd_bull_pct", "bull_score_pct", "bear_score_pct", "neutral_score_pct",
)


def finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def market_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def ist_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(IST)


def same_ist_date(value: object, expected_date: str) -> bool:
    parsed = ist_datetime(value)
    return parsed is not None and parsed.date().isoformat() == expected_date


TRENDS_SLOTS = {"0915": "09:15", "1100": "11:00", "1300": "13:00", "1900": "19:00"}


def trends_slot_evidence_complete(value: object, expected_date: str) -> bool:
    """Require four unique, same-session slot observations with validated times."""
    if not isinstance(value, dict) or value.get("date") != expected_date:
        return False
    rows = value.get("slots")
    if not isinstance(rows, list) or len(rows) != len(TRENDS_SLOTS):
        return False
    by_id = {}
    for row in rows:
        if not isinstance(row, dict):
            return False
        slot_id = row.get("id")
        if slot_id not in TRENDS_SLOTS or slot_id in by_id:
            return False
        by_id[slot_id] = row
    if set(by_id) != set(TRENDS_SLOTS):
        return False

    for slot_id, label in TRENDS_SLOTS.items():
        row = by_id[slot_id]
        if row.get("status") != "success" or row.get("time") != label:
            return False
        stamp = ist_datetime(row.get("source_data_time"))
        if stamp is None or stamp.date().isoformat() != expected_date:
            return False
        expected = datetime.combine(
            stamp.date(), time.fromisoformat(label), tzinfo=IST
        )
        observation_lag = (expected - stamp).total_seconds() / 60
        if observation_lag < -15 or observation_lag > 360:
            return False
        if not all(finite_number(row.get(field)) for field in (
            "bull_pct", "bear_pct", "neutral_pct", "crowd_pct"
        )):
            return False
    return True


def captured_after_close(value: object, expected_date: str) -> bool:
    parsed = ist_datetime(value)
    return (
        parsed is not None
        and parsed.date().isoformat() == expected_date
        and parsed.time().replace(tzinfo=None) >= time(20, 0)
    )


def participant_fields_complete(participants: object) -> bool:
    if not isinstance(participants, dict):
        return False
    for group in PARTICIPANTS:
        values = participants.get(group)
        if not isinstance(values, dict):
            return False
        if any(not finite_number(values.get(field)) for field in OI_FIELDS):
            return False
    return True


def assess_snapshot(record: object, oi_previous_dates: dict[str, str]) -> dict:
    if not isinstance(record, dict):
        record = {}

    date = record.get("date")
    valid_date = isinstance(date, str) and market_date(date) == date
    indices = record.get("indices") if isinstance(record.get("indices"), dict) else {}

    closes_complete = bool(valid_date) and all(
        isinstance(indices.get(name), dict)
        and finite_number(indices[name].get("close"))
        and market_date(indices[name].get("close_as_of")) == date
        for name in INDEXES
    )
    news_complete = all(
        isinstance(indices.get(name), dict)
        and finite_number(indices[name].get("experimental_news_score"))
        and isinstance(indices[name].get("experimental_headline_count"), int)
        and indices[name].get("experimental_headline_count", 0) > 0
        for name in INDEXES
    )

    trends = record.get("trends") if isinstance(record.get("trends"), dict) else {}
    trends_valid = trends.get("valid") is True
    trends_fields_complete = all(finite_number(trends.get(field)) for field in TRENDS_FIELDS)
    trends_date_aligned = bool(valid_date) and same_ist_date(
        trends.get("as_of") or trends.get("source_data_time"), date
    )
    trends_slot_evidence_ok = bool(valid_date) and trends_slot_evidence_complete(
        trends.get("daily_slot_evidence"), date
    )
    trends_daily_complete = (
        trends_valid
        and trends.get("daily_complete") is True
        and trends_fields_complete
        and trends_date_aligned
        and trends_slot_evidence_ok
    )

    oi = record.get("participant_oi") if isinstance(record.get("participant_oi"), dict) else {}
    oi_date = oi.get("date")
    oi_history_has_date = bool(valid_date) and date in oi_previous_dates
    oi_snapshot_complete = (
        bool(valid_date)
        and oi_date == date
        and oi_history_has_date
        and participant_fields_complete(oi.get("participants"))
    )
    oi_change_available = bool(valid_date) and bool(oi_previous_dates.get(date))

    eod_capture_valid = bool(valid_date) and captured_after_close(
        record.get("captured_at_utc"), date
    )

    eligible = all((
        closes_complete,
        news_complete,
        trends_daily_complete,
        oi_snapshot_complete,
        oi_change_available,
        eod_capture_valid,
    ))
    return {
        "date": date if valid_date else None,
        "index_closes_complete": closes_complete,
        "index_news_complete": news_complete,
        "trends_valid": trends_valid,
        "trends_daily_complete": trends_daily_complete,
        "trends_slot_evidence_complete": trends_slot_evidence_ok,
        "participant_oi_complete": oi_snapshot_complete,
        "oi_change_available": oi_change_available,
        "eod_capture_valid": eod_capture_valid,
        "complete_for_combined_backtest": eligible,
        "oi_previous_date": oi_previous_dates.get(date) if valid_date else None,
    }


def _archive_dates(records: object) -> tuple[list[str], int, int, int]:
    if not isinstance(records, list):
        return [], 0, 0, 0
    dates = [row.get("date") for row in records if isinstance(row, dict)]
    valid_dates = [value for value in dates if market_date(value) == value]
    duplicate_count = len(valid_dates) - len(set(valid_dates))
    out_of_order = sum(
        1 for left, right in zip(valid_dates, valid_dates[1:]) if right < left
    )
    invalid_count = len(dates) - len(valid_dates)
    return valid_dates, duplicate_count, out_of_order, invalid_count


def validate_archives(
    market_payload: object,
    oi_payload: object,
    min_sessions: int = 120,
    target_sessions: int = 250,
) -> dict:
    if min_sessions < 1 or target_sessions < min_sessions:
        raise ValueError("target_sessions must be >= min_sessions >= 1")

    market_records = (
        market_payload.get("records", [])
        if isinstance(market_payload, dict) else []
    )
    oi_records = (
        oi_payload.get("records", [])
        if isinstance(oi_payload, dict) else []
    )

    market_dates, market_duplicates, market_order_errors, market_invalid = _archive_dates(
        market_records
    )
    oi_dates, oi_duplicates, oi_order_errors, oi_invalid_dates = _archive_dates(oi_records)

    oi_valid_rows = 0
    oi_invalid_rows = 0
    for row in oi_records if isinstance(oi_records, list) else []:
        if not isinstance(row, dict) or not participant_fields_complete(row.get("participants")):
            oi_invalid_rows += 1
        else:
            oi_valid_rows += 1

    oi_previous_dates = {}
    previous = None
    for date in oi_dates:
        if date not in oi_previous_dates:
            oi_previous_dates[date] = previous
        previous = date

    assessments = [
        assess_snapshot(row, oi_previous_dates)
        for row in market_records if isinstance(row, dict)
    ]
    eligible_dates = [
        row["date"] for row in assessments
        if row.get("complete_for_combined_backtest")
    ]
    incomplete_trends = sum(
        1 for row in assessments if not row.get("trends_daily_complete")
    )
    incomplete_trends_slot_evidence = sum(
        1 for row in assessments if not row.get("trends_slot_evidence_complete")
    )
    missing_news = sum(
        1 for row in assessments if not row.get("index_news_complete")
    )
    missing_oi = sum(
        1 for row in assessments
        if not row.get("participant_oi_complete") or not row.get("oi_change_available")
    )
    invalid_closes = sum(
        1 for row in assessments if not row.get("index_closes_complete")
    )
    invalid_capture = sum(
        1 for row in assessments if not row.get("eod_capture_valid")
    )

    integrity_errors = []
    if market_duplicates:
        integrity_errors.append(f"duplicate market snapshot dates: {market_duplicates}")
    if market_order_errors:
        integrity_errors.append(f"out-of-order market snapshot rows: {market_order_errors}")
    if market_invalid:
        integrity_errors.append(f"invalid market snapshot dates: {market_invalid}")
    if oi_duplicates:
        integrity_errors.append(f"duplicate OI dates: {oi_duplicates}")
    if oi_order_errors:
        integrity_errors.append(f"out-of-order OI rows: {oi_order_errors}")
    if oi_invalid_dates or oi_invalid_rows:
        integrity_errors.append(
            f"invalid OI rows: dates={oi_invalid_dates}, participant fields={oi_invalid_rows}"
        )

    if integrity_errors:
        status = "invalid_archive"
        reason = "; ".join(integrity_errors)
    elif len(eligible_dates) >= min_sessions:
        status = "ready_for_exploratory_backtest"
        reason = "Minimum complete point-in-time sessions reached; run chronological holdout."
    else:
        status = "insufficient_data"
        reason = (
            f"{len(eligible_dates)} complete sessions; "
            f"{min_sessions} required before combined-signal testing."
        )

    return {
        "schema_version": 1,
        "status": status,
        "reason": reason,
        "market_signal_records": len(market_records) if isinstance(market_records, list) else 0,
        "market_signal_first_date": min(market_dates) if market_dates else None,
        "market_signal_last_date": max(market_dates) if market_dates else None,
        "market_signal_duplicate_dates": market_duplicates,
        "market_signal_out_of_order_rows": market_order_errors,
        "market_signal_invalid_dates": market_invalid,
        "oi_archive_records": len(oi_records) if isinstance(oi_records, list) else 0,
        "oi_valid_rows": oi_valid_rows,
        "oi_invalid_rows": oi_invalid_dates + oi_invalid_rows,
        "oi_duplicate_dates": oi_duplicates,
        "oi_out_of_order_rows": oi_order_errors,
        "oi_first_date": min(oi_dates) if oi_dates else None,
        "oi_last_date": max(oi_dates) if oi_dates else None,
        "combined_backtest_eligible_sessions": len(eligible_dates),
        "minimum_required_sessions": min_sessions,
        "target_sessions": target_sessions,
        "target_met": len(eligible_dates) >= target_sessions,
        "incomplete_trends_sessions": incomplete_trends,
        "sessions_with_incomplete_trends_slot_evidence": incomplete_trends_slot_evidence,
        "sessions_missing_index_news": missing_news,
        "sessions_missing_or_unpaired_oi": missing_oi,
        "sessions_with_invalid_index_closes": invalid_closes,
        "sessions_without_valid_after_close_capture": invalid_capture,
        "eligible_dates": eligible_dates,
        "recent_snapshot_quality": assessments[-5:],
        "score_changed": False,
        "eligible_for_live_score": False,
        "source_note": (
            "Only point-in-time snapshots are eligible. Intraday history.csv is not a substitute. "
            "NSE participant OI is aggregate Index F&O data, not independent OI for each index."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-history", default=str(ROOT / "market_signal_history.json"))
    parser.add_argument("--oi-history", default=str(ROOT / "participant_oi_history.json"))
    parser.add_argument("--min-sessions", type=int, default=120)
    parser.add_argument("--target-sessions", type=int, default=250)
    args = parser.parse_args()

    market_payload = json.loads(Path(args.market_history).read_text(encoding="utf-8"))
    oi_payload = json.loads(Path(args.oi_history).read_text(encoding="utf-8"))
    report = validate_archives(
        market_payload, oi_payload,
        min_sessions=args.min_sessions,
        target_sessions=args.target_sessions,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## Combined-signal archive readiness\n\n")
            summary.write(f"- Status: **{report['status']}**\n")
            summary.write(f"- Complete sessions: **{report['combined_backtest_eligible_sessions']} / {report['minimum_required_sessions']} required**\n")
            summary.write(f"- OI archive: **{report['oi_valid_rows']} valid / {report['oi_archive_records']} records**\n")
            summary.write(f"- Incomplete Trends sessions: **{report['incomplete_trends_sessions']}**\n")
            summary.write(f"- Reason: {report['reason']}\n")
            summary.write("- Live score changed: **No**\n")

    return 1 if report["status"] == "invalid_archive" else 0


if __name__ == "__main__":
    raise SystemExit(main())
