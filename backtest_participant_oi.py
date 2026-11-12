#!/usr/bin/env python3
"""Exploratory point-in-time NSE participant OI diagnostics; never changes live scores.

NSE participant OI is aggregate Index F&O data, not separate NIFTY/SENSEX/BANKNIFTY OI.
The same participant features are tested against each index's own daily OHLC series.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "participant_oi_history.json"
OUTPUT = ROOT / "participant_oi_backtest.json"
INDEXES = {"NIFTY": "^NSEI", "SENSEX": "^BSESN", "BANKNIFTY": "^NSEBANK"}
HORIZONS = (1, 3, 5)
GROUPS = ("FII", "DII", "PRO", "CLIENT")
FIELDS = ("future_index", "index_call", "index_put")
REGIMES = ("bull", "bear", "sideways", "unknown")
RESEARCH_TARGET_SESSIONS = 250
MIN_VALID_OI_SESSIONS = 20
INDIA_TZ = ZoneInfo("Asia/Kolkata")


def finite_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def validate_oi_records(records):
    """Reject duplicate/incomplete OI dates and report original ordering."""
    if not isinstance(records, list):
        raise ValueError("archive records is not a list")
    required = (
        "future_index_long", "future_index_short",
        "index_call_long", "index_call_short",
        "index_put_long", "index_put_short",
    )
    seen = set()
    duplicates = set()
    invalid = []
    out_of_order = 0
    previous_date = None
    valid = []

    for row_number, row in enumerate(records, start=1):
        if not isinstance(row, dict):
            invalid.append(f"row {row_number}: not an object")
            continue
        date = row.get("date")
        try:
            dt.date.fromisoformat(date)
        except (TypeError, ValueError):
            invalid.append(f"row {row_number}: invalid ISO date")
            continue
        if date in seen:
            duplicates.add(date)
        seen.add(date)
        if previous_date is not None and date < previous_date:
            out_of_order += 1
        previous_date = date

        participants = row.get("participants")
        row_errors = []
        if not isinstance(participants, dict):
            row_errors.append("participants missing")
        else:
            for group in GROUPS:
                participant = participants.get(group)
                if not isinstance(participant, dict):
                    row_errors.append(f"{group} missing")
                    continue
                for key in required:
                    if finite_number(participant.get(key)) is None:
                        row_errors.append(f"{group}.{key} invalid")
        if row_errors:
            invalid.append(f"{date}: " + ", ".join(row_errors))
        else:
            valid.append(row)

    if duplicates:
        raise ValueError("duplicate OI dates: " + ", ".join(sorted(duplicates)))
    if invalid:
        raise ValueError("invalid OI rows: " + "; ".join(invalid[:8]))
    ordered = sorted(valid, key=lambda row: row["date"])
    if len(ordered) < MIN_VALID_OI_SESSIONS:
        raise ValueError(
            f"only {len(ordered)} valid OI sessions; "
            f"at least {MIN_VALID_OI_SESSIONS} required for diagnostics"
        )
    return ordered, {
        "archive_rows": len(records),
        "valid_oi_sessions": len(ordered),
        "duplicate_oi_dates": 0,
        "out_of_order_rows": out_of_order,
        "invalid_rows": 0,
        "first_date": ordered[0]["date"],
        "last_date": ordered[-1]["date"],
    }


def load_oi_records():
    payload = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("OI archive root is not an object")
    return validate_oi_records(payload.get("records", []))


def incomplete_current_session_date(now_utc=None):
    """Return today's IST date until 16:00; an intraday daily candle is not a close."""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    now_ist = now.astimezone(INDIA_TZ)
    return now_ist.date().isoformat() if now_ist.time() < dt.time(16, 0) else None


def load_index_prices(symbol, now_utc=None):
    history = yf.Ticker(symbol).history(period="2y", interval="1d", auto_adjust=False)
    if history is None or history.empty:
        raise RuntimeError(f"Yahoo Finance returned no daily OHLC history for {symbol}")
    if isinstance(history.columns, pd.MultiIndex):
        history.columns = history.columns.get_level_values(0)
    if not {"Open", "Close"}.issubset(history.columns):
        raise RuntimeError(f"Yahoo Finance daily Open/Close missing for {symbol}")

    incomplete_date = incomplete_current_session_date(now_utc)
    incomplete_excluded_date = None
    prices = {}
    seen = set()
    duplicates = set()
    invalid_rows = 0
    for stamp, row in history.iterrows():
        date = stamp.date().isoformat()
        if date == incomplete_date:
            incomplete_excluded_date = date
            continue
        if date in seen:
            duplicates.add(date)
            continue
        seen.add(date)
        open_price = finite_number(row["Open"])
        close_price = finite_number(row["Close"])
        if open_price is None or close_price is None or open_price <= 0 or close_price <= 0:
            invalid_rows += 1
            continue
        prices[date] = {"open": open_price, "close": close_price}

    if duplicates:
        raise RuntimeError(
            f"duplicate daily OHLC dates for {symbol}: " + ", ".join(sorted(duplicates)[:8])
        )
    if len(prices) < 30:
        raise RuntimeError(f"only {len(prices)} valid OHLC sessions returned for {symbol}")
    return prices, {
        "duplicate_ohlc_dates": 0,
        "invalid_ohlc_rows": invalid_rows,
        "ohlc_sessions": len(prices),
        "ohlc_first_date": min(prices),
        "ohlc_last_date": max(prices),
        "incomplete_current_session_excluded_date": incomplete_excluded_date,
    }


def summarize_date_alignment(price_dates, oi_dates):
    """Count OI dates absent from prices and price sessions absent from OI."""
    price_set, oi_set = set(price_dates), set(oi_dates)
    if not oi_set:
        raise ValueError("OI date set is empty")
    first_date, last_date = min(oi_set), max(oi_set)
    expected = sorted(date for date in price_set if first_date <= date <= last_date)
    missing = sorted(set(expected) - oi_set)
    unmatched = sorted(oi_set - price_set)
    matched = len(oi_set & price_set)
    return {
        "price_sessions_in_oi_date_range": len(expected),
        "oi_dates_matching_price_calendar": matched,
        "missing_oi_sessions_inside_price_range": len(missing),
        "missing_oi_dates_sample": missing[:20],
        "oi_dates_without_price": len(unmatched),
        "oi_dates_without_price_sample": unmatched[:20],
        "oi_to_price_date_match_pct": round(matched / len(oi_set) * 100.0, 2),
    }


def classify_regimes(prices):
    """Signal-date-only regime: close vs SMA20 and SMA20 slope over five sessions."""
    dates = sorted(prices)
    closes = pd.Series(
        [prices[date]["close"] for date in dates], index=dates, dtype="float64"
    )
    sma = closes.rolling(20, min_periods=20).mean()
    prior_sma = sma.shift(5)
    result = {}
    for date in dates:
        current_sma, old_sma = sma.loc[date], prior_sma.loc[date]
        close = closes.loc[date]
        if pd.isna(current_sma) or pd.isna(old_sma):
            result[date] = "unknown"
        elif close > current_sma and current_sma > old_sma:
            result[date] = "bull"
        elif close < current_sma and current_sma < old_sma:
            result[date] = "bear"
        else:
            result[date] = "sideways"
    return result


def normalized_leg_change(current, previous, field, leg):
    key = f"{field}_{leg}"
    current_value = finite_number(current.get(key))
    previous_value = finite_number(previous.get(key))
    previous_long = finite_number(previous.get(f"{field}_long"))
    previous_short = finite_number(previous.get(f"{field}_short"))
    if None in (current_value, previous_value, previous_long, previous_short):
        return None
    previous_gross = previous_long + previous_short
    if previous_gross <= 0:
        return None
    return (current_value - previous_value) / previous_gross * 100.0


def normalized_net_change(current, previous, field):
    long_change = normalized_leg_change(current, previous, field, "long")
    short_change = normalized_leg_change(current, previous, field, "short")
    if long_change is None or short_change is None:
        return None
    return long_change - short_change




def client_option_quantity_features(current, previous):
    """Return raw CLIENT option OI quantity changes with explicit directional signs.

    Positive values mean CLIENT crowd added bullish exposure:
    CE long additions and PE short additions are bullish; CE short and PE long
    additions are bearish. Values are changes in open-interest positions, not
    traded buy volume.
    """
    keys = (
        "index_call_long", "index_call_short",
        "index_put_long", "index_put_short",
    )
    changes = {}
    for key in keys:
        today = finite_number(current.get(key))
        prior = finite_number(previous.get(key))
        if today is None or prior is None:
            return {}
        changes[key] = today - prior

    call_net = changes["index_call_long"] - changes["index_call_short"]
    put_raw_net = changes["index_put_long"] - changes["index_put_short"]
    put_directional = changes["index_put_short"] - changes["index_put_long"]
    return {
        "index_call_net_quantity": call_net,
        "index_put_raw_net_quantity": put_raw_net,
        "index_put_directional_net_quantity": put_directional,
        "index_option_user_arithmetic_net_quantity": call_net + put_raw_net,
        "index_option_directional_net_quantity": call_net + put_directional,
    }


def correlation(x, y, method):
    if len(x) < 5:
        return None
    left, right = pd.Series(x), pd.Series(y)
    if method == "spearman":
        left, right = left.rank(method="average"), right.rank(method="average")
        method = "pearson"
    value = left.corr(right, method=method)
    return round(float(value), 4) if pd.notna(value) else None


def calculate_metrics(rows, directional=False):
    if not rows:
        return {
            "n": 0, "pearson_r": None, "spearman_r": None,
            "avg_forward_return_pct": None, "positive_return_rate_pct": None,
            "signal_coverage_pct": None, "directional_signal_count": 0 if directional else None,
            "directional_observation_count": 0 if directional else None,
            "correct_signals": 0 if directional else None,
            "false_signals": 0 if directional else None,
            "false_bullish_signals": 0 if directional else None,
            "false_bearish_signals": 0 if directional else None,
            "false_signal_rate_pct": None, "directional_hit_rate_pct": None,
            "contrarian_correct_signals": 0 if directional else None,
            "contrarian_false_signals": 0 if directional else None,
            "contrarian_hit_rate_pct": None, "contrarian_false_signal_rate_pct": None,
            "bullish_signal_avg_return_pct": None, "bearish_signal_avg_return_pct": None,
            "bull_bear_return_spread_pct": None,
        }

    signals = [row["signal"] for row in rows]
    returns = [row["forward_return_pct"] for row in rows]
    nonzero = [row for row in rows if row["signal"] != 0]
    scored = [row for row in nonzero if row["forward_return_pct"] != 0] if directional else []
    correct = sum(
        1 for row in scored
        if (row["signal"] > 0) == (row["forward_return_pct"] > 0)
    )
    false_bullish = sum(
        1 for row in scored if row["signal"] > 0 and row["forward_return_pct"] < 0
    )
    false_bearish = sum(
        1 for row in scored if row["signal"] < 0 and row["forward_return_pct"] > 0
    )
    false_count = false_bullish + false_bearish
    bullish_returns = [
        row["forward_return_pct"] for row in nonzero if row["signal"] > 0
    ] if directional else []
    bearish_returns = [
        row["forward_return_pct"] for row in nonzero if row["signal"] < 0
    ] if directional else []
    bullish_avg = sum(bullish_returns) / len(bullish_returns) if bullish_returns else None
    bearish_avg = sum(bearish_returns) / len(bearish_returns) if bearish_returns else None
    count = len(scored)

    return {
        "n": len(rows),
        "pearson_r": correlation(signals, returns, "pearson"),
        "spearman_r": correlation(signals, returns, "spearman"),
        "avg_forward_return_pct": round(sum(returns) / len(returns), 4),
        "positive_return_rate_pct": round(
            sum(1 for value in returns if value > 0) / len(returns) * 100.0, 2
        ),
        "signal_coverage_pct": round(len(nonzero) / len(rows) * 100.0, 2) if directional else None,
        "directional_signal_count": len(nonzero) if directional else None,
        "directional_observation_count": count if directional else None,
        "correct_signals": correct if directional else None,
        "false_signals": false_count if directional else None,
        "false_bullish_signals": false_bullish if directional else None,
        "false_bearish_signals": false_bearish if directional else None,
        "false_signal_rate_pct": round(false_count / count * 100.0, 2) if directional and count else None,
        "directional_hit_rate_pct": round(correct / count * 100.0, 2) if directional and count else None,
        # PDMP is contrarian: every crowd-follow miss is a contrarian hit, and vice versa.
        "contrarian_correct_signals": false_count if directional else None,
        "contrarian_false_signals": correct if directional else None,
        "contrarian_hit_rate_pct": round(false_count / count * 100.0, 2) if directional and count else None,
        "contrarian_false_signal_rate_pct": round(correct / count * 100.0, 2) if directional and count else None,
        "bullish_signal_avg_return_pct": round(bullish_avg, 4) if bullish_avg is not None else None,
        "bearish_signal_avg_return_pct": round(bearish_avg, 4) if bearish_avg is not None else None,
        "bull_bear_return_spread_pct": (
            round(bullish_avg - bearish_avg, 4)
            if bullish_avg is not None and bearish_avg is not None else None
        ),
    }


def partition_non_overlapping_rows(rows, horizon):
    """Partition dated holdout rows into every possible non-overlapping phase.

    Within each phase, signal positions are at least horizon sessions apart,
    so their forward-return windows do not overlap. Different phases are
    alternative partitions of the same holdout and are not independent.
    """
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    valid_rows = [
        row for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("signal_session_position"), int)
        and not isinstance(row.get("signal_session_position"), bool)
    ]
    if not valid_rows:
        return []
    anchor = min(row["signal_session_position"] for row in valid_rows)
    return [
        [
            row for row in valid_rows
            if (row["signal_session_position"] - anchor) % horizon == phase
        ]
        for phase in range(horizon)
    ]


def non_overlapping_phase_metrics(rows, horizon, directional):
    """Describe every non-overlapping holdout phase; do not infer significance."""
    phases = partition_non_overlapping_rows(rows, horizon)
    if not phases:
        return []
    anchor_row = min(
        (row for row in rows if isinstance(row, dict)
         and isinstance(row.get("signal_session_position"), int)
         and not isinstance(row.get("signal_session_position"), bool)),
        key=lambda row: row["signal_session_position"],
    )
    results = []
    for phase_offset, phase_rows in enumerate(phases):
        metrics = calculate_metrics(phase_rows, directional=directional)
        results.append({
            "phase_offset_sessions": phase_offset,
            "anchor_signal_date": anchor_row.get("date"),
            "n": metrics["n"],
            "directional_observation_count": metrics["directional_observation_count"],
            "correct_signals": metrics["correct_signals"],
            "false_signals": metrics["false_signals"],
            "false_signal_rate_pct": metrics["false_signal_rate_pct"],
            "directional_hit_rate_pct": metrics["directional_hit_rate_pct"],
            "contrarian_correct_signals": metrics["contrarian_correct_signals"],
            "contrarian_false_signals": metrics["contrarian_false_signals"],
            "contrarian_hit_rate_pct": metrics["contrarian_hit_rate_pct"],
            "contrarian_false_signal_rate_pct": metrics["contrarian_false_signal_rate_pct"],
            "avg_forward_return_pct": metrics["avg_forward_return_pct"],
        })
    return results



def magnitude_threshold_diagnostics(rows_by_feature):
    """Evaluate predeclared absolute-signal quantiles learned on train only.

    Thresholds are the 50th, 75th and 90th percentiles of absolute training
    quantities. They are applied unchanged to the chronological holdout.
    This is descriptive threshold research, not a fitted live scoring rule.
    """
    feature = "CLIENT.index_option_directional_net_quantity"
    observations = rows_by_feature.get(feature, [])
    diagnostics = []
    for horizon in HORIZONS:
        sample = [row for row in observations if row["horizon"] == horizon]
        cut = int(len(sample) * 0.70)
        train, holdout = sample[:cut], sample[cut:]
        magnitudes = sorted(abs(row["signal"]) for row in train if row["signal"] != 0)
        if not magnitudes:
            continue
        for quantile in (0.50, 0.75, 0.90):
            rank = max(0, min(len(magnitudes) - 1, math.ceil(quantile * len(magnitudes)) - 1))
            threshold = magnitudes[rank]
            selected = [
                row for row in holdout
                if abs(row["signal"]) >= threshold and row["forward_return_pct"] != 0
            ]
            metrics = calculate_metrics(selected, directional=True)
            diagnostics.append({
                "feature": feature,
                "horizon_sessions": horizon,
                "training_quantile": quantile,
                "training_nonzero_observations": len(magnitudes),
                "absolute_quantity_threshold": threshold,
                "holdout_selected_observations": metrics["directional_observation_count"],
                "holdout_total_rows": len(selected),
                "crowd_follow_hit_rate_pct": metrics["directional_hit_rate_pct"],
                "pdmp_contrarian_hit_rate_pct": metrics["contrarian_hit_rate_pct"],
                "crowd_follow_false_signals": metrics["false_signals"],
                "pdmp_contrarian_false_signals": metrics["contrarian_false_signals"],
                "holdout_avg_forward_return_pct": metrics["avg_forward_return_pct"],
            })
    return diagnostics


def client_futures_recent_direction_check(records, prices, sessions=7, anchor_date="2026-11-12"):
    """Check latest CLIENT Futures OI signals against next-session close direction."""
    if not isinstance(sessions, int) or isinstance(sessions, bool) or sessions < 1:
        raise ValueError("sessions must be a positive integer")
    price_dates = sorted(prices)
    price_index = {date: position for position, date in enumerate(price_dates)}
    ordered = sorted(records, key=lambda row: row["date"])
    observations = []
    for position in range(1, len(ordered)):
        previous, current = ordered[position - 1], ordered[position]
        signal_date = current.get("date")
        previous_date = previous.get("date")
        if signal_date not in price_index or previous_date not in price_index:
            continue
        signal_pos = price_index[signal_date]
        if signal_pos - price_index[previous_date] != 1 or signal_pos + 1 >= len(price_dates):
            continue
        current_client = (current.get("participants") or {}).get("CLIENT") or {}
        previous_client = (previous.get("participants") or {}).get("CLIENT") or {}
        long_now = finite_number(current_client.get("future_index_long"))
        long_before = finite_number(previous_client.get("future_index_long"))
        short_now = finite_number(current_client.get("future_index_short"))
        short_before = finite_number(previous_client.get("future_index_short"))
        if None in (long_now, long_before, short_now, short_before):
            continue
        long_change, short_change = long_now - long_before, short_now - short_before
        previous_gross = long_before + short_before
        if previous_gross <= 0:
            continue
        # Scale the net change against prior total exposure. Dividing by the
        # absolute changes would saturate nearly every one-sided move at +/-10.
        score = max(-10.0, min(10.0, 10.0 * (long_change - short_change) / previous_gross))
        next_date = price_dates[signal_pos + 1]
        base_close = finite_number(prices[signal_date].get("close"))
        next_close = finite_number(prices[next_date].get("close"))
        if base_close is None or next_close is None or base_close <= 0 or next_close <= 0:
            continue
        forward_return = (next_close / base_close - 1.0) * 100.0
        prediction = "BULLISH" if score > 0 else ("BEARISH" if score < 0 else "NEUTRAL")
        actual = "UP" if forward_return > 0 else ("DOWN" if forward_return < 0 else "FLAT")
        observations.append({
            "signal_date": signal_date, "next_session": next_date,
            "client_futures_long_change": round(long_change, 2),
            "client_futures_short_change": round(short_change, 2),
            "previous_gross_exposure": round(previous_gross, 2),
            "score": round(score, 2), "predicted_direction": prediction,
            "next_session_close_change_pct": round(forward_return, 4),
            "actual_direction": actual,
            "correct": (prediction == "BULLISH" and actual == "UP") or
                       (prediction == "BEARISH" and actual == "DOWN"),
            "contrarian_correct": (prediction == "BULLISH" and actual == "DOWN") or
                                  (prediction == "BEARISH" and actual == "UP"),
        })
    # Only count genuinely new signal dates after the agreed baseline.
    new_observations = [row for row in observations if row["signal_date"] > anchor_date]
    recent = new_observations[-sessions:]
    directional = [
        row for row in recent
        if row["predicted_direction"] != "NEUTRAL" and row["actual_direction"] != "FLAT"
    ]
    correct = sum(1 for row in directional if row["correct"])
    contrarian_correct = sum(1 for row in directional if row["contrarian_correct"])
    count = len(directional)
    return {
        "status": "ready" if len(recent) >= sessions else "collecting_new_sessions",
        "anchor_date_exclusive": anchor_date,
        "new_completed_observations": len(new_observations),
        "remaining_observations": max(0, sessions - len(recent)),
        "method": "CLIENT Futures EOD OI Δ(Long−Short), scaled by prior gross exposure to ±10; compare direct and contrarian signs with next NSE session close-to-close index direction",
        "requested_sessions": sessions, "sample_sessions": len(recent),
        "directional_observation_count": count, "correct_signals": correct,
        "wrong_signals": count - correct,
        "directional_hit_rate_pct": round(correct / count * 100.0, 2) if count else None,
        "contrarian_correct_signals": contrarian_correct,
        "contrarian_hit_rate_pct": round(contrarian_correct / count * 100.0, 2) if count else None,
        "neutral_or_flat_excluded": len(recent) - count,
        "first_signal_date": recent[0]["signal_date"] if recent else None,
        "last_signal_date": recent[-1]["signal_date"] if recent else None,
        "observations": recent, "score_changed": False,
        "eligible_for_live_score": False,
        "scope": "NSE participant-wise CLIENT Index Futures aggregate; market-wide, not index-specific",
    }

def analyze_index(index_name, symbol, records):
    prices, price_validation = load_index_prices(symbol)
    price_dates = sorted(prices)
    price_index = {date: i for i, date in enumerate(price_dates)}
    oi_dates = [row["date"] for row in records]
    alignment = summarize_date_alignment(price_dates, oi_dates)
    regimes = classify_regimes(prices)
    rows_by_feature = {}
    aligned_dates = []
    nonconsecutive_skipped = 0
    unmatched_pairs_skipped = 0

    for index in range(1, len(records)):
        current, previous = records[index], records[index - 1]
        date, previous_date = current["date"], previous["date"]
        if date not in price_index or previous_date not in price_index:
            unmatched_pairs_skipped += 1
            continue
        if price_index[date] - price_index[previous_date] != 1:
            nonconsecutive_skipped += 1
            continue
        aligned_dates.append(date)
        current_groups, previous_groups = current["participants"], previous["participants"]
        price_position = price_index[date]

        for group in GROUPS:
            for field in FIELDS:
                features = []
                net_value = normalized_net_change(
                    current_groups[group], previous_groups[group], field
                )
                if net_value is not None:
                    features.append((f"{field}_net_change_pct_prior_gross", net_value))
                for leg in ("long", "short"):
                    leg_value = normalized_leg_change(
                        current_groups[group], previous_groups[group], field, leg
                    )
                    if leg_value is not None:
                        if field == "future_index" and leg == "short":
                            leg_value *= -1
                        features.append((
                            f"{field}_{leg}_change_pct_prior_gross", leg_value
                        ))

                # Add the raw CLIENT option quantity features once per date pair.
                if group == "CLIENT" and field == "index_put":
                    features.extend(client_option_quantity_features(
                        current_groups[group], previous_groups[group]
                    ).items())

                for suffix, value in features:
                    bucket = rows_by_feature.setdefault(f"{group}.{suffix}", [])
                    for horizon in HORIZONS:
                        target_position = price_position + horizon
                        if target_position >= len(price_dates):
                            continue
                        entry_date = price_dates[price_position + 1]
                        target_date = price_dates[target_position]
                        forward = (
                            prices[target_date]["close"] / prices[entry_date]["open"] - 1.0
                        ) * 100.0
                        if math.isfinite(forward):
                            bucket.append({
                                "date": date, "entry_date": entry_date,
                                "target_date": target_date, "horizon": horizon,
                                "signal_session_position": price_position,
                                "signal": value, "forward_return_pct": forward,
                                "regime": regimes.get(date, "unknown"),
                            })

    if len(aligned_dates) < MIN_VALID_OI_SESSIONS:
        raise RuntimeError(
            f"only {len(aligned_dates)} OI dates aligned to {index_name}; "
            f"need at least {MIN_VALID_OI_SESSIONS}"
        )

    results = []
    for feature, observations in sorted(rows_by_feature.items()):
        group, field_feature = feature.split(".", 1)
        futures_directional = field_feature.startswith("future_index")
        options_directional = field_feature == "index_option_directional_net_quantity"
        directional_signal = futures_directional or options_directional
        for horizon in HORIZONS:
            sample_rows = [row for row in observations if row["horizon"] == horizon]
            cut = int(len(sample_rows) * 0.70)
            for split, sample in (
                ("all", sample_rows),
                ("train_first_70pct", sample_rows[:cut]),
                ("chronological_holdout_last_30pct", sample_rows[cut:]),
            ):
                item = {
                    "feature": feature, "participant": group, "field": field_feature,
                    "horizon_sessions": horizon, "sample": split,
                    "directional_futures": futures_directional,
                    "directional_options": options_directional,
                }
                item.update(calculate_metrics(sample, directional=directional_signal))
                if split == "chronological_holdout_last_30pct":
                    item["regime_metrics"] = {
                        regime: calculate_metrics(
                            [row for row in sample if row["regime"] == regime],
                            directional=directional_signal,
                        )
                        for regime in REGIMES
                    }
                    if directional_signal:
                        item["non_overlapping_holdout_phases"] = (
                            non_overlapping_phase_metrics(
                                sample, horizon, directional=directional_signal
                            )
                        )
                results.append(item)

    regime_counts = Counter(regimes.get(date, "unknown") for date in aligned_dates)
    return {
        "symbol": symbol,
        "price_source": f"Yahoo Finance daily Open/Close ({symbol}), 2-year window",
        **price_validation,
        **alignment,
        "aligned_oi_dates": len(aligned_dates),
        "nonconsecutive_oi_pairs_skipped": nonconsecutive_skipped,
        "unmatched_oi_pairs_skipped": unmatched_pairs_skipped,
        "aligned_first_date": min(aligned_dates),
        "aligned_last_date": max(aligned_dates),
        "regime_definition": (
            "As of signal date t: bull if close > SMA20 and SMA20(t) > SMA20(t-5); "
            "bear if close < SMA20 and SMA20(t) < SMA20(t-5); otherwise sideways. "
            "Only data available through t is used."
        ),
        "regime_counts_on_aligned_dates": {
            regime: regime_counts.get(regime, 0) for regime in REGIMES
        },
        "target_definition": (
            "OI known after EOD on date t; entry next trading session open; exit at "
            "the close of session 1, 3, or 5 counted from that next session. "
            "No same-day close entry."
        ),
        "false_signal_definition": (
            "For explicitly marked futures and CLIENT option directional-net features, "
            "every non-zero signed quantity/feature is a raw directional call. "
            "Bullish signal followed by a negative return or bearish signal followed by "
            "a positive return is false. Zero-return observations are excluded; no "
            "optimized signal threshold is fitted."
        ),
        "non_overlapping_holdout_method": (
            "For each horizon H, the chronological holdout is split into all H possible "
            "phase offsets using actual index-session positions. Within one phase, signal "
            "dates are at least H sessions apart, so forward windows do not overlap. "
            "Non-overlapping phases are reported for futures directional features only; "
            "options remain correlation-only. Phases are alternative partitions, not "
            "independent samples. Descriptive only: no phase selection or phase-level p-values."
        ),
        "metrics": results,
        "client_futures_recent_7_session_check": client_futures_recent_direction_check(records, prices, sessions=7),
        "client_futures_new_14_session_check": client_futures_recent_direction_check(records, prices, sessions=14),
        "client_option_quantity_magnitude_threshold_diagnostics": magnitude_threshold_diagnostics(rows_by_feature),
    }


def run():
    records, archive_validation = load_oi_records()
    index_results, errors = {}, {}
    for name, symbol in INDEXES.items():
        try:
            index_results[name] = analyze_index(name, symbol, records)
        except Exception as exc:
            errors[name] = str(exc)[:300]
    if not index_results:
        raise RuntimeError("all index backtests failed: " + json.dumps(errors, ensure_ascii=False))

    report = {
        "status": "exploratory_only",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "oi_source": "NSE official participant-wise EOD OI CSV archive",
        "oi_scope_warning": (
            "NSE participant-wise OI is aggregate Index F&O participant totals, not "
            "separate NIFTY/SENSEX/BANKNIFTY participant OI. The same aggregate OI "
            "features are tested independently against each index price series."
        ),
        "oi_first_date": records[0]["date"], "oi_last_date": records[-1]["date"],
        "oi_sessions": len(records), "archive_validation": archive_validation,
        "data_adequacy": {
            "research_target_sessions": RESEARCH_TARGET_SESSIONS,
            "target_met": len(records) >= RESEARCH_TARGET_SESSIONS,
            "status": "expanded_exploratory_sample" if len(records) >= RESEARCH_TARGET_SESSIONS else "limited_sample",
            "note": (
                "250 sessions is approximately one trading year and a broader "
                "exploratory coverage target, not a statistical guarantee. A live score "
                "still requires stable out-of-sample incremental value."
            ),
        },
        "validation": {
            "chronological_split": "first 70% train; last 30% holdout, ordered by date",
            "directional_hit_rate": (
                "Futures net/leg OI changes and CLIENT option directional net quantity "
                "are tested as signed crowd-direction signals. CE long and PE short "
                "changes are bullish; CE short and PE long changes are bearish. "
                "Other option features remain correlation-only."
            ),
            "false_signal_rate": (
                "Non-zero signed futures and explicitly directional CLIENT option "
                "quantity feature signs versus forward return sign; zero-return "
                "observations excluded; no optimized threshold."
            ),
            "regime_method": "signal-date-only SMA20 and its five-session slope",
            "score_changed": False, "eligible_for_live_score": False,
            "reason": (
                "Exploratory OI diagnostics only. No OI weight or trading score is "
                "assigned; aggregate scope, sample size and incremental value remain "
                "limiting factors."
            ),
            "client_option_quantity_definition": (
                "Directional crowd quantity = change in CLIENT CE long − CE short "
                "+ PE short − PE long. CE long and PE short additions are bullish; "
                "CE short and PE long additions are bearish. The user's raw arithmetic "
                "net (CE long − CE short + PE long − PE short) is retained as a "
                "separate correlation-only diagnostic."
            ),
        },
        "indices": index_results, "index_errors": errors,
    }

    if "NIFTY" in index_results:
        nifty = index_results["NIFTY"]
        report.update({
            "price_source": nifty["price_source"],
            "nifty_ohlc_sessions": nifty["ohlc_sessions"],
            "aligned_oi_dates": nifty["aligned_oi_dates"],
            "nonconsecutive_oi_pairs_skipped": nifty["nonconsecutive_oi_pairs_skipped"],
            "aligned_first_date": nifty["aligned_first_date"],
            "aligned_last_date": nifty["aligned_last_date"],
            "target_definition": nifty["target_definition"],
            "metrics": nifty["metrics"],
        })

    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "OI multi-index backtest written: "
        + ", ".join(
            f"{name}={data['aligned_oi_dates']} aligned, "
            f"{data['missing_oi_sessions_inside_price_range']} OI gaps"
            for name, data in index_results.items()
        )
    )
    if errors:
        print("Some index diagnostics unavailable: " + json.dumps(errors, ensure_ascii=False))


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        failure = {
            "status": "unavailable",
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "score_changed": False, "reason": str(exc),
        }
        OUTPUT.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"OI backtest diagnostics unavailable: {exc}")
