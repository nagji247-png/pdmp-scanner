"""Offline close-to-close contrarian backtest. No network/provider access."""
import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


def _day(value):
    if not isinstance(value, str):
        return None
    raw = value.strip()
    for parser in (date.fromisoformat,):
        try:
            return parser(raw[:10])
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            pass
    return None


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _observed(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def run_contrarian_backtest(signals, closes, threshold=1.0):
    """Positive score means bullish crowd; negative means bearish crowd.
    Forecast the opposite direction from the EOD signal date close to the
    next available session close. Dates are exchange-local market dates.
    """
    if not isinstance(signals, list) or not isinstance(closes, list):
        raise TypeError("signals and closes must both be lists")
    threshold = _number(threshold)
    if threshold is None or not 0 <= threshold <= 10:
        raise ValueError("threshold must be between 0 and 10")

    prices = defaultdict(dict)
    bad_prices = 0
    for row in closes:
        if not isinstance(row, dict):
            bad_prices += 1
            continue
        asset = str(row.get("asset") or "").strip().upper()
        day = _day(row.get("market_date"))
        close = _number(row.get("close"))
        source = row.get("source")
        if not asset or day is None or close is None or close <= 0 or not isinstance(source, str) or not source.strip():
            bad_prices += 1
            continue
        old = prices[asset].get(day)
        if old and old["close"] != close:
            raise ValueError(f"conflicting close rows for {asset} on {day.isoformat()}")
        prices[asset][day] = {"close": close, "source": source.strip()}

    sessions = {asset: sorted(rows) for asset, rows in prices.items()}
    latest = {}
    bad_signals = 0
    for row in signals:
        if not isinstance(row, dict):
            bad_signals += 1
            continue
        asset = str(row.get("asset") or "").strip().upper()
        day = _day(row.get("signal_date"))
        known_on = _day(row.get("known_on") or row.get("signal_date"))
        score = _number(row.get("score"))
        source = row.get("source")
        observed = _observed(row.get("observed_at"))
        if (not asset or day is None or known_on is None or known_on > day
                or score is None or not -10 <= score <= 10
                or not isinstance(source, str) or not source.strip() or observed is None):
            bad_signals += 1
            continue
        key = (asset, day)
        if key not in latest or observed > latest[key]["_observed"]:
            latest[key] = {"asset": asset, "day": day, "score": score,
                           "source": source.strip(), "_observed": observed}

    trades = []
    skipped = {"neutral_or_below_threshold": 0, "missing_base_close": 0,
               "missing_next_session": 0}
    for (asset, signal_day), signal in sorted(latest.items()):
        crowd = 1 if signal["score"] > threshold else -1 if signal["score"] < -threshold else 0
        if crowd == 0:
            skipped["neutral_or_below_threshold"] += 1
            continue
        if signal_day not in prices.get(asset, {}):
            skipped["missing_base_close"] += 1
            continue
        future = [d for d in sessions.get(asset, []) if d > signal_day]
        if not future:
            skipped["missing_next_session"] += 1
            continue
        target_day = future[0]
        base = prices[asset][signal_day]["close"]
        target = prices[asset][target_day]["close"]
        move = (target / base - 1) * 100
        actual = 1 if move > 0 else -1 if move < 0 else 0
        if actual == 0:
            continue
        contra = -crowd
        trades.append({
            "asset": asset, "signal_date": signal_day.isoformat(),
            "signal_score": signal["score"], "signal_source": signal["source"],
            "base_close": base, "target_session": target_day.isoformat(),
            "target_close": target, "next_session_return_pct": round(move, 6),
            "crowd_direction": "BULLISH" if crowd > 0 else "BEARISH",
            "contrarian_forecast": "BULLISH" if contra > 0 else "BEARISH",
            "actual_direction": "BULLISH" if actual > 0 else "BEARISH",
            "contrarian_correct": contra == actual,
            "crowd_follow_correct": crowd == actual,
            "contrarian_signed_return_pct": round(contra * move, 6),
        })

    def summary(items):
        n = len(items)
        if not n:
            return {"sample_count": 0, "contrarian_accuracy_pct": None,
                    "crowd_follow_accuracy_pct": None, "average_next_return_pct": None,
                    "average_contrarian_signed_return_pct": None}
        wins = sum(x["contrarian_correct"] for x in items)
        follow = sum(x["crowd_follow_correct"] for x in items)
        return {
            "sample_count": n, "contrarian_correct": wins,
            "contrarian_accuracy_pct": round(100 * wins / n, 2),
            "crowd_follow_correct": follow,
            "crowd_follow_accuracy_pct": round(100 * follow / n, 2),
            "average_next_return_pct": round(sum(x["next_session_return_pct"] for x in items) / n, 6),
            "average_contrarian_signed_return_pct": round(sum(x["contrarian_signed_return_pct"] for x in items) / n, 6),
        }

    grouped = defaultdict(list)
    for trade in trades:
        grouped[trade["asset"]].append(trade)
    return {
        "mode": "offline_close_to_close_contrarian_backtest",
        "provider_calls": 0, "production_score_modified": False,
        "signal_convention": "positive score = bullish crowd; negative score = bearish crowd",
        "forecast_rule": "contrarian direction = opposite of crowd score",
        "threshold": threshold, "summary": summary(trades),
        "by_asset": {asset: summary(rows) for asset, rows in sorted(grouped.items())},
        "skipped": skipped, "malformed_signal_rows": bad_signals,
        "malformed_price_rows": bad_prices, "trades": trades,
        "limitations": [
            "Results depend on the quality and completeness of supplied dated signal and close archives.",
            "Signals must be end-of-session snapshots; intraday signals require intraday entry prices.",
            "Direction accuracy is not option-premium profitability; costs, slippage and expiry are not modeled.",
            "Small samples are descriptive and do not establish predictive edge.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("signals", help="JSON list of dated signal rows")
    parser.add_argument("closes", help="JSON list of dated close rows")
    parser.add_argument("--threshold", type=float, default=1.0)
    parser.add_argument("--out", default="-", help="report path, or - for stdout")
    args = parser.parse_args()
    result = run_contrarian_backtest(
        json.loads(Path(args.signals).read_text(encoding="utf-8")),
        json.loads(Path(args.closes).read_text(encoding="utf-8")),
        threshold=args.threshold,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(rendered)
    else:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
