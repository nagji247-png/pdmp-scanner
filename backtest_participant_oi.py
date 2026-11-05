#!/usr/bin/env python3
"""Exploratory point-in-time backtest of NSE participant OI against three index returns.

NSE participant-wise OI is an aggregate Index F&O participant dataset, not OI
reported separately for NIFTY, SENSEX, or BANKNIFTY. The same aggregate features
are therefore tested against each index's own OHLC series. This script never
changes a live trading score.
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
INDEXES = {
    "NIFTY": "^NSEI",
    "SENSEX": "^BSESN",
    "BANKNIFTY": "^NSEBANK",
}
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
        raise ValueError(f"only {len(dates)} valid OI sessions; at least 20 required")
    return [by_date[d] for d in dates]


def load_index_prices(symbol):
    history = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=False)
    if history is None or history.empty:
        raise RuntimeError(f"Yahoo Finance returned no daily OHLC history for {symbol}")
    if isinstance(history.columns, pd.MultiIndex):
        history.columns = history.columns.get_level_values(0)
    if not {"Open", "Close"}.issubset(history.columns):
        raise RuntimeError(f"Yahoo Finance daily Open/Close missing for {symbol}")
    prices = {}
    for stamp, row in history[["Open", "Close"]].dropna().iterrows():
        open_price = finite_number(row["Open"])
        close_price = finite_number(row["Close"])
        if open_price is not None and close_price is not None and open_price > 0 and close_price > 0:
            prices[stamp.date().isoformat()] = {"open": open_price, "close": close_price}
    if len(prices) < 30:
        raise RuntimeError(f"only {len(prices)} valid OHLC sessions returned for {symbol}")
    return prices


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


def analyze_index(index_name, symbol, records):
    prices = load_index_prices(symbol)
    price_dates = sorted(prices)
    price_index = {date: i for i, date in enumerate(price_dates)}
    rows_by_feature = {}
    aligned_dates = []
    nonconsecutive_skipped = 0

    for index in range(1, len(records)):
        current, previous = records[index], records[index - 1]
        date, previous_date = current["date"], previous["date"]
        if date not in price_index or previous_date not in price_index:
            continue
        if price_index[date] - price_index[previous_date] != 1:
            nonconsecutive_skipped += 1
            continue
        aligned_dates.append(date)
        current_groups = current["participants"]
        previous_groups = previous["participants"]
        pidx = price_index[date]
        for group in GROUPS:
            for field in FIELDS:
                features = []
                net_value = normalized_net_change(current_groups[group],
                                                  previous_groups[group], field)
                if net_value is not None:
                    features.append((f"{field}_net_change_pct_prior_gross", net_value))
                for leg in ("long", "short"):
                    leg_value = normalized_leg_change(current_groups[group],
                                                      previous_groups[group], field, leg)
                    if leg_value is not None:
                        # Futures short additions are bearish; options remain correlation-only.
                        if field == "future_index" and leg == "short":
                            leg_value *= -1
                        features.append((f"{field}_{leg}_change_pct_prior_gross", leg_value))
                for suffix, value in features:
                    feature = f"{group}.{suffix}"
                    bucket = rows_by_feature.setdefault(feature, [])
                    for horizon in HORIZONS:
                        target_idx = pidx + horizon
                        if target_idx >= len(price_dates):
                            continue
                        entry_date = price_dates[pidx + 1]
                        target_date = price_dates[target_idx]
                        entry_open = prices[entry_date]["open"]
                        target_close = prices[target_date]["close"]
                        forward = (target_close / entry_open - 1.0) * 100.0
                        if math.isfinite(forward):
                            bucket.append({
                                "date": date, "entry_date": entry_date,
                                "target_date": target_date, "horizon": horizon,
                                "signal": value, "forward_return_pct": forward,
                            })

    if len(aligned_dates) < 20:
        raise RuntimeError(
            f"only {len(aligned_dates)} OI dates aligned to {index_name}; need at least 20"
        )

    results = []
    for feature, observations in sorted(rows_by_feature.items()):
        group, field_feature = feature.split(".", 1)
        is_futures = field_feature.startswith("future_index")
        for horizon in HORIZONS:
            horizon_rows = [r for r in observations if r["horizon"] == horizon]
            cut = int(len(horizon_rows) * 0.70)
            for split, sample in (
                ("all", horizon_rows),
                ("train_first_70pct", horizon_rows[:cut]),
                ("chronological_holdout_last_30pct", horizon_rows[cut:]),
            ):
                item = {"feature": feature, "participant": group,
                        "field": field_feature, "horizon_sessions": horizon,
                        "sample": split}
                item.update(calculate_metrics(sample, directional=is_futures))
                results.append(item)

    return {
        "symbol": symbol,
        "price_source": f"Yahoo Finance daily open and close ({symbol})",
        "ohlc_sessions": len(prices),
        "aligned_oi_dates": len(aligned_dates),
        "nonconsecutive_oi_pairs_skipped": nonconsecutive_skipped,
        "aligned_first_date": min(aligned_dates),
        "aligned_last_date": max(aligned_dates),
        "target_definition": (
            "OI change known after EOD on date t; entry is next trading session open; "
            "exit is the close of session 1, 3, or 5 counted from that next session. "
            "No same-day close entry."
        ),
        "metrics": results,
    }


def run():
    records = load_oi_records()
    index_results = {}
    errors = {}
    for index_name, symbol in INDEXES.items():
        try:
            index_results[index_name] = analyze_index(index_name, symbol, records)
        except Exception as exc:
            errors[index_name] = str(exc)[:300]

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
        "oi_first_date": records[0]["date"],
        "oi_last_date": records[-1]["date"],
        "oi_sessions": len(records),
        "validation": {
            "chronological_split": "first 70% train; last 30% holdout, ordered by date",
            "directional_hit_rate": (
                "reported for futures net OI and futures long/short changes (short "
                "changes sign-inverted); option-side long/short is correlation-only."
            ),
            "score_changed": False,
            "eligible_for_live_score": False,
            "reason": (
                "Exploratory sample only. No OI weight or trading score is assigned. "
                "Require longer history and stable chronological holdout performance "
                "across indices before considering any live score contribution."
            ),
        },
        "indices": index_results,
        "index_errors": errors,
    }
    # Keep legacy top-level NIFTY summary fields available for existing readers.
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
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(
        "OI multi-index backtest written: "
        + ", ".join(f"{name}={data['aligned_oi_dates']} aligned" for name, data in index_results.items())
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
            "score_changed": False,
            "reason": str(exc),
        }
        OUTPUT.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"OI backtest diagnostics unavailable: {exc}")
