"""Research-only archive for daily crowd mood and index quote evidence."""
import datetime as dt
import math

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
INDEXES = ("NIFTY", "SENSEX", "BANKNIFTY")


def classify_mood(trends):
    if not isinstance(trends, dict) or trends.get("ok") is not True or trends.get("stale") is True:
        return None, None
    if not str(trends.get("today_basis") or "").startswith("now_1d"):
        return None, None
    try:
        bull, bear, neutral = (float(trends[k]) for k in ("bull_score_pct", "bear_score_pct", "neutral_score_pct"))
    except (KeyError, TypeError, ValueError):
        return None, None
    if not all(math.isfinite(x) and 0 <= x <= 100 for x in (bull, bear, neutral)):
        return None, None
    if abs(bull + bear + neutral - 100) > 2 or bull + bear < 1:
        return None, None
    share = bull / (bull + bear) * 100
    if share >= 70:
        return "EXTREME_BULLISH", round(share, 2)
    if share <= 30:
        return "EXTREME_BEARISH", round(share, 2)
    return "NON_EXTREME", round(share, 2)


def _parse_stamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.astimezone(dt.timezone.utc) if stamp.tzinfo else None
    except ValueError:
        return None


def _quote(item):
    source = str(item.get("price_source") or "")
    try:
        price = float(item.get("price"))
        valid = math.isfinite(price) and price > 0
    except (TypeError, ValueError):
        price, valid = None, False
    stamp = None
    day, clock = item.get("price_as_of"), item.get("price_time")
    if isinstance(day, str) and isinstance(clock, str):
        for df in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                date = dt.datetime.strptime(day[:10], df).date()
                for tf in ("%H:%M:%S", "%H:%M"):
                    try:
                        time = dt.datetime.strptime(clock.strip(), tf).time()
                        stamp = dt.datetime.combine(date, time, tzinfo=IST).astimezone(dt.timezone.utc)
                        break
                    except ValueError:
                        pass
                break
            except ValueError:
                pass
    closing = any(x in source.lower() for x in ("last closing", "previous close", "पिछला बंद", "closing price"))
    quote_date = None
    if isinstance(day, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                quote_date = dt.datetime.strptime(day[:10], fmt).date().isoformat()
                break
            except ValueError:
                pass
    return {"price": price if valid else None, "price_as_of": day, "price_time": clock,
            "quote_market_date": quote_date, "quote_kind": "closing" if closing else "intraday_or_unknown",
            "price_source": source or None, "quote_timestamp_utc": stamp.isoformat() if stamp else None,
            "intraday_eligible": bool(valid and stamp and not closing)}


def update_archive(archive, result, captured_at=None):
    archive = archive if isinstance(archive, dict) else {}
    events = list(archive.get("events") or [])
    snapshots = list(archive.get("price_snapshots") or [])
    captured = _parse_stamp(captured_at or result.get("updated"))
    if captured is None:
        return archive
    market_date = captured.astimezone(IST).date().isoformat()
    trends = result.get("trends") or {}
    mood, share = classify_mood(trends)
    source_time = _parse_stamp(trends.get("source_data_time") or trends.get("as_of"))
    if mood in ("EXTREME_BULLISH", "EXTREME_BEARISH") and source_time:
        key = market_date + "|" + mood
        if not any(x.get("event_key") == key for x in events):
            events.append({"event_key": key, "market_date": market_date,
                "captured_at_utc": captured.isoformat(), "trends_source_timestamp_utc": source_time.isoformat(),
                "basis": trends.get("today_basis"), "bull_pct": trends.get("bull_score_pct"),
                "bear_pct": trends.get("bear_score_pct"), "neutral_pct": trends.get("neutral_score_pct"),
                "directional_bull_share_pct": share, "mood": mood, "index_scope": list(INDEXES),
                "outcomes": {}, "research_only": True})
    # Backfill older daily crowd events, but never use them for intraday denominators.
    legacy_events = (result.get("crowd_stats") or {}).get("events") or []
    for legacy in legacy_events:
        date = legacy.get("date")
        direction = str(legacy.get("direction") or "").lower()
        try:
            pct = float(legacy.get("crowd_pct"))
        except (TypeError, ValueError):
            continue
        if not isinstance(date, str) or direction not in ("bull", "bear") or not math.isfinite(pct):
            continue
        if (direction == "bull" and pct < 70) or (direction == "bear" and pct > 30):
            continue
        legacy_mood = "EXTREME_BULLISH" if direction == "bull" else "EXTREME_BEARISH"
        key = date + "|legacy|" + legacy_mood
        if not any(x.get("event_key") == key or (x.get("market_date") == date and x.get("mood_source") == "fresh_google_trends") for x in events):
            events.append({"event_key": key, "market_date": date,
                "captured_at_utc": captured.isoformat(), "trends_source_timestamp_utc": None,
                "basis": "legacy_daily_crowd_stats", "bull_pct": pct if direction == "bull" else None,
                "bear_pct": pct if direction == "bear" else None, "neutral_pct": None,
                "directional_bull_share_pct": pct, "mood": legacy_mood,
                "mood_source": "legacy_crowd_stats", "time_precision": "daily_only",
                "intraday_event_eligible": False, "index_scope": ["NIFTY"],
                "legacy_outcome_not_imported": True, "outcomes": {}, "research_only": True})
    for name in INDEXES:
        quote = _quote((result.get("instruments") or {}).get(name) or {})
        snapshots.append({"captured_at_utc": captured.isoformat(), "scan_market_date": market_date,
                          "market_date": quote.get("quote_market_date") or market_date,
                          "index": name, **quote})
    cutoff = captured - dt.timedelta(days=400)
    def recent(row):
        stamp = _parse_stamp(row.get("captured_at_utc"))
        return stamp is not None and stamp >= cutoff
    signal_state = (((result.get("signals") or {}).get("state") or {}).get("NIFTY") or {})
    archived_bars = list(archive.get("intraday_30m_bars") or [])
    known_bars = {x.get("end") for x in archived_bars if isinstance(x, dict)}
    for bar in signal_state.get("completed_30m_bars") or []:
        if not isinstance(bar, dict) or not bar.get("end") or bar.get("end") in known_bars:
            continue
        archived_bars.append({"index": "NIFTY", **bar})
        known_bars.add(bar.get("end"))
    archived_bars.sort(key=lambda x: str(x.get("end") or ""))
    archived_bars = archived_bars[-4000:]
    archive.update({"schema_version": 1, "description": "Daily extreme crowd events and scan-time index quote evidence; research only",
        "updated_at": captured.isoformat(), "events": [x for x in events if recent(x)][-400:],
        "price_snapshots": [x for x in snapshots if recent(x)][-14400:],
        "intraday_30m_bars": archived_bars})
    return archive
