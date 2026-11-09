"""Research-only evaluation of cash-basket breadth against the next captured index close.

This deliberately does not alter production scores. A sample is paired only when
both the signal-session and next captured session have dated, valid index closes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

INDEX_KEYS = ("NIFTY", "BANKNIFTY", "SENSEX")


def _dated_close(record, index_key):
    if not isinstance(record, dict) or not isinstance(record.get("indices"), dict):
        return None
    item = record["indices"].get(index_key)
    if not isinstance(item, dict):
        return None
    try:
        close = float(item["close"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(close) or close <= 0:
        return None
    as_of = str(item.get("close_as_of") or "").strip()
    day = str(record.get("date") or "").strip()
    if as_of:
        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = dt.datetime.strptime(as_of, fmt).date().isoformat()
                break
            except ValueError:
                pass
        if parsed != day:
            return None
    try:
        dt.date.fromisoformat(day)
    except ValueError:
        return None
    return close


def _pearson(xs, ys):
    if len(xs) < 2:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy), 4)


def evaluate_cash_basket(diagnostics, market_history, min_samples=20):
    """Pair each complete breadth signal with the next captured close per index."""
    if min_samples < 2:
        raise ValueError("min_samples must be at least 2")
    diagnostic_rows = diagnostics.get("records", []) if isinstance(diagnostics, dict) else []
    history_rows = market_history.get("records", []) if isinstance(market_history, dict) else []
    history = sorted(
        (row for row in history_rows if isinstance(row, dict)),
        key=lambda row: str(row.get("date") or ""),
    )
    by_date = {str(row.get("date")): row for row in history if row.get("date")}
    output = {}
    for index_key in INDEX_KEYS:
        samples = []
        for diagnostic in diagnostic_rows:
            if not isinstance(diagnostic, dict):
                continue
            signal_date = str(diagnostic.get("date") or "")
            metric = (diagnostic.get("indices") or {}).get(index_key, {})
            if metric.get("status") != "complete_diagnostic":
                continue
            try:
                breadth_score = float(metric["score"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(breadth_score) or not -10 <= breadth_score <= 10:
                continue
            signal_row = by_date.get(signal_date)
            signal_close = _dated_close(signal_row, index_key)
            if signal_close is None:
                continue
            future_row = next((row for row in history if str(row.get("date") or "") > signal_date
                               and _dated_close(row, index_key) is not None), None)
            if future_row is None:
                continue
            future_close = _dated_close(future_row, index_key)
            forward_return = (future_close / signal_close - 1.0) * 100.0
            if not math.isfinite(forward_return):
                continue
            samples.append({
                "signal_date": signal_date,
                "next_captured_date": future_row["date"],
                "breadth_score": round(breadth_score, 2),
                "next_captured_return_pct": round(forward_return, 4),
            })
        scores = [row["breadth_score"] for row in samples]
        returns = [row["next_captured_return_pct"] for row in samples]
        directional = [(s, r) for s, r in zip(scores, returns) if s != 0 and r != 0]
        continuation_hits = sum((s > 0) == (r > 0) for s, r in directional)
        contrarian_hits = len(directional) - continuation_hits
        n = len(samples)
        output[index_key] = {
            "sample_count": n,
            "minimum_samples_required": min_samples,
            "status": "ready_for_research_review" if n >= min_samples else "insufficient_sample",
            "pearson_correlation": _pearson(scores, returns),
            "continuation_directional_hits": continuation_hits,
            "contrarian_directional_hits": contrarian_hits,
            "directional_sample_count": len(directional),
            "continuation_hit_rate_pct": round(100 * continuation_hits / len(directional), 2) if directional else None,
            "contrarian_hit_rate_pct": round(100 * contrarian_hits / len(directional), 2) if directional else None,
            "samples": samples,
            "research_only": True,
            "score_eligible": False,
        }
    return {
        "schema_version": 1,
        "indices": output,
        "minimum_samples_required": min_samples,
        "research_only": True,
        "score_eligible": False,
        "production_mutation": False,
        "note": "Next captured EOD close, not guaranteed to be the immediately following exchange session; review gaps before interpreting. Correlation and hit rates are descriptive, not proof of predictive power.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostics", default="index_cash_basket_diagnostics.json")
    parser.add_argument("--history", default="market_signal_history.json")
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--output", default="cash_basket_forward_evaluation.json")
    args = parser.parse_args()
    diagnostics = json.loads(Path(args.diagnostics).read_text(encoding="utf-8"))
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    result = evaluate_cash_basket(diagnostics, history, args.min_samples)
    target = Path(args.output)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps({
        "status": {key: value["status"] for key, value in result["indices"].items()},
        "sample_count": {key: value["sample_count"] for key, value in result["indices"].items()},
        "minimum_samples_required": args.min_samples,
        "research_only": True, "score_eligible": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
