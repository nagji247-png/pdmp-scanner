#!/usr/bin/env python3
"""Prospective, next-session-close performance ledger for TRINETRA signals.

The ledger is append-only: original signal snapshots are immutable. Results are
scored only from a later, completed NSE session snapshot (>= 15:45 IST).
"""
import json
import math
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
LEDGER = Path("signal_performance.json")
DATA = Path("data.json")
MASTER = Path("nse-fo-stock-sector-master.json")
DAILY = Path("daily_stock_buying_activity.json")
CONTRARIAN = Path("contrarian.json")
DEPARTMENTS = (
    "MARKET ACTIVITY RADAR",
    "LATEST ACTIVITY ALERTS",
    "SECTOR ACTIVITY",
    "DAILY STOCK BUYING ACTIVITY",
    "NEXT-SESSION REVERSAL",
)


def read_json(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if value is not None else default
    except (OSError, ValueError, TypeError):
        return default


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(IST).date()
    except ValueError:
        return None


def parse_stamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except ValueError:
        return None


def load_ledger():
    ledger = read_json(LEDGER, {})
    if not isinstance(ledger, dict) or ledger.get("schema_version") != 1:
        ledger = {"schema_version": 1, "updated_at": None, "events": []}
    if not isinstance(ledger.get("events"), list):
        ledger["events"] = []
    return ledger


def quote_map(data):
    result = {}
    for key in ("instruments",):
        if isinstance(data.get(key), dict):
            result.update(data[key])
    market = data.get("market_activity_quotes") or {}
    if isinstance(market.get("instruments"), dict):
        for symbol, quote in market["instruments"].items():
            if symbol not in result or not isinstance(result.get(symbol), dict):
                result[symbol] = quote
            elif result[symbol].get("type") != "stock" and isinstance(quote, dict):
                result[symbol] = quote
    return result


def valid_price(quote):
    if not isinstance(quote, dict):
        return None
    return number(quote.get("price"))


def direction_for_daily(row):
    signal = str(row.get("signal") or "")
    if signal in {"LONG BUILD-UP", "DISCLOSED BUY DEAL WATCH", "DELIVERY WATCH", "EARLY BUYING WATCH", "SHORT COVERING"}:
        return "BULLISH"
    if signal in {"SHORT BUILD-UP", "DISCLOSED SELL DEAL WATCH", "SELLING WATCH", "LONG UNWINDING"}:
        return "BEARISH"
    return None


def make_event(department, instrument, direction, signal_date, stamp, price=None, members=None, source="", details=None):
    if direction not in ("BULLISH", "BEARISH"):
        return None
    members = members or {}
    # One immutable record per department/instrument/direction/session.
    key = "|".join((department, signal_date.isoformat(), str(instrument), direction))
    return {
        "id": key,
        "department": department,
        "instrument": str(instrument),
        "direction": direction,
        "signal_date": signal_date.isoformat(),
        "signal_time_ist": stamp.isoformat(timespec="seconds") if stamp else None,
        "entry_price": round(price, 6) if price is not None else None,
        "member_prices": {k: round(v, 6) for k, v in members.items() if number(v) and number(v) > 0},
        "source": source or "TRINETRA verified snapshot",
        "details": details or {},
        "evaluation_date": None,
        "exit_price": None,
        "return_pct": None,
        "signed_return_pct": None,
        "status": "PENDING",
        "reason": "अगले ट्रेडिंग सेशन की सत्यापित क्लोजिंग बाकी",
    }


def collect_signals(data, master, daily, contrarian, fpi, stamp):
    signal_date = stamp.date()
    quotes = quote_map(data)
    known = master.get("stocks") if isinstance(master.get("stocks"), dict) else {}
    sectors = {}
    for symbol, info in known.items():
        sector = (info or {}).get("sector") or "सेक्टर उपलब्ध नहीं"
        price = valid_price(quotes.get(symbol))
        if price is not None and price > 0:
            sectors.setdefault(sector, {})[symbol] = price
    # Keep non-F&O NSE cash shares in the same unmapped bucket used by the radar.
    bulk = (data.get("market_activity_quotes") or {}).get("instruments") or {}
    for symbol, q in bulk.items():
        if symbol not in known and isinstance(q, dict) and q.get("type") == "stock":
            price = valid_price(q)
            if price is not None and price > 0:
                sectors.setdefault("सेक्टर मैपिंग उपलब्ध नहीं", {})[symbol] = price

    found = []
    for sector, members in sectors.items():
        ups = downs = 0
        for symbol in members:
            change = number((quotes.get(symbol) or {}).get("change_pct"))
            if change is not None:
                ups += change > 0
                downs += change < 0
        if ups != downs:
            direction = "BULLISH" if ups > downs else "BEARISH"
            details = {"advancers": ups, "decliners": downs, "coverage": len(members),
                       "return_method": "equal-weight available constituents"}
            found.append(make_event("MARKET ACTIVITY RADAR", sector, direction, signal_date, stamp,
                                    members=members, source="NSE quote snapshot", details=details))
            found.append(make_event("SECTOR ACTIVITY", sector, direction, signal_date, stamp,
                                    members=members, source="NSE quote snapshot", details=details))

    # Build the same ranked HIGH / WATCH / FLOW alert candidates shown by the dashboard.
    candidates = []
    for symbol, q in quotes.items():
        if not isinstance(q, dict) or q.get("type") != "stock":
            continue
        change = number(q.get("change_pct"))
        if change is None:
            continue
        positive = negative = 0
        for headline in q.get("headlines") or []:
            age = number((headline or {}).get("age_h"))
            score = number((headline or {}).get("score"))
            if age is not None and age <= 24 and score is not None:
                positive += score > 0
                negative += score < 0
        news_total = positive + negative
        news_signal = news_total >= 2 and abs(positive - negative) >= 2
        news_bias = "bull" if positive > negative else "bear" if negative > positive else "mixed"
        aligned = (change > 0 and news_bias == "bull") or (change < 0 and news_bias == "bear")
        if abs(change) >= 2 and news_signal and aligned:
            candidates.append({"kind": "high", "rank": 0, "activity": abs(change),
                               "symbol": symbol, "direction": "BULLISH" if change > 0 else "BEARISH",
                               "price": valid_price(q), "source": q.get("price_source") or "NSE quote",
                               "details": {"change_pct": change, "positive_news": positive, "negative_news": negative}})
        elif abs(change) >= 1.5 or news_signal:
            candidates.append({"kind": "watch", "rank": 1,
                               "activity": max(abs(change), abs(positive - negative)),
                               "symbol": symbol, "direction": "BULLISH" if change > 0 else "BEARISH" if change < 0 else
                                          ("BULLISH" if positive > negative else "BEARISH" if negative > positive else None),
                               "price": valid_price(q), "source": q.get("price_source") or "NSE quote",
                               "details": {"change_pct": change, "positive_news": positive, "negative_news": negative}})
    fpi_history = fpi.get("history") if isinstance(fpi, dict) else []
    if isinstance(fpi_history, list) and len(fpi_history) >= 2:
        latest, previous = fpi_history[0], fpi_history[1]
        old_map = {x.get("name"): number(x.get("net_equity_cr")) for x in previous.get("sectors", []) if isinstance(x, dict)}
        for item in latest.get("sectors", []) if isinstance(latest, dict) else []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            current = number(item.get("net_equity_cr"))
            old = old_map.get(item["name"])
            if current is None or old is None or current == old:
                continue
            sector = item["name"]
            candidates.append({"kind": "flow", "rank": 2, "activity": abs(current-old),
                               "symbol": sector, "direction": "BULLISH" if current-old > 0 else "BEARISH",
                               "members": sectors.get(sector, {}),
                               "source": "NSDL FPI sector flow change",
                               "details": {"net_equity_change_cr": current-old}})

    candidates.sort(key=lambda item: (item["rank"], -item["activity"]))
    selected, counts = [], {"high": 0, "watch": 0, "flow": 0}
    for kind in ("high", "watch", "flow"):
        for item in candidates:
            if item["kind"] == kind and counts[kind] < 3 and len(selected) < 8:
                if item.get("direction"):
                    selected.append(item)
                    counts[kind] += 1
    for item in candidates:
        if len(selected) >= 8:
            break
        if item not in selected and item.get("direction"):
            selected.append(item)
    for item in selected:
        found.append(make_event("LATEST ACTIVITY ALERTS", item["symbol"], item["direction"],
                                signal_date, stamp, price=item.get("price"),
                                members=item.get("members"), source=item.get("source"),
                                details={"kind": item["kind"], **item.get("details", {})}))

    if isinstance(daily, dict) and parse_date(daily.get("as_of")) == signal_date:
        for row in daily.get("rows") or []:
            if not isinstance(row, dict):
                continue
            direction = direction_for_daily(row)
            price = number(row.get("price"))
            if direction and price is not None and price > 0:
                found.append(make_event("DAILY STOCK BUYING ACTIVITY", row.get("symbol"), direction,
                                        signal_date, stamp, price=price,
                                        source="NSE EOD Daily Stock Buying Activity",
                                        details={"signal": row.get("signal"), "as_of": daily.get("as_of")}))

    # Reuse only new extreme events whose event-time price is present in this scan.
    for item in contrarian if isinstance(contrarian, list) else []:
        if not isinstance(item, dict) or parse_date(item.get("date")) != signal_date:
            continue
        event_stamp = parse_stamp(item.get("event_time_utc"))
        if not event_stamp or abs((stamp - event_stamp).total_seconds()) > 30 * 60:
            continue
        symbol = str(item.get("instrument") or "")
        price = valid_price(quotes.get(symbol))
        score = number(item.get("score"))
        if score is not None:
            found.append(make_event("NEXT-SESSION REVERSAL", symbol,
                                    "BULLISH" if score > 0 else "BEARISH",
                                    signal_date, event_stamp, price=price,
                                    source=(quotes.get(symbol) or {}).get("price_source") or "TRINETRA event-time quote",
                                    details={"contrarian_score": score}))
    return [event for event in found if event]

def evaluate_pending(events, data, stamp):
    # Do not treat intraday quotes as closing prices.
    if stamp.hour * 60 + stamp.minute < 15 * 60 + 45:
        return
    quotes = quote_map(data)
    current_date = stamp.date()
    for event in events:
        if event.get("status") != "PENDING":
            continue
        signal_date = parse_date(event.get("signal_date"))
        if not signal_date or current_date <= signal_date:
            continue
        entry = number(event.get("entry_price"))
        if entry is not None and entry > 0:
            quote = quotes.get(event.get("instrument")) or {}
            exit_price = valid_price(quote)
            quote_date = parse_date(quote.get("price_as_of"))
            if exit_price is None or exit_price <= 0 or quote_date != current_date:
                event.update({"status": "UNVERIFIED", "evaluation_date": current_date.isoformat(),
                              "reason": "अगले सत्र की सत्यापित क्लोजिंग कीमत उपलब्ध नहीं"})
                continue
            move = (exit_price / entry - 1) * 100
        else:
            members = event.get("member_prices") or {}
            moves = []
            for symbol, old_price in members.items():
                quote = quotes.get(symbol) or {}
                new_price = valid_price(quote)
                quote_date = parse_date(quote.get("price_as_of")) or parse_date(data.get("updated"))
                old = number(old_price)
                if old and old > 0 and new_price and new_price > 0 and quote_date == current_date:
                    moves.append((new_price / old - 1) * 100)
            required = max(3, math.ceil(len(members) * 0.6))
            if len(moves) < required:
                event.update({"status": "UNVERIFIED", "evaluation_date": current_date.isoformat(),
                              "reason": f"सेक्टर क्लोजिंग कवरेज अपर्याप्त ({len(moves)}/{len(members)})"})
                continue
            move = sum(moves) / len(moves)
            exit_price = None
        signed = move if event.get("direction") == "BULLISH" else -move
        if abs(signed) < 0.05:
            status = "FLAT"
        else:
            status = "CORRECT" if signed > 0 else "INCORRECT"
        event.update({
            "evaluation_date": current_date.isoformat(),
            "exit_price": round(exit_price, 6) if exit_price is not None else None,
            "return_pct": round(move, 4),
            "signed_return_pct": round(signed, 4),
            "status": status,
            "reason": "अगले ट्रेडिंग सेशन की क्लोजिंग से जाँचा गया",
        })


def summarize(events):
    summary = {}
    for department in DEPARTMENTS:
        rows = [e for e in events if e.get("department") == department]
        correct = sum(e.get("status") == "CORRECT" for e in rows)
        incorrect = sum(e.get("status") == "INCORRECT" for e in rows)
        flat = sum(e.get("status") == "FLAT" for e in rows)
        unverified = sum(e.get("status") == "UNVERIFIED" for e in rows)
        pending = sum(e.get("status") == "PENDING" for e in rows)
        returns = [number(e.get("signed_return_pct")) for e in rows
                   if e.get("status") in ("CORRECT", "INCORRECT", "FLAT")]
        returns = [v for v in returns if v is not None]
        gains = [v for v in returns if v > 0]
        losses = [-v for v in returns if v < 0]
        evaluated = correct + incorrect
        summary[department] = {
            "total": len(rows), "correct": correct, "incorrect": incorrect,
            "flat": flat, "unverified": unverified, "pending": pending,
            "accuracy_pct": round(correct / evaluated * 100, 2) if evaluated else None,
            "average_profit_pct": round(sum(gains) / len(gains), 4) if gains else None,
            "average_loss_pct": round(sum(losses) / len(losses), 4) if losses else None,
            "net_return_pct": round(sum(returns), 4) if returns else None,
            "profit_factor": round(sum(gains) / sum(losses), 4) if losses else (None if not gains else "Infinity"),
            "sample_size": len(returns),
        }
    return summary


def main():
    data = read_json(DATA, {})
    master = read_json(MASTER, {})
    daily = read_json(DAILY, {})
    contrarian = read_json(CONTRARIAN, [])
    fpi = read_json(Path("fpi-sector-data.json"), {})
    stamp = parse_stamp(data.get("updated"))
    if not stamp:
        print("SIGNAL_PERFORMANCE_SKIP invalid data.json updated timestamp")
        return
    ledger = load_ledger()
    events = ledger["events"]
    known_ids = {e.get("id") for e in events if isinstance(e, dict)}
    evaluate_pending(events, data, stamp)
    for event in collect_signals(data, master, daily, contrarian, fpi, stamp):
        if event["id"] not in known_ids:
            events.append(event)
            known_ids.add(event["id"])
    ledger["updated_at"] = stamp.isoformat(timespec="seconds")
    ledger["summary"] = summarize(events)
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"events": len(events), "departments": ledger["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
