#!/usr/bin/env python3
"""Research-only ATM +/- strike-window backtest using committed official EOD archives.

Signal: same-expiry, same-strike, same-side premium/OI change from prior close
to signal-day close, weighted by absolute change in OI quantity.
Outcome: next official archived index close versus signal-day close.

This is a close-to-close direction study, NOT an executable option-premium P&L
backtest. It never changes production data.json or any dashboard score.
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path

DEFAULT_OI = Path("nse_index_option_oi.json")
DEFAULT_NSE_CLOSE = Path("nse_index_close_archive.json")
DEFAULT_OUT = Path("atm_option_window_backtest_report.json")
SYMBOL_INDEX_NAMES = {"NIFTY": ("Nifty 50",), "BANKNIFTY": ("Nifty Bank",)}
WINDOWS = (5, 10)
DISTANCE_BANDS = (("ATM", 0, 0), ("ATM_1_2", 1, 2), ("ATM_3_5", 3, 5), ("ATM_6_10", 6, 10))
EXPECTED_STRIKE_STEP = {"NIFTY": 50.0, "BANKNIFTY": 100.0}

def _date(value):
    text = str(value or "").strip()
    return text if len(text) == 10 and text[4] == "-" and text[7] == "-" else None

def _finite(value):
    try: number = float(value)
    except (TypeError, ValueError, OverflowError): return None
    return number if math.isfinite(number) else None

def _direction(value):
    return "UP" if value > 0 else "DOWN" if value < 0 else "FLAT"

def _index_close(record, symbol):
    indices = record.get("indices") if isinstance(record, dict) else None
    if not isinstance(indices, dict): return None
    for name in SYMBOL_INDEX_NAMES[symbol]:
        value = _finite(indices.get(name))
        if value is not None and value > 0: return value
    return None

def _contract_map(record, symbol):
    section = (record.get("option_contracts") or {}).get(symbol) if isinstance(record, dict) else None
    rows = section.get("contracts") if isinstance(section, dict) else None
    if not isinstance(rows, list): return {}
    result = {}
    for row in rows:
        if not isinstance(row, dict): continue
        expiry, side = _date(row.get("expiry")), str(row.get("side") or "").upper()
        strike, close, oi = _finite(row.get("strike")), _finite(row.get("close")), _finite(row.get("open_interest"))
        if not expiry or side not in ("CE", "PE") or strike is None or strike <= 0: continue
        if close is None or close <= 0 or oi is None or oi < 0 or not oi.is_integer(): continue
        key = (expiry, round(strike, 4), side)
        if key in result: raise ValueError(f"duplicate option contract key: {symbol} {key}")
        result[key] = {"close": close, "open_interest": int(oi)}
    return result

def _classify(side, premium_change, oi_change):
    if premium_change > 0 and oi_change > 0: category = "long_build_up"
    elif premium_change < 0 and oi_change > 0: category = "short_build_up"
    elif premium_change > 0 and oi_change < 0: category = "short_covering"
    elif premium_change < 0 and oi_change < 0: category = "long_unwinding"
    else: return None, None
    bullish = ((side == "CE" and category in ("long_build_up", "short_covering"))
               or (side == "PE" and category in ("short_build_up", "long_unwinding")))
    return category, "bullish" if bullish else "bearish"

def score_window(previous_record, signal_record, symbol, spot_close, steps):
    previous, current = _contract_map(previous_record, symbol), _contract_map(signal_record, symbol)
    signal_date = _date(signal_record.get("date"))
    if not previous or not current or not signal_date:
        return {"available": False, "reason": "contract_archive_missing_or_invalid"}
    common_expiries = sorted({expiry for expiry, _, _ in current
        if expiry > signal_date and any(old_expiry == expiry for old_expiry, _, _ in previous)})
    if not common_expiries: return {"available": False, "reason": "no_common_unexpired_expiry"}
    expiry = common_expiries[0]
    # Build the strike ladder from every listed strike for this expiry. Do not
    # silently remove a strike with a missing CE/PE leg and then substitute a
    # farther strike; selected-window completeness is checked below.
    current_strikes = sorted({strike for exp, strike, _side in current if exp == expiry})
    if not current_strikes: return {"available": False, "reason": "no_listed_strikes_for_expiry"}
    atm = min(current_strikes, key=lambda strike: (abs(strike - spot_close), strike))
    atm_index = current_strikes.index(atm)
    selected = current_strikes[max(0, atm_index-steps):atm_index+steps+1]
    required = 2*steps+1
    expected_step = EXPECTED_STRIKE_STEP.get(symbol)
    if expected_step is None:
        return {"available": False, "reason": "unknown_official_strike_step", "expiry": expiry}
    if any(abs((right-left)-expected_step) > 1e-6 for left, right in zip(selected, selected[1:])):
        return {"available": False, "reason": "non_contiguous_strike_ladder",
                "atm_strike": atm, "selected_strikes": selected,
                "expected_strike_step": expected_step, "expiry": expiry}
    if len(selected) != required:
        return {"available": False, "reason": "insufficient_symmetric_strike_coverage",
                "atm_strike": atm, "available_strikes": len(selected), "required_strikes": required,
                "expiry": expiry}
    totals = {side: {"bullish_oi_change": 0, "bearish_oi_change": 0, "classified_contracts": 0}
              for side in ("CE", "PE")}
    category_totals, matched = {}, 0
    unclassified_contracts, exclusion_counts = [], {}
    band_totals = {
        name: {"bullish_oi_change_quantity": 0, "bearish_oi_change_quantity": 0,
               "classified_contracts": 0, "matched_contracts": 0,
               "category_oi_change_quantity": {}, "by_side": {
                   side: {"bullish_oi_change_quantity": 0, "bearish_oi_change_quantity": 0,
                          "classified_contracts": 0} for side in ("CE", "PE")}}
        for name, low, high in DISTANCE_BANDS if high <= steps
    }
    contract_details = []
    for strike_index, strike in enumerate(selected):
        distance = abs(strike_index - steps)
        band_name = next(name for name, low, high in DISTANCE_BANDS if low <= distance <= high)
        band = band_totals[band_name]
        for side in ("CE", "PE"):
            key = (expiry, strike, side)
            before, after = previous.get(key), current.get(key)
            if before is None or after is None:
                return {"available": False, "reason": "incomplete_contract_pair", "expiry": expiry}
            matched += 1
            band["matched_contracts"] += 1
            premium_change = after["close"] - before["close"]
            oi_change = after["open_interest"] - before["open_interest"]
            category, direction = _classify(side, premium_change, oi_change)
            if direction is None:
                zero_premium = premium_change == 0
                zero_oi = oi_change == 0
                reason = ("ZERO_PREMIUM_AND_OI_CHANGE" if zero_premium and zero_oi
                          else "ZERO_PREMIUM_CHANGE" if zero_premium
                          else "ZERO_OI_CHANGE")
                exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
                detail = {
                    "signal_date": signal_date, "symbol": symbol, "expiry": expiry,
                    "strike": strike, "side": side, "distance_from_atm_steps": distance,
                    "distance_band": band_name,
                    "previous_premium": before["close"], "current_premium": after["close"],
                    "premium_change": premium_change,
                    "previous_open_interest": before["open_interest"],
                    "current_open_interest": after["open_interest"], "oi_change": oi_change,
                    "reason": reason,
                }
                unclassified_contracts.append(detail)
                contract_details.append({**detail, "classified": False})
                continue
            quantity = abs(oi_change)
            bucket = totals[side]
            bucket["classified_contracts"] += 1
            bucket["bullish_oi_change" if direction == "bullish" else "bearish_oi_change"] += quantity
            category_totals[category] = category_totals.get(category, 0) + quantity
            band["classified_contracts"] += 1
            band["bullish_oi_change_quantity" if direction == "bullish" else "bearish_oi_change_quantity"] += quantity
            band["category_oi_change_quantity"][category] = band["category_oi_change_quantity"].get(category, 0) + quantity
            side_band = band["by_side"][side]
            side_band["classified_contracts"] += 1
            side_band["bullish_oi_change_quantity" if direction == "bullish" else "bearish_oi_change_quantity"] += quantity
            contract_details.append({
                "signal_date": signal_date, "symbol": symbol, "expiry": expiry,
                "strike": strike, "side": side, "distance_from_atm_steps": distance,
                "distance_band": band_name, "previous_premium": before["close"],
                "current_premium": after["close"], "premium_change": premium_change,
                "previous_open_interest": before["open_interest"],
                "current_open_interest": after["open_interest"], "oi_change": oi_change,
                "category": category, "direction": direction, "oi_change_quantity": quantity,
                "classified": True})
    distance_bands = {}
    for name, bucket in band_totals.items():
        band_bull, band_bear = bucket["bullish_oi_change_quantity"], bucket["bearish_oi_change_quantity"]
        band_net = band_bull - band_bear
        by_side = {}
        for side, side_bucket in bucket["by_side"].items():
            side_net = side_bucket["bullish_oi_change_quantity"] - side_bucket["bearish_oi_change_quantity"]
            by_side[side] = {**side_bucket, "net_bullish_minus_bearish_quantity": side_net,
                "signal": "BULLISH" if side_net > 0 else "BEARISH" if side_net < 0 else "NEUTRAL"}
        distance_bands[name] = {**bucket, "by_side": by_side,
            "net_bullish_minus_bearish_quantity": band_net,
            "signal": "BULLISH" if band_net > 0 else "BEARISH" if band_net < 0 else "NEUTRAL"}
    bull = sum(x["bullish_oi_change"] for x in totals.values())
    bear = sum(x["bearish_oi_change"] for x in totals.values())
    net, classified = bull-bear, sum(x["classified_contracts"] for x in totals.values())
    result = {"available": classified > 0,
        "reason": None if classified else "no_contracts_with_nonzero_premium_and_OI_changes",
        "expiry": expiry, "spot_close": round(spot_close, 6), "atm_strike": atm,
        "window_steps_each_side": steps, "selected_strikes": selected,
        "matched_contracts": matched, "classified_contracts": classified,
        "classification_coverage_pct": round(100*classified/matched, 2) if matched else 0,
        "bullish_oi_change_quantity": bull, "bearish_oi_change_quantity": bear,
        "net_bullish_minus_bearish_quantity": net,
        "signal": "BULLISH" if net > 0 else "BEARISH" if net < 0 else "NEUTRAL",
        "category_oi_change_quantity": category_totals,
        "classification_exclusions_by_reason": exclusion_counts,
        "unclassified_contracts": unclassified_contracts, "contract_details": contract_details,
        "distance_bands": distance_bands, "by_side": {}}
    for side, bucket in totals.items():
        side_net = bucket["bullish_oi_change"]-bucket["bearish_oi_change"]
        result["by_side"][side] = {**bucket, "net_bullish_minus_bearish_quantity": side_net,
            "signal": "BULLISH" if side_net > 0 else "BEARISH" if side_net < 0 else "NEUTRAL"}
    return result

def _summarize(observations, field):
    rows = [row for row in observations if row.get(field, {}).get("available")
            and row.get(field, {}).get("signal") in ("BULLISH", "BEARISH")
            and row.get("actual_direction") in ("UP", "DOWN")]
    correct = sum((r[field]["signal"] == "BULLISH" and r["actual_direction"] == "UP")
                  or (r[field]["signal"] == "BEARISH" and r["actual_direction"] == "DOWN") for r in rows)
    total = len(rows)
    return {"directional_samples": total, "crowd_follow_correct": correct,
        "crowd_follow_accuracy_pct": round(100*correct/total, 2) if total else None,
        "contrarian_correct": total-correct,
        "contrarian_accuracy_pct": round(100*(total-correct)/total, 2) if total else None}

def build_report(oi_archive, close_archive):
    oi_records = oi_archive.get("records") if isinstance(oi_archive, dict) else None
    close_records = close_archive.get("records") if isinstance(close_archive, dict) else None
    if not isinstance(oi_records, list) or not isinstance(close_records, list):
        raise ValueError("OI and NSE close archives must both contain records arrays")
    oi_by_date = {}
    for row in oi_records:
        if not isinstance(row, dict) or not _date(row.get("date")): continue
        day = row["date"]
        if day in oi_by_date: raise ValueError(f"duplicate OI archive date: {day}")
        oi_by_date[day] = row
    closes = {}
    for row in close_records:
        if not isinstance(row, dict) or not _date(row.get("date")): continue
        day = row["date"]
        if day in closes: raise ValueError(f"duplicate NSE close archive date: {day}")
        closes[day] = row
    close_dates = sorted(closes)
    by_asset = {}
    for symbol in ("NIFTY", "BANKNIFTY"):
        observations, skipped = [], {"missing_previous_or_current_OI": 0, "missing_spot_close": 0}
        for index in range(1, len(close_dates)-1):
            prev_date, signal_date, next_date = close_dates[index-1:index+2]
            previous_record, signal_record = oi_by_date.get(prev_date), oi_by_date.get(signal_date)
            if not previous_record or not signal_record:
                skipped["missing_previous_or_current_OI"] += 1
                continue
            spot, next_close = _index_close(closes[signal_date], symbol), _index_close(closes[next_date], symbol)
            if spot is None or next_close is None:
                skipped["missing_spot_close"] += 1
                continue
            change = next_close-spot
            observation = {"signal_date": signal_date, "next_session_date": next_date,
                "spot_close": round(spot, 6), "next_session_close": round(next_close, 6),
                "next_session_change": round(change, 6),
                "next_session_change_pct": round(100*change/spot, 4),
                "actual_direction": _direction(change), "windows": {}}
            for steps in WINDOWS:
                field = f"atm_plus_minus_{steps}"
                observation["windows"][field] = score_window(previous_record, signal_record, symbol, spot, steps)
            observations.append(observation)
        summaries = {}
        for steps in WINDOWS:
            field = f"atm_plus_minus_{steps}"
            summaries[field] = _summarize([{"actual_direction":r["actual_direction"],field:r["windows"][field]}
                                           for r in observations], field)
            for band_name in (name for name, low, high in DISTANCE_BANDS if high <= steps):
                band_rows = []
                for row in observations:
                    band_result = (row["windows"][field].get("distance_bands") or {}).get(band_name, {})
                    band_rows.append({"actual_direction": row["actual_direction"], field: {
                        "available": band_result.get("classified_contracts", 0) > 0
                                     and band_result.get("signal") in ("BULLISH", "BEARISH"),
                        "signal": band_result.get("signal")}})
                summaries[field][f"distance_{band_name.lower()}"] = _summarize(band_rows, field)
            for side in ("CE", "PE"):
                side_rows = []
                for row in observations:
                    window = row["windows"][field]
                    side_result = (window.get("by_side") or {}).get(side, {})
                    side_rows.append({"actual_direction":row["actual_direction"],field:{
                        "available":window.get("available",False) and side_result.get("signal") in ("BULLISH","BEARISH"),
                        "signal":side_result.get("signal")}})
                summaries[field][f"{side.lower()}_only"] = _summarize(side_rows, field)
        by_asset[symbol] = {"source":"NSE official F&O UDiFF Common Bhavcopy Final + NSE official Daily Snapshot",
            "observations":observations,"summary":summaries,"skipped":skipped}
    return {"status":"exploratory_only",
        "method":"same expiry + same strike + same CE/PE; prior EOD close versus signal-day EOD close; absolute OI change quantity weighted",
        "outcome":"next official NSE session index close versus signal-day index close",
        "evaluation_limit":"close-to-close direction only; not option premium P&L, entry-at-open, slippage, brokerage, or executable strategy",
        "atm_definition":"nearest listed strike to signal-day official index close; ATM plus/minus 5 or 10 listed strikes on each side, including ATM",
        "distance_band_definition":{"ATM":"0 strikes","ATM_1_2":"1-2 strikes from ATM","ATM_3_5":"3-5 strikes from ATM","ATM_6_10":"6-10 strikes from ATM"},
        "expiry_rule":"nearest common expiry strictly later than signal date; same expiry matched across both EOD sessions",
        "production_score_changed":False,"eligible_for_live_score":False,
        "sensex":{"status":"not_tested","reason":"NSE UDiFF option archive contains NIFTY and BANKNIFTY only; separate verified BSE SENSEX option-contract archive is required"},
        "oi_archive_sessions":len(oi_by_date),"oi_archive_first_date":min(oi_by_date) if oi_by_date else None,
        "oi_archive_last_date":max(oi_by_date) if oi_by_date else None,
        "nse_close_archive_sessions":len(close_dates),
        "nse_close_archive_first_date":close_dates[0] if close_dates else None,
        "nse_close_archive_last_date":close_dates[-1] if close_dates else None,
        "by_asset":by_asset}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--oi-archive",default=str(DEFAULT_OI))
    parser.add_argument("--close-archive",default=str(DEFAULT_NSE_CLOSE))
    parser.add_argument("--out",default=str(DEFAULT_OUT))
    args=parser.parse_args()
    oi=json.loads(Path(args.oi_archive).read_text(encoding="utf-8"))
    closes=json.loads(Path(args.close_archive).read_text(encoding="utf-8"))
    report=build_report(oi,closes)
    Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"oi_sessions":report["oi_archive_sessions"],
        "close_sessions":report["nse_close_archive_sessions"],
        "nifty_atm5":report["by_asset"]["NIFTY"]["summary"]["atm_plus_minus_5"],
        "nifty_atm10":report["by_asset"]["NIFTY"]["summary"]["atm_plus_minus_10"],
        "banknifty_atm5":report["by_asset"]["BANKNIFTY"]["summary"]["atm_plus_minus_5"],
        "banknifty_atm10":report["by_asset"]["BANKNIFTY"]["summary"]["atm_plus_minus_10"],
        "production_score_changed":False,"report":args.out},ensure_ascii=False,sort_keys=True))

if __name__ == "__main__": main()
