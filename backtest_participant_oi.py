#!/usr/bin/env python3
"""Exploratory, point-in-time backtest of NSE participant OI versus forward NIFTY returns.

This script deliberately does not generate or change a trading score. OI is observed
after the EOD session on date t; targets begin at the NIFTY close on t and end at
the close of a later trading session. Results are descriptive diagnostics only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "participant_oi_history.json"
OUTPUT = ROOT / "participant_oi_backtest.json"
SYMBOL = "^NSEI"
HORIZONS = (1, 3, 5)
GROUPS = ("FII", "DII", "PRO", "CLIENT")
FIELDS = ("future_index", "index_call", "index_put")


def finite_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def load_oi_records():
    payload = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("archive records is not a list")
    by_date = {}
    seen_dates = set()
    required = ("future_index_long", "future_index_short",
                "index_call_long", "index_call_short",
                "index_put_long", "index_put_short")
    for row in records:
        date = row.get("date")
        dt.date.fromisoformat(date)
        if date in seen_dates:
            raise ValueError(f"duplicate OI date: {date}")
        seen_dates.add(date)
        participants = row.get("participants") or {}
        if not all(group in participants for group in GROUPS):
            raise ValueError(f"{date}: one or more participant groups are missing")
        for group in GROUPS:
            for key in required:
                if finite_number(participants[group].get(key)) is None:
                    raise ValueError(f"{date}: invalid {group}.{key}")
        by_date[date] = row
    dates = sorted(by_date)
    if len(dates) != len(set(dates)):
        raise ValueError("duplicate OI dates")
    if len(dates) < 20:
        raise ValueError(f"only {len(dates)} valid OI sessions; at least 20 required for diagnostics")
    return [by_date[d] for d in dates]


def load_nifty_closes():
    history = yf.Ticker(SYMBOL).history(period="6mo", interval="1d", auto_adjust=False)
    if history is None or history.empty or "Close" not in history:
        raise RuntimeError("Yahoo Finance returned no NIFTY daily close history")
    closes = {}
    for stamp, value in history["Close"].dropna().items():
        close = finite_number(value)
        if close is not None and close > 0:
            closes[stamp.date().isoformat()] = close
    if len(closes) < 30:
        raise RuntimeError(f"only {len(closes)} valid NIFTY daily closes returned")
    return closes


def normalized_leg_change(current, previous, field, leg):
    key = f"{field}_{leg}"
    current_value = finite_number(current.get(key))
    previous_value = finite_number(previous.get(key))
    previous_gross = (
        finite_number(previous.get(f"{field}_long")) +
        finite_number(previous.get(f"{field}_short"))
    )
    if current_value is None or previous_value is None or previous_gross <= 0:
        return None
    return (current_value - previous_value) / previous_gross * 100.0


def normalized_net_change(current, previous, field):
    long_change = normalized_leg_change(current, previous, field, "long")
    short_change = normalized_leg_change(current, previous, field, "short")
    if long_change is None or short_change is None:
        return None
    return long_change - short_change


def correlation(x, y, method):
    if len(x) < 5:
        return None
    value = pd.Series(x).corr(pd.Series(y), method=method)
    return round(float(value), 4) if pd.notna(value) else None


def metrics(rows, directional=False):
    if not rows:
        return {"n": 0, "pearson_r": None, "spearman_r": None,
                "avg_forward_return_pct": None, "positive_return_rate_pct": None,
                "directional_hit_rate_pct": None}
    x = [r["signal"] for r in rows]
    y = [r["forward_return_pct"] for r in rows]
    nonzero = [(a, b) for a, b in zip(x, y) if a != 0 and b != 0]
    hit = (sum(1 for a, b in nonzero if (a > 0) == (b > 0)) / len(nonzero) * 100
           if directional and nonzero else None)
    return {
        "n": len(rows),
        "pearson_r": correlation(x, y, "pearson"),
        "spearman_r": correlation(x, y, "spearman"),
        "avg_forward_return_pct": round(sum(y) / len(y), 4),
        "positive_return_rate_pct": round(sum(1 for v in y if v > 0) / len(y) * 100, 2),
        "directional_hit_rate_pct": round(hit, 2) if hit is not None else None,
    }


def run():
    records = load_oi_records()
    closes = load_nifty_closes()
    price_dates = sorted(closes)
    price_index = {date: i for i, date in enumerate(price_dates)}
    rows_by_feature = {}
    aligned_dates = []
    nonconsecutive_oi_pairs_skipped = 0

    for index in range(1, len(records)):
        current, previous = records[index], records[index - 1]
        date, previous_date = current["date"], previous["date"]
        if date not in price_index or previous_date not in price_index:
            continue
        # Only call this a one-session OI change when the two archive dates
        # are adjacent NIFTY trading sessions. Never silently span a missing day.
        if price_index[date] - price_index[previous_date] != 1:
            nonconsecutive_oi_pairs_skipped += 1
            continue
        aligned_dates.append(date)
        current_groups = current["participants"]
        previous_groups = previous["participants"]
        pidx = price_index[date]
        for group in GROUPS:
            for field in FIELDS:
                net_value = normalized_net_change(current_groups[group],
                                                  previous_groups[group], field)
                features = []
                if net_value is not None:
                    features.append((f"{field}_net_change_pct_prior_gross", net_value, 1))
                for leg in ("long", "short"):
                    leg_value = normalized_leg_change(current_groups[group],
                                                      previous_groups[group], field, leg)
                    if leg_value is not None:
                        # Futures long additions are positive; short additions are bearish.
                        direction = -1 if field == "future_index" and leg == "short" else 1
                        features.append((f"{field}_{leg}_change_pct_prior_gross",
                                         leg_value * direction, direction))
                for feature_suffix, value, _direction in features:
                    feature = f"{group}.{feature_suffix}"
                    bucket = rows_by_feature.setdefault(feature, [])
                    for horizon in HORIZONS:
                        target_idx = pidx + horizon
                        if target_idx >= len(price_dates):
                            continue
                        target_date = price_dates[target_idx]
                        forward = (closes[target_date] / closes[date] - 1.0) * 100.0
                        if math.isfinite(forward):
                            bucket.append({
                                "date": date, "target_date": target_date,
                                "horizon": horizon, "signal": value,
                                "forward_return_pct": forward,
                            })

    if len(aligned_dates) < 20:
        raise RuntimeError(
            f"only {len(aligned_dates)} OI dates aligned to NIFTY closes; "
            "need at least 20 before publishing diagnostics"
        )

    results = []
    for feature, observations in sorted(rows_by_feature.items()):
        group, field_feature = feature.split(".", 1)
        is_futures = field_feature.startswith("future_index")
        for horizon in HORIZONS:
            horizon_rows = [r for r in observations if r["horizon"] == horizon]
            # Chronological 70/30 split; no random shuffle and no future leakage.
            cut = int(len(horizon_rows) * 0.70)
            for split, sample in (
                ("all", horizon_rows),
                ("train_first_70pct", horizon_rows[:cut]),
                ("chronological_holdout_last_30pct", horizon_rows[cut:]),
            ):
                item = {"feature": feature, "participant": group,
                        "field": field_feature, "horizon_sessions": horizon,
                        "sample": split}
                item.update(metrics(sample, directional=is_futures))
                results.append(item)

    report = {
        "status": "exploratory_only",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "oi_source": "NSE official participant-wise EOD OI CSV archive",
        "price_source": "Yahoo Finance daily close (^NSEI)",
        "oi_first_date": records[0]["date"],
        "oi_last_date": records[-1]["date"],
        "oi_sessions": len(records),
        "nifty_close_sessions": len(closes),
        "aligned_oi_dates": len(aligned_dates),
        "nonconsecutive_oi_pairs_skipped": nonconsecutive_oi_pairs_skipped,
        "aligned_first_date": min(aligned_dates),
        "aligned_last_date": max(aligned_dates),
        "target_definition": (
            "OI change known after EOD on date t; forward return is NIFTY close "
            "from date t to the close of the 1st, 3rd, or 5th subsequent trading session."
        ),
        "normalization": (
            "Separate long and short leg changes, plus net change, each divided by "
            "that participant/field's previous-session gross OI (long + short), in percent."
        ),
        "validation": {
            "chronological_split": "first 70% train; last 30% holdout, ordered by date",
            "directional_hit_rate": (
                "reported for futures net OI and futures long/short changes (short changes "
                "are sign-inverted); call/put OI is correlation-only because option-side "
                "long/short positions are not a clean directional proxy."
            ),
            "score_changed": False,
            "eligible_for_live_score": False,
            "reason": (
                "Exploratory sample only. No OI weight or trading score is assigned. "
                "Require longer history and stable chronological holdout performance "
                "before considering any live score contribution."
            ),
        },
        "metrics": results,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(
        f"OI backtest diagnostics written: {len(records)} OI sessions, "
        f"{len(aligned_dates)} aligned dates, {len(results)} metric rows"
    )


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        # Keep the market scan healthy; persist an explicit failure, never stale/zero metrics.
        failure = {
            "status": "unavailable",
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "score_changed": False,
            "reason": str(exc),
        }
        OUTPUT.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"OI backtest diagnostics unavailable: {exc}")
