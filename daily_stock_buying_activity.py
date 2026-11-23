"""Build TRINETRA Daily Stock Buying Activity from official NSE EOD archives.

Cash price/volume, same-expiry stock futures OI, and delivery are joined only
when their exchange dates and symbol keys match. No institutional identity or
intraday entry timing is inferred.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

ARCHIVE = Path("nse_cm_bhavcopy_archive.json")
MASTER = Path("nse-fo-stock-sector-master.json")
OUTPUT = Path("daily_stock_buying_activity.json")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc


def finite_number(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def futures_oi_metrics(current_contracts, previous_contracts, as_of_date):
    """Compare active-contract aggregate OI while using the front active expiry for price.

    Expiring contracts are excluded on their expiry date. Summing OI across the
    same set of still-active expiries prevents routine near-month rollover from
    being misclassified as market-wide OI unwinding.
    """
    if not isinstance(current_contracts, dict) or not isinstance(previous_contracts, dict):
        return None, "missing_snapshot"
    active_expiries = sorted(
        expiry for expiry in set(current_contracts) & set(previous_contracts)
        if expiry > as_of_date
    )
    if not active_expiries:
        return None, "no_common_expiry"

    current_oi_values = [
        finite_number(current_contracts[expiry].get("open_interest"))
        for expiry in active_expiries
        if isinstance(current_contracts.get(expiry), dict)
    ]
    previous_oi_values = [
        finite_number(previous_contracts[expiry].get("open_interest"))
        for expiry in active_expiries
        if isinstance(previous_contracts.get(expiry), dict)
    ]
    if (len(current_oi_values) != len(active_expiries)
            or len(previous_oi_values) != len(active_expiries)
            or any(value is None or value < 0 for value in current_oi_values + previous_oi_values)):
        return None, "invalid_contract"
    current_oi = sum(current_oi_values)
    previous_oi = sum(previous_oi_values)
    front_expiry = active_expiries[0]
    current_close = finite_number(current_contracts[front_expiry].get("close"))
    previous_close = finite_number(previous_contracts[front_expiry].get("close"))
    if (previous_oi <= 0 or current_close is None or current_close <= 0
            or previous_close is None or previous_close <= 0):
        return None, "invalid_contract"
    return {
        "expiry": front_expiry,
        "oi_expiries": active_expiries,
        "oi_expiry_count": len(active_expiries),
        "oi_change_pct": round((current_oi / previous_oi - 1.0) * 100.0, 2),
        "futures_change_pct": round((current_close / previous_close - 1.0) * 100.0, 2),
    }, "verified"


def build_price_volume_outcomes(sessions, session_maps):
    """Reconstruct EOD price/volume alerts and score only completed 1/3/5-session outcomes."""
    history = []
    summary = {
        horizon: {"right": 0, "wrong": 0, "stable": 0, "pending": 0}
        for horizon in (1, 3, 5)
    }
    for index in range(1, len(sessions)):
        current_map = session_maps[index]
        for symbol, row in current_map.items():
            close = finite_number(row.get("close"))
            previous = finite_number(row.get("previous_close"))
            volume = finite_number(row.get("volume"))
            if close is None or previous is None or previous <= 0 or volume is None or volume <= 0:
                continue
            prior_volumes = [
                finite_number(session_maps[j][symbol].get("volume"))
                for j in range(max(0, index - 20), index)
                if symbol in session_maps[j]
            ]
            prior_volumes = [value for value in prior_volumes if value is not None and value >= 0]
            if not prior_volumes:
                continue
            average = sum(prior_volumes) / len(prior_volumes)
            if average <= 0 or volume / average < 1.5:
                continue
            change_pct = (close / previous - 1.0) * 100.0
            direction = "BUY" if change_pct >= 0.2 else "SELL" if change_pct <= -0.2 else "NEUTRAL"
            outcomes = {}
            for horizon in (1, 3, 5):
                future_index = index + horizon
                if future_index >= len(sessions):
                    status = "PENDING"
                else:
                    future_row = session_maps[future_index].get(symbol)
                    future_close = finite_number(future_row.get("close")) if future_row else None
                    if future_close is None or close <= 0:
                        status = "PENDING"
                    elif direction == "NEUTRAL":
                        status = "NOT SCORED"
                    else:
                        forward_return = (future_close / close - 1.0) * 100.0
                        if abs(forward_return) < 0.000001:
                            status = "STABLE"
                        elif (direction == "BUY" and forward_return > 0) or (direction == "SELL" and forward_return < 0):
                            status = "RIGHT"
                        else:
                            status = "WRONG"
                outcomes[str(horizon) + "D"] = status
                if status in ("RIGHT", "WRONG", "STABLE", "PENDING"):
                    summary[horizon][status.lower()] += 1
            history.append({
                "date": sessions[index]["date"], "symbol": symbol,
                "direction": direction,
                "signal": "EARLY BUYING WATCH" if direction == "BUY" else "SELLING WATCH" if direction == "SELL" else "UNUSUAL ACTIVITY WATCH",
                "change_pct": round(change_pct, 2),
                "volume_ratio": round(volume / average, 2),
                "average_volume_sessions": len(prior_volumes),
                "outcomes": outcomes,
                "basis": "NSE cash EOD price-volume; not institutional attribution",
            })
    history.sort(key=lambda item: (item["date"], item["symbol"]), reverse=True)
    # Keep every scored record so the dashboard's clickable outcome counts
    # can open the exact matching stock list instead of an incomplete 200-row sample.
    return history, summary


def build_report(archive, master, generated_at=None, fo_archive=None, delivery_archive=None, deals_archive=None):
    records = archive.get("records") if isinstance(archive, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError("NSE CM archive has no usable sessions")
    sessions = sorted(
        (item for item in records if isinstance(item, dict)
         and isinstance(item.get("equity_rows"), list)
         and item.get("date")),
        key=lambda item: item["date"],
    )
    if not sessions:
        raise ValueError("NSE CM archive has no dated EQ rows")
    latest = sessions[-1]
    latest_date = dt.date.fromisoformat(str(latest["date"]))
    prior_sessions = [item for item in sessions[:-1] if item.get("equity_rows")]
    fno_symbols = set((master.get("stocks") or {}).keys())
    history = {}
    for session in prior_sessions[-20:]:
        for row in session["equity_rows"]:
            symbol = str(row.get("symbol") or "").upper()
            volume = finite_number(row.get("volume"))
            if symbol and volume is not None and volume >= 0:
                history.setdefault(symbol, []).append(volume)

    fo_records = (fo_archive or {}).get("records", []) if isinstance(fo_archive, dict) else []
    previous_cash_date = sessions[-2]["date"] if len(sessions) >= 2 else None
    previous_fo = next((record for record in reversed(fo_records)
                        if isinstance(record, dict) and record.get("date") == previous_cash_date), None)
    current_fo = next((record for record in reversed(fo_records)
                       if isinstance(record, dict) and record.get("date") == latest_date.isoformat()), None)
    current_futures = (current_fo or {}).get("stock_futures") or {}
    previous_futures = (previous_fo or {}).get("stock_futures") or {}

    delivery_records = (delivery_archive or {}).get("records", []) if isinstance(delivery_archive, dict) else []
    delivery_record = next((record for record in reversed(delivery_records)
                            if isinstance(record, dict) and record.get("date") == latest_date.isoformat()), None)
    delivery_rows = (delivery_record or {}).get("rows") or {}
    delivery_history_by_symbol = {}
    for record in delivery_records:
        if not isinstance(record, dict) or record.get("date") >= latest_date.isoformat():
            continue
        for symbol, values in (record.get("rows") or {}).items():
            if not isinstance(values, dict):
                continue
            delivery_pct = finite_number(values.get("delivery_pct"))
            if delivery_pct is not None and 0 <= delivery_pct <= 100:
                delivery_history_by_symbol.setdefault(str(symbol).upper(), []).append(delivery_pct)
    session_maps = [
        {str(row.get("symbol") or "").upper(): row for row in session.get("equity_rows", [])
         if isinstance(row, dict) and row.get("symbol")}
        for session in sessions
    ]
    signal_history, outcome_summary = build_price_volume_outcomes(sessions, session_maps)

    def consecutive_activity_days(symbol):
        streak = 0
        for index in range(len(sessions) - 1, -1, -1):
            current_row = session_maps[index].get(symbol)
            if not current_row:
                break
            current_volume = finite_number(current_row.get("volume"))
            prior_values = [
                finite_number(session_maps[j][symbol].get("volume"))
                for j in range(max(0, index - 20), index)
                if symbol in session_maps[j]
            ]
            prior_values = [value for value in prior_values if value is not None and value >= 0]
            average = sum(prior_values) / len(prior_values) if prior_values else None
            if current_volume is None or average is None or average <= 0 or current_volume / average < 1.5:
                break
            streak += 1
        return streak

    deals_records = (deals_archive or {}).get("records", []) if isinstance(deals_archive, dict) else []
    deals_record = next((record for record in reversed(deals_records)
                         if isinstance(record, dict) and record.get("date") == latest_date.isoformat()), None)
    # Keep the latest-session rows separate for signal matching: an older disclosed
    # deal must never be attached to today's price/OI signal. The history table must
    # preserve every archived deal row, even when its date or verification metadata
    # is missing; missing dates are a display fallback, never a reason to drop a deal.
    current_deal_rows = (deals_record or {}).get("rows") or []
    deal_rows = []
    for deal_record in deals_records:
        if not isinstance(deal_record, dict):
            continue
        report_date = deal_record.get("date")
        for deal in deal_record.get("rows") or []:
            if isinstance(deal, dict):
                deal_rows.append({**deal, "date": deal.get("date") or report_date})
    # Keep dated history newest-first; rows without a usable date remain visible at the end.
    deal_rows.sort(key=lambda deal: str(deal.get("date") or ""), reverse=True)
    deals_by_symbol = {}
    for deal in current_deal_rows:
        if not isinstance(deal, dict):
            continue
        symbol = str(deal.get("symbol") or "").upper()
        side = str(deal.get("side") or "").upper()
        if symbol and side in ("BUY", "SELL"):
            deals_by_symbol.setdefault(symbol, []).append(deal)

    rows = []
    for item in latest["equity_rows"]:
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        close = finite_number(item.get("close"))
        previous = finite_number(item.get("previous_close"))
        volume = finite_number(item.get("volume"))
        if close is None or previous is None or previous <= 0:
            continue
        change_pct = (close / previous - 1.0) * 100.0
        prior_volumes = history.get(symbol, [])
        avg_volume = (sum(prior_volumes) / len(prior_volumes)) if prior_volumes else None
        volume_ratio = (volume / avg_volume) if volume is not None and avg_volume and avg_volume > 0 else None
        volume_alert_eligible = volume_ratio is not None and volume_ratio >= 1.5
        current_stock = current_futures.get(symbol) or {}
        prior_stock = previous_futures.get(symbol) or {}
        futures_change_pct = None
        oi_change_pct = None
        futures_expiry = None
        # Compare total OI across the same set of active expiries so routine
        # rollover out of the near month is not mistaken for broad unwinding.
        metrics, _ = futures_oi_metrics(
            current_stock.get("by_expiry") or {},
            prior_stock.get("by_expiry") or {},
            latest_date.isoformat(),
        )
        if metrics:
            futures_expiry = metrics["expiry"]
            oi_change_pct = metrics["oi_change_pct"]
            futures_change_pct = metrics["futures_change_pct"]
        volume_baseline_note = (
            str(len(prior_volumes)) + " उपलब्ध पिछले सत्रों के औसत से कम-से-कम 1.5 गुना कैश वॉल्यूम"
        )
        if futures_change_pct is not None and oi_change_pct is not None:
            if futures_change_pct > 0 and oi_change_pct > 0:
                signal, strength = "LONG BUILD-UP", "WATCH"
            elif futures_change_pct < 0 and oi_change_pct > 0:
                signal, strength = "SHORT BUILD-UP", "WATCH"
            elif futures_change_pct > 0 and oi_change_pct < 0:
                signal, strength = "SHORT COVERING", "WATCH"
            elif futures_change_pct < 0 and oi_change_pct < 0:
                signal, strength = "LONG UNWINDING", "WATCH"
            else:
                signal, strength = (
                    ("UNUSUAL ACTIVITY WATCH", "EARLY") if volume_alert_eligible
                    else ("NO SIGNAL", "EARLY")
                )
            evidence = ["Futures भाव और सभी उपलब्ध active expiries का संयुक्त OI उपलब्ध",
                        volume_baseline_note if volume_alert_eligible else ("कैश वॉल्यूम उपलब्ध नहीं; Futures संकेत स्वतंत्र रूप से उपलब्ध" if volume is None else "कैश वॉल्यूम 1.5x सीमा पर नहीं; Futures संकेत स्वतंत्र रूप से उपलब्ध" if futures_change_pct != 0 and oi_change_pct != 0 else "कैश वॉल्यूम 1.5x सीमा पर नहीं; Futures भाव/OI में स्पष्ट दिशात्मक संयोजन नहीं")]
        elif volume_alert_eligible and change_pct >= 0.2:
            signal, strength = "EARLY BUYING WATCH", "EARLY"
            evidence = ["भाव सकारात्मक", volume_baseline_note]
        elif volume_alert_eligible and change_pct <= -0.2:
            signal, strength = "SELLING WATCH", "EARLY"
            evidence = ["भाव नकारात्मक", volume_baseline_note]
        elif volume_alert_eligible:
            signal, strength = "UNUSUAL ACTIVITY WATCH", "EARLY"
            evidence = ["भाव में स्पष्ट दिशा अभी नहीं", volume_baseline_note]
        else:
            signal, strength = "NO SIGNAL", "EARLY"
            evidence = []

        current_delivery_pct = finite_number((delivery_rows.get(symbol) or {}).get("delivery_pct"))
        prior_delivery_values = delivery_history_by_symbol.get(symbol, [])[-20:]
        avg_delivery_pct = (sum(prior_delivery_values) / len(prior_delivery_values)) if prior_delivery_values else None
        delivery_watch = (
            current_delivery_pct is not None and avg_delivery_pct is not None
            and current_delivery_pct >= 40.0
            and current_delivery_pct >= avg_delivery_pct + 10.0
        )
        if delivery_watch and signal in ("EARLY BUYING WATCH", "UNUSUAL ACTIVITY WATCH", "NO SIGNAL"):
            signal, strength = "DELIVERY WATCH", "WATCH"
            evidence.append(
                "Delivery % अपने उपलब्ध पिछले सत्रों के औसत से "
                + str(round(current_delivery_pct - avg_delivery_pct, 1))
                + " प्रतिशत-अंक अधिक; यह खरीददार की पहचान नहीं बताता"
            )

        symbol_deals = deals_by_symbol.get(symbol, [])
        matching_deals = [
            deal for deal in symbol_deals
            if (signal in ("LONG BUILD-UP", "SHORT COVERING", "EARLY BUYING WATCH", "DELIVERY WATCH") and deal.get("side") == "BUY")
            or (signal in ("SHORT BUILD-UP", "LONG UNWINDING", "SELLING WATCH") and deal.get("side") == "SELL")
            or (signal == "NO SIGNAL" and deal.get("side") in ("BUY", "SELL"))
        ]
        deal_evidence = [
            {
                "date": deal.get("date") or latest_date.isoformat(),
                "kind": deal.get("kind"),
                "side": deal.get("side"),
                "client": deal.get("client"),
                "quantity": deal.get("quantity"),
                "price": deal.get("price"),
            }
            for deal in matching_deals
        ]
        if matching_deals:
            if signal == "NO SIGNAL":
                sides = {deal.get("side") for deal in matching_deals}
                signal = "DISCLOSED DEAL ACTIVITY WATCH" if len(sides) > 1 else (
                    "DISCLOSED BUY DEAL WATCH" if "BUY" in sides else "DISCLOSED SELL DEAL WATCH"
                )
                strength = "WATCH"
                evidence.append("NSE की उसी तारीख की disclosed deal report में सौदा दर्ज")
            disclosed_types = sorted({str(deal.get("kind") or "NSE").upper() for deal in matching_deals})
            if signal == "LONG BUILD-UP":
                strength = "STRONG"
                evidence.append("उसी दिशा में NSE disclosed " + "/".join(disclosed_types) + " BUY deal")
            elif signal == "SHORT BUILD-UP":
                strength = "STRONG"
                evidence.append("उसी दिशा में NSE disclosed " + "/".join(disclosed_types) + " SELL deal")
            elif signal == "EARLY BUYING WATCH":
                strength = "WATCH"
                evidence.append("NSE disclosed BUY deal भी दर्ज")
            elif signal == "SELLING WATCH":
                strength = "WATCH"
                evidence.append("NSE disclosed SELL deal भी दर्ज")
            elif signal == "DELIVERY WATCH":
                strength = "WATCH"
                evidence.append("NSE disclosed BUY deal भी दर्ज; Delivery और disclosed deal अलग-अलग प्रमाण हैं")
            elif signal == "SHORT COVERING":
                strength = "WATCH"
                evidence.append("NSE disclosed BUY deal भी दर्ज; Short Covering नया Long Build-up नहीं है")
            elif signal == "LONG UNWINDING":
                strength = "WATCH"
                evidence.append("NSE disclosed SELL deal भी दर्ज; Long Unwinding नया Short Build-up नहीं है")

        if signal == "NO SIGNAL":
            continue

        rows.append({
            "symbol": symbol,
            "category": "F&O" if symbol in fno_symbols else "अन्य NSE",
            "new_discovery": symbol not in fno_symbols,
            "activity_days": consecutive_activity_days(symbol),
            "price": close,
            "change_pct": round(change_pct, 2),
            "oi_change_pct": oi_change_pct,
            "futures_change_pct": futures_change_pct,
            "futures_expiry": futures_expiry,
            "delivery_pct": (delivery_rows.get(symbol) or {}).get("delivery_pct"),
            "delivery_qty": (delivery_rows.get(symbol) or {}).get("delivery_qty"),
            "delivery_avg_pct_20": round(avg_delivery_pct, 2) if avg_delivery_pct is not None else None,
            "volume": int(volume) if volume is not None else None,
            "average_volume_20": round(avg_volume, 2) if avg_volume is not None else None,
            "average_volume_sessions": len(prior_volumes),
            "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
            "signal": signal,
            "strength": strength,
            "evidence": evidence,
            "deal_evidence": deal_evidence,
            "source": "NSE CM-UDiFF Common Bhavcopy Final",
            "as_of": latest_date.isoformat(),
            "missing_fields": ([] if oi_change_pct is not None else ["Futures OI" if symbol in fno_symbols else "Futures OI लागू नहीं"])
                              + ([] if volume is not None else ["Cash Volume"])
                              + ([] if avg_volume is not None else ["Cash Volume baseline"])
                              + ([] if (delivery_rows.get(symbol) or {}).get("delivery_pct") is not None else ["Security-wise Delivery %"]),
        })
    strength_order = {"STRONG": 0, "WATCH": 1, "EARLY": 2}
    rows.sort(key=lambda row: (
        strength_order.get(row["strength"], 3),
        -(row["volume_ratio"] or 0),
        -abs(row["change_pct"]),
        row["symbol"],
    ))
    # Source coverage is measured across the scanned universe, not only alert rows.
    # Otherwise a quiet market day would incorrectly look like disconnected data.
    fno_futures_oi_matched = 0
    fno_same_expiry_pairs = 0
    fno_no_common_expiry = 0
    fno_missing_snapshot = 0
    fno_invalid_contract_values = 0
    for symbol in fno_symbols:
        current_stock = current_futures.get(symbol) or {}
        prior_stock = previous_futures.get(symbol) or {}
        # Count coverage from validated exact-expiry rows, independently of other
        # invalid contracts recorded for the same symbol.
        if not isinstance(current_stock.get("by_expiry"), dict) or not isinstance(prior_stock.get("by_expiry"), dict):
            fno_missing_snapshot += 1
            continue
        current_contracts = current_stock.get("by_expiry") or {}
        prior_contracts = prior_stock.get("by_expiry") or {}
        metrics, status = futures_oi_metrics(
            current_contracts, prior_contracts, latest_date.isoformat()
        )
        if status == "no_common_expiry":
            fno_no_common_expiry += 1
            continue
        if status == "missing_snapshot":
            fno_missing_snapshot += 1
            continue
        fno_same_expiry_pairs += 1
        if metrics:
            fno_futures_oi_matched += 1
        else:
            fno_invalid_contract_values += 1

    long_build_up_watch = sum(1 for row in rows if row.get("signal") == "LONG BUILD-UP")
    short_build_up_watch = sum(1 for row in rows if row.get("signal") == "SHORT BUILD-UP")
    directional_build_up_with_deal = sum(
        1 for row in rows
        if row.get("signal") in ("LONG BUILD-UP", "SHORT BUILD-UP")
        and row.get("deal_evidence")
    )
    directional_build_up_without_deal = long_build_up_watch + short_build_up_watch - directional_build_up_with_deal
    strong_count = sum(1 for row in rows if row.get("strength") == "STRONG")

    latest_eq_symbols = {
        str(item.get("symbol") or "").upper()
        for item in latest.get("equity_rows", [])
        if isinstance(item, dict) and item.get("symbol")
    }
    delivery_eq_matched = sum(
        1 for symbol in latest_eq_symbols
        if finite_number((delivery_rows.get(symbol) or {}).get("delivery_pct")) is not None
    )
    cash_quote_valid = sum(
        1 for item in latest.get("equity_rows", [])
        if finite_number(item.get("close")) is not None
        and finite_number(item.get("previous_close")) is not None
        and finite_number(item.get("previous_close")) > 0
        and finite_number(item.get("volume")) is not None
    )

    return {
        "schema_version": 1,
        "generated_at": generated_at or dt.datetime.now(IST).isoformat(timespec="seconds"),
        "as_of": latest_date.isoformat(),
        "source": "NSE India official CM-UDiFF Common Bhavcopy Final",
        "universe": {
            "fno_symbols_in_master": len(fno_symbols),
            "nse_eq_symbols_scanned": len(latest["equity_rows"]),
            "qualifying_activity_rows": len(rows),
            "other_nse_rows": sum(row["category"] == "अन्य NSE" for row in rows),
        },
        "rows": rows,
        "strength_summary": {
            level: sum(1 for row in rows if row.get("strength") == level)
            for level in ("STRONG", "WATCH", "EARLY")
        },
        "strong_diagnostics": {
            "rule": "LONG BUILD-UP plus same-session NSE disclosed BUY, or SHORT BUILD-UP plus same-session NSE disclosed SELL",
            "fno_universe": len(fno_symbols),
            "current_fo_record_date": (current_fo or {}).get("date"),
            "previous_fo_record_date": (previous_fo or {}).get("date"),
            "current_fo_symbol_records": len(current_futures),
            "previous_fo_symbol_records": len(previous_futures),
            "same_expiry_pairs": fno_same_expiry_pairs,
            "usable_same_expiry_pairs": fno_futures_oi_matched,
            "missing_snapshot_symbols": fno_missing_snapshot,
            "no_common_expiry_symbols": fno_no_common_expiry,
            "invalid_contract_symbols": fno_invalid_contract_values,
            "long_build_up_watch": long_build_up_watch,
            "short_build_up_watch": short_build_up_watch,
            "directional_build_up_with_deal": directional_build_up_with_deal,
            "directional_build_up_without_deal": directional_build_up_without_deal,
            "strong_count": strong_count,
        },
        "signal_history": signal_history,
        "outcome_summary": outcome_summary,
        "bulk_block_deals": deal_rows,
        "coverage": {
            "cash_price_volume": "verified",
            "futures_oi": "verified_for_matched_stock_futures" if fno_futures_oi_matched else "not_yet_connected",
            "delivery_pct": ("verified_for_matched_symbols" if delivery_eq_matched else "record_without_valid_symbol_matches" if delivery_record else "not_yet_connected"),
            "bulk_block_deals": ("verified" if deals_record and (deals_record.get("verified_report_count") or 0) == 2
                                 else "partial" if deals_record and (deals_record.get("verified_report_count") or 0) == 1
                                 else "not_yet_connected"),
            "intraday": "not_available_in_this_eod_scan",
        },
        "coverage_counts": {
            "nse_eq_symbols_scanned": len(latest_eq_symbols),
            "cash_quote_valid_symbols": cash_quote_valid,
            "fno_symbols_in_master": len(fno_symbols),
            "fno_symbols_with_same_expiry_oi": fno_futures_oi_matched,
            "delivery_symbols_matched": delivery_eq_matched,
            "delivery_eq_symbols_scanned": len(latest_eq_symbols) if delivery_record else 0,
            "bulk_block_reports_verified": int((deals_record or {}).get("verified_report_count") or 0),
            "bulk_block_deal_rows": len(deal_rows),
        },
        "note": "EARLY is an EOD price-volume alert, not proof of institutional buying or a buy recommendation. Delivery and OI are shown only when verified.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default=str(ARCHIVE))
    parser.add_argument("--master", default=str(MASTER))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--fo-archive", default="nse_index_option_oi.json")
    parser.add_argument("--delivery-archive", default="nse_delivery_archive.json")
    parser.add_argument("--deals-archive", default="nse_bulk_block_deals.json")
    args = parser.parse_args()
    fo_path = Path(args.fo_archive)
    delivery_path = Path(args.delivery_archive)
    deals_path = Path(args.deals_archive)
    fo_archive = read_json(fo_path) if fo_path.exists() else None
    delivery_archive = read_json(delivery_path) if delivery_path.exists() else None
    deals_archive = read_json(deals_path) if deals_path.exists() else None
    report = build_report(read_json(Path(args.archive)), read_json(Path(args.master)),
                          fo_archive=fo_archive, delivery_archive=delivery_archive,
                          deals_archive=deals_archive)
    target = Path(args.output)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps({"as_of": report["as_of"], "scanned": report["universe"]["nse_eq_symbols_scanned"],
                      "alerts": len(report["rows"]), "other_nse_alerts": report["universe"]["other_nse_rows"],
                      "oi": report["coverage"]["futures_oi"], "delivery": report["coverage"]["delivery_pct"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
