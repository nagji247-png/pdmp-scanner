#!/usr/bin/env python3
"""Prospective, close-only performance ledger for TRINETRA signal departments.

Each event is immutable after capture except for its single forward-close evaluation.
No 30-minute or 60-minute evaluation is performed here.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
LEDGER = Path("signal-performance.json")
DEPARTMENTS = {
    "MARKET ACTIVITY RADAR": "radar",
    "LATEST ACTIVITY ALERTS": "alerts",
    "SECTOR ACTIVITY": "sectors",
    "DAILY STOCK BUYING ACTIVITY": "daily_buying",
    "NEXT-SESSION REVERSAL": "reversal",
}


def read_json(path: str, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value
    except (OSError, ValueError, TypeError):
        return default


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def iso_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"):
        try:
            return dt.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(IST).date() if parsed.tzinfo else parsed.date()
    except ValueError:
        return None


def next_session(day, calendar):
    if not isinstance(calendar, dict) or calendar.get("calendar_year") != day.year:
        return None
    holidays = {str(x.get("date")) for x in calendar.get("holidays", []) if isinstance(x, dict)}
    specials = calendar.get("special_sessions") or {}
    candidate = day + dt.timedelta(days=1)
    for _ in range(15):
        key = candidate.isoformat()
        if key in specials or (candidate.weekday() < 5 and key not in holidays):
            return key
        candidate += dt.timedelta(days=1)
    return None


def direction_from_signal(signal):
    value = str(signal or "").upper()
    if value in {"LONG BUILD-UP", "SHORT COVERING", "DISCLOSED BUY DEAL WATCH", "EARLY BUYING WATCH"}:
        return "BULLISH"
    if value in {"SHORT BUILD-UP", "LONG UNWINDING", "SELLING WATCH", "DISCLOSED SELL DEAL WATCH"}:
        return "BEARISH"
    return None


def event_id(department, day, instrument, direction, suffix=""):
    return "|".join((department, str(day), str(instrument), str(direction), str(suffix)))


def add_event(events, seen, department, day, instrument, direction, baseline_price=None,
              source="", reference_prices=None, metadata=None, target_day=None):
    key = event_id(department, day, instrument, direction)
    if key in seen or not direction:
        return
    baseline = number(baseline_price)
    refs = {str(k): number(v) for k, v in (reference_prices or {}).items()}
    refs = {k: v for k, v in refs.items() if v is not None and v > 0}
    if baseline is None and not refs:
        return
    events.append({
        "id": key, "department": department, "signal_date": str(day),
        "target_session": target_day, "instrument": str(instrument),
        "direction": direction, "signal_time": str(source or ""),
        "baseline_price": baseline, "reference_prices": refs,
        "source": str(source or "Verified dashboard snapshot"),
        "metadata": metadata or {}, "status": "pending",
        "result": None, "actual_move_pct": None, "return_pct": None,
    })
    seen.add(key)


def capture_radar_and_sectors(events, seen, data, master, calendar):
    quotes = (data.get("market_activity_quotes") or {}).get("instruments") or {}
    if not isinstance(quotes, dict) or not quotes:
        return
    updated = str(data.get("updated") or "")
    stamp = updated
    quote_dates = [iso_date(q.get("price_as_of")) for q in quotes.values() if isinstance(q, dict)]
    quote_dates = [d for d in quote_dates if d]
    if not quote_dates:
        return
    day = max(quote_dates)
    day_text = day.isoformat()
    # Do not create a signal from a mixed-date or stale market snapshot.
    if sum(1 for d in quote_dates if d == day) < 1:
        return
    stocks = (master.get("stocks") or {}) if isinstance(master, dict) else {}
    sector_members = {}
    valid_prices = {}
    all_symbols = set(stocks) | set(quotes)
    for symbol in all_symbols:
        info = stocks.get(symbol) or {}
        q = quotes.get(symbol) or (data.get("instruments") or {}).get(symbol) or {}
        price = number(q.get("price"))
        change = number(q.get("change_pct"))
        qday = iso_date(q.get("price_as_of"))
        if price is None or price <= 0 or change is None or qday != day:
            continue
        valid_prices[symbol] = price
        sector = str((info or {}).get("sector") or "सेक्टर मैपिंग उपलब्ध नहीं")
        sector_members.setdefault(sector, []).append((symbol, price, change))
    bull_sectors, bear_sectors = 0, 0
    for sector, members in sector_members.items():
        up = sum(1 for _, _, ch in members if ch > 0)
        down = sum(1 for _, _, ch in members if ch < 0)
        if up == down:
            continue
        direction = "BULLISH" if up > down else "BEARISH"
        bull_sectors += direction == "BULLISH"
        bear_sectors += direction == "BEARISH"
        refs = {sym: price for sym, price, _ in members}
        add_event(events, seen, "SECTOR ACTIVITY", day_text, sector, direction,
                  source=stamp, reference_prices=refs,
                  metadata={"covered": len(members), "advances": up, "declines": down},
                  target_day=next_session(day, calendar))
    if bull_sectors != bear_sectors:
        direction = "BULLISH" if bull_sectors > bear_sectors else "BEARISH"
        add_event(events, seen, "MARKET ACTIVITY RADAR", day_text, "MARKET-WIDE", direction,
                  source=stamp, reference_prices=valid_prices,
                  metadata={"bullish_sectors": bull_sectors, "bearish_sectors": bear_sectors,
                            "covered_stocks": len(valid_prices)},
                  target_day=next_session(day, calendar))


def capture_alerts(events, seen, data, master, calendar):
    quotes = (data.get("market_activity_quotes") or {}).get("instruments") or {}
    stocks = (master.get("stocks") or {}) if isinstance(master, dict) else {}
    for symbol, q in quotes.items():
        if not isinstance(q, dict):
            continue
        day = iso_date(q.get("price_as_of"))
        change = number(q.get("change_pct"))
        price = number(q.get("price"))
        if not day or change is None or price is None or price <= 0:
            continue
        pos, neg = number(q.get("pos_n")) or 0, number(q.get("neg_n")) or 0
        news_signal = pos + neg >= 2 and abs(pos - neg) >= 2
        news_direction = "BULLISH" if pos > neg else "BEARISH" if neg > pos else None
        price_direction = "BULLISH" if change > 0 else "BEARISH" if change < 0 else None
        high = abs(change) >= 2 and news_signal and news_direction == price_direction
        watch = abs(change) >= 1.5 or news_signal
        if not (high or watch) or not price_direction:
            continue
        sector = str((stocks.get(symbol) or {}).get("sector") or "सेक्टर उपलब्ध नहीं")
        add_event(events, seen, "LATEST ACTIVITY ALERTS", day.isoformat(), symbol,
                  price_direction, baseline_price=price, source=data.get("updated"),
                  metadata={"alert": "HIGH" if high else "WATCH", "sector": sector,
                            "change_pct_at_signal": change},
                  target_day=next_session(day, calendar))


def capture_daily_buying(events, seen, report, calendar):
    if not isinstance(report, dict):
        return
    day = iso_date(report.get("as_of"))
    if not day:
        return
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        direction = direction_from_signal(row.get("signal"))
        price = number(row.get("price"))
        symbol = str(row.get("symbol") or "").upper()
        if not symbol or not direction or price is None or price <= 0:
            continue
        add_event(events, seen, "DAILY STOCK BUYING ACTIVITY", day.isoformat(), symbol,
                  direction, baseline_price=price, source=report.get("generated_at") or report.get("as_of"),
                  metadata={"signal": row.get("signal"), "strength": row.get("strength"),
                            "category": row.get("category")},
                  target_day=next_session(day, calendar))


def capture_reversals(events, seen, contrarian, calendar):
    if not isinstance(contrarian, list):
        return
    for row in contrarian:
        if not isinstance(row, dict):
            continue
        day = iso_date(row.get("date"))
        score = number(row.get("score"))
        baseline = number(row.get("baseline_price"))
        if not day or score is None or abs(score) < 6 or baseline is None or baseline <= 0:
            continue
        # Contrarian prediction is opposite to the extreme crowd/news score.
        direction = "BEARISH" if score > 0 else "BULLISH"
        key = event_id("NEXT-SESSION REVERSAL", day.isoformat(), row.get("instrument"), direction)
        if key in seen:
            continue
        event = {
            "id": key, "department": "NEXT-SESSION REVERSAL",
            "signal_date": day.isoformat(), "target_session": next_session(day, calendar),
            "instrument": str(row.get("instrument") or ""), "direction": direction,
            "signal_time": row.get("event_time_utc") or row.get("baseline_time") or "",
            "baseline_price": baseline, "reference_prices": {},
            "source": row.get("baseline_source") or "TRINETRA contrarian event baseline",
            "metadata": {"crowd_score": score, "contrarian_key": row.get("key")},
            "status": "pending", "result": None, "actual_move_pct": None, "return_pct": None,
        }
        # Existing official next-session close evaluation is reusable; ignore all 30m/60m fields.
        move = number(row.get("next_change"))
        if move is not None and row.get("outcome") in ("continued", "reversed", "neutral"):
            expected = 1 if direction == "BULLISH" else -1
            pnl = expected * move
            event["actual_move_pct"] = move
            event["return_pct"] = pnl
            event["status"] = "evaluated"
            event["result"] = "FLAT" if abs(move) < 0.01 else "CORRECT" if pnl > 0 else "INCORRECT"
            event["evaluated_session"] = row.get("next_session_date") or None
            event["evaluation_source"] = "Existing contrarian next-session close result"
        events.append(event)
        seen.add(key)


def close_confirmed(data, day):
    updated = data.get("updated")
    try:
        stamp = dt.datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        stamp = stamp.astimezone(IST) if stamp.tzinfo else stamp.replace(tzinfo=IST)
    except ValueError:
        return False
    quotes = (data.get("market_activity_quotes") or {}).get("instruments") or {}
    dates = [iso_date(q.get("price_as_of")) for q in quotes.values() if isinstance(q, dict)]
    return stamp.date() == day and stamp.time() >= dt.time(15, 30) and any(x == day for x in dates)


def evaluate_pending(events, data, calendar):
    quotes = (data.get("market_activity_quotes") or {}).get("instruments") or {}
    if not isinstance(quotes, dict) or not quotes:
        return
    dates = [iso_date(q.get("price_as_of")) for q in quotes.values() if isinstance(q, dict)]
    dates = [x for x in dates if x]
    if not dates:
        return
    day = max(dates)
    if not close_confirmed(data, day):
        return
    day_text = day.isoformat()
    stocks = (data.get("instruments") or {})
    for event in events:
        if event.get("status") != "pending" or event.get("target_session") != day_text:
            continue
        refs = event.get("reference_prices") or {}
        moves = []
        if refs:
            for symbol, base in refs.items():
                q = quotes.get(symbol) or stocks.get(symbol) or {}
                price = number(q.get("price"))
                base = number(base)
                if price is not None and base and base > 0 and price > 0:
                    moves.append((price / base - 1) * 100)
        else:
            symbol = event.get("instrument")
            q = quotes.get(symbol) or stocks.get(symbol) or {}
            price, base = number(q.get("price")), number(event.get("baseline_price"))
            if price is not None and base and base > 0 and price > 0:
                moves.append((price / base - 1) * 100)
        if not moves:
            if event.get("target_session") and event.get("target_session") < day_text:
                event.update({"status": "unverified", "result": "UNVERIFIED",
                              "reason": "अगले ट्रेडिंग सेशन की प्रमाणित क्लोजिंग उपलब्ध नहीं मिली"})
            continue
        actual = sum(moves) / len(moves)
        expected_sign = 1 if event.get("direction") == "BULLISH" else -1
        pnl = expected_sign * actual
        event.update({
            "status": "evaluated",
            "result": "FLAT" if abs(actual) < 0.01 else "CORRECT" if pnl > 0 else "INCORRECT",
            "actual_move_pct": round(actual, 4),
            "return_pct": round(pnl, 4),
            "evaluated_session": day_text,
            "evaluation_source": "Verified next-session NSE market close snapshot",
            "matched_constituents": len(moves),
        })


def build_summary(events):
    summary = {}
    for department in DEPARTMENTS:
        rows = [e for e in events if e.get("department") == department]
        done = [e for e in rows if e.get("status") == "evaluated" and e.get("result") in ("CORRECT", "INCORRECT", "FLAT")]
        correct = sum(e["result"] == "CORRECT" for e in done)
        incorrect = sum(e["result"] == "INCORRECT" for e in done)
        flat = sum(e["result"] == "FLAT" for e in done)
        unverified = sum(e.get("status") == "unverified" for e in rows)
        returns = [number(e.get("return_pct")) for e in done]
        returns = [x for x in returns if x is not None]
        gains = sum(x for x in returns if x > 0)
        losses = -sum(x for x in returns if x < 0)
        summary[department] = {
            "total": len(rows), "evaluated": len(done), "pending": sum(e.get("status") == "pending" for e in rows),
            "correct": correct, "incorrect": incorrect, "flat": flat, "unverified": unverified,
            "accuracy_pct": round(correct / (correct + incorrect) * 100, 2) if correct + incorrect else None,
            "average_profit_pct": round(sum(x for x in returns if x > 0) / sum(x > 0 for x in returns), 4) if any(x > 0 for x in returns) else None,
            "average_loss_pct": round(sum(x for x in returns if x < 0) / sum(x < 0 for x in returns), 4) if any(x < 0 for x in returns) else None,
            "net_return_pct": round(sum(returns), 4) if returns else None,
            "profit_factor": round(gains / losses, 3) if losses > 0 else ("∞" if gains > 0 else None),
            "sample_size": len(done),
        }
    return summary


def update_tracker(data_path="data.json", master_path="nse-fo-stock-sector-master.json",
                   daily_path="daily_stock_buying_activity.json", contrarian_path="contrarian.json",
                   calendar_path="exchange_calendar.json", ledger_path=LEDGER):
    data = read_json(data_path, {})
    master = read_json(master_path, {})
    report = read_json(daily_path, {})
    contrarian = read_json(contrarian_path, [])
    calendar = read_json(calendar_path, {})
    ledger = read_json(ledger_path, {"schema_version": 1, "events": []})
    events = ledger.get("events") if isinstance(ledger, dict) else []
    if not isinstance(events, list):
        events = []
    seen = {e.get("id") for e in events if isinstance(e, dict)}
    evaluate_pending(events, data, calendar)
    capture_radar_and_sectors(events, seen, data, master, calendar)
    capture_alerts(events, seen, data, master, calendar)
    capture_daily_buying(events, seen, report, calendar)
    capture_reversals(events, seen, contrarian, calendar)
    ledger = {
        "schema_version": 1,
        "updated": data.get("updated"),
        "evaluation_rule": "Next trading session close only; no 30m/60m evaluation",
        "events": events,
        "summary": build_summary(events),
    }
    Path(ledger_path).write_text(json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"events": len(events), "departments": len(ledger["summary"]),
                      "evaluated": sum(x["evaluated"] for x in ledger["summary"].values())}, ensure_ascii=False))
    return ledger


if __name__ == "__main__":
    update_tracker()
