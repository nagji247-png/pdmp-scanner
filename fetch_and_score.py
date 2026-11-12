import json, csv, os, re, time, math, datetime as dt, html
from html.parser import HTMLParser
from urllib.parse import quote_plus
from component_scoring import (
    DEFAULT_COMPONENT_WEIGHTS, build_component, combine_components,
    search_component_from_snapshot, client_oi_context, is_fresh_timestamp,
    parse_utc_timestamp,
    compare_mcx_bhavcopy_contract_oi, compare_nse_udiff_index_futures_oi,
)
from provisional_component_scoring import (
    PROVISIONAL_WEIGHTS, index_oi_balance_component,
    client_marketwide_components, source_date_is_fresh,
)
from validate_market_signal_history import market_snapshot_completeness
from crowd_mood_intraday import update_archive as update_crowd_mood_archive
import feedparser, yfinance as yf
import requests
from curl_cffi import requests as curl_requests

# ---- इंडेक्स और कमोडिटी ----
# (yfinance सिंबल, न्यूज़ खोज शब्द)
INDEXES = {
    "NIFTY": ("^NSEI", '"Nifty 50" OR Nifty index OR Nifty 50 stocks India'),
    "SENSEX": ("^BSESN", '"BSE Sensex" OR Sensex index India'),
    "BANKNIFTY": ("^NSEBANK", '"Bank Nifty" OR Nifty Bank index OR banking index India'),
    "USDINR": ("INR=X", "USD INR exchange rate India"),
    "GOLD": ("GC=F", "gold price"),
    "SILVER": ("SI=F", "silver price"),
    "CRUDEOIL": ("BZ=F", "MCX crude oil futures India"),
    "BITCOIN": ("BTC-USD", "bitcoin price"),
    "NASDAQ": ("^IXIC", "Nasdaq stock market"),
    "DJI": ("^DJI", "Dow Jones stock market"),
}

# ---- स्टॉक वॉचलिस्ट ----
# अपने स्टॉक यहाँ जोड़ें या हटाएँ। NSE स्टॉक के लिए सिंबल के आगे ".NS" लगता है।
STOCKS = {
    "RELIANCE": ("RELIANCE.NS", "Reliance Industries share"),
    "HDFCBANK": ("HDFCBANK.NS", "HDFC Bank share"),
    "TATAMOTORS": ("TMPV.NS", "Tata Motors Passenger Vehicles share"),
    "HINDALCO": ("HINDALCO.NS", "Hindalco share"),
    "ADANIPORTS": ("ADANIPORTS.NS", "Adani Ports share"),
    "COALINDIA": ("COALINDIA.NS", "Coal India share"),
    "EICHERMOT": ("EICHERMOT.NS", "Eicher Motors share"),
    "APOLLOHOSP": ("APOLLOHOSP.NS", "Apollo Hospitals share"),
    "SBIN": ("SBIN.NS", "SBI share"),
}

# वॉचलिस्ट से हटाए गए शेयरों के पुराने Contrarian रिकॉर्ड पूरे करने हेतु
# इन्हें Dashboard के सक्रिय स्टॉक कार्ड में नहीं जोड़ा जाता।
ARCHIVE_PENDING_SYMBOLS = {
    "RAYMOND": "RAYMOND.NS",
    "GESHIP": "GESHIP.NS",
    "ITC": "ITC.NS",
    "MOTILALOFS": "MOTILALOFS.NS",
}

# Google Trends में स्टॉक का नाम पहचानने के लिए वैकल्पिक नाम।
# नया स्टॉक जोड़ें तो यहाँ भी एक लाइन जोड़ें।
STOCK_ALIASES = {
    "RELIANCE": ["reliance"],
    "HDFCBANK": ["hdfc bank", "hdfcbank", "hdfc"],
    "TATAMOTORS": ["tata motors", "tatamotors"],
    "HINDALCO": ["hindalco"],
    "ADANIPORTS": ["adani ports", "adaniports"],
    "COALINDIA": ["coal india", "coalindia"],
    "EICHERMOT": ["eicher", "eichermot"],
    "APOLLOHOSP": ["apollo hospital", "apollohosp", "apollo"],
    "SBIN": ["sbi", "sbin", "state bank"],
}

# शब्द-सूची: वज़न 1 या 2। मिलान शब्द की शुरुआत से होता है।
# "again" में "gain" नहीं गिना जाता, क्योंकि वह शब्द के बीच में है।
POS = {"rally": 2, "rallies": 2, "surge": 2, "record high": 2, "bullish": 2, "gain": 1,
       "jump": 1, "rise": 1, "rose": 1, "climb": 1, "rebound": 1, "higher": 1, "profit": 1,
       "beat": 1, "upgrade": 2, "buy": 1}
NEG = {"crash": 2, "slump": 2, "bearish": 2, "plunge": 2, "tumble": 2, "fall": 1, "fell": 1,
       "slid": 1, "slip": 1, "dip": 1, "drag": 1, "loss": 1, "drop": 1, "decline": 1,
       "weigh": 1, "lower": 1, "sell-off": 2, "selloff": 2, "downgrade": 2, "miss": 1}

# Google Trends: डर-संबंधी खोजें (फ़ियर मेट्रिक के लिए, एक ही अनुरोध)
FEAR_TERMS = ["nifty crash", "stock market crash", "sensex fall"]

# भीड़ के मूड के लिए शब्द: आम लोग जैसे बोलते हैं, English और हिन्दी दोनों।
# Google Trends हर अनुरोध में अधिकतम 5 शब्द लेता है, इसलिए शब्द 4-4 के समूहों में जाते हैं,
# और हर समूह के साथ ANCHOR शब्द जोड़ा जाता है, ताकि अलग अनुरोधों के नंबर तुलनीय बनें।
ANCHOR = "nifty"
# Nifty/Sensex से जुड़े खोज-वाक्यांश। Google Trends सापेक्ष रुचि देता है, वास्तविक search count नहीं।
# तेजी और गिरावट में समान 16-16 शब्द: 8 English + 8 हिंदी।
# 4 शब्द + nifty anchor प्रति अनुरोध; अतिरिक्त शब्दों से कुल 4 अतिरिक्त Trends requests होंगे।
BULL_TERMS = [
    "market rally", "market recovery", "nifty breakout", "stock market gains",
    "बाजार में तेजी", "शेयर बाजार में तेजी", "निफ्टी में तेजी", "बाजार में चढ़ाव",
    "nifty rally", "sensex rally", "bank nifty breakout", "stocks to buy",
    "सेंसेक्स में तेजी", "बैंक निफ्टी में तेजी", "निफ्टी ऊपर जाएगा", "शेयर खरीदने चाहिए",
]
BEAR_TERMS = [
    "market fall", "market crash", "market correction", "market sell-off",
    "बाजार में गिरावट", "शेयर बाजार में गिरावट", "निफ्टी में गिरावट", "बाजार में बिकवाली",
    "nifty correction", "sensex correction", "nifty sell on rise", "sensex crash",
    "निफ्टी में करेक्शन", "सेंसेक्स में करेक्शन", "तेजी पर बिकवाली", "सेंसेक्स में भारी गिरावट",
]
NEUTRAL_TERMS = [
    "nifty sideways", "sensex sideways", "market flat", "nifty rangebound",
    "sensex stable", "market consolidation", "बाजार स्थिर", "निफ्टी सपाट",
]
TERM_CHUNK = 4

# भीड़ का मूड तभी दिखेगा जब दोनों तरफ़ के शब्दों में कम से कम इतनी खोज हो।
# यह मान "निफ़्टी" की खोज के प्रतिशत में है। शुरुआती मान है, डैशबोर्ड पर असली अनुपात दिखता है ताकि बदला जा सके।
MIN_SIDE_PCT = 0.01
TRENDS_RETRIES = 1  # तय समय पर केवल एक प्रयास; 429 पर उसी स्लॉट में दोबारा अनुरोध नहीं
TRENDS_MAX_AGE_MINUTES = 180  # 3 घंटे से पुरानी Google Trends reading stale मानी जाएगी; पुराना डेटा reuse नहीं होगा

# बाज़ार पर असर वाली ट्रेंडिंग खबरें: हर विषय की एक खोज
MARKET_NEWS_TOPICS = [
    ("भारतीय बाज़ार", "India stock market Nifty Sensex today"),
    ("कच्चा तेल", "crude oil prices today"),
    ("अमेरिकी Fed और ब्याज दर", "Federal Reserve interest rate decision"),
    ("RBI नीति", "RBI monetary policy India rates"),
    ("व्यापार और टैरिफ", "global trade tariffs stock markets"),
    ("सोना, डॉलर और रुपया", "gold price dollar rupee today"),
]
# खबर को बाज़ार से जुड़ा मानने के शब्द (पूरे शब्द या वाक्यांश के रूप में मिलने चाहिए)
MARKET_IMPACT_WORDS = [
    "market", "markets", "stock", "stocks", "shares", "sensex", "nifty", "crude", "oil",
    "interest rate", "interest rates", "rate cut", "rate hike", "repo rate", "fed", "rbi",
    "inflation", "tariff", "tariffs", "war", "gdp", "bond", "bonds", "dollar", "rupee",
    "earnings", "budget", "gold", "bitcoin", "recession", "sanctions", "opec", "fii", "fpi",
    "yield", "yields",
]

# भीड़ की सोच: इस सीमा से ऊपर/नीचे का मतलब "सोच एकतरफ़ा" है
CROWD_EXTREME = 70
CROWD_LOW = 30
# Nifty के वॉच-स्तर (आप यहाँ अपने लेवल जोड़ सकते हैं)
NIFTY_WATCH_LEVELS = [21000, 22000, 23000]

# ⚡ संकेत: स्कोर और कीमत की दिशा अलग हो, इन सीमाओं के साथ
DIV_SCORE_MIN = 1.0
DIV_CHANGE_MIN = 0.2

# ---- संकेत-बदलाव लॉग ----
# भारतीय बाज़ार पर ज़ोर: इन इंस्ट्रूमेंट के संकेत में बदलाव दर्ज होता है।
# इंडेक्स (NIFTY, BANKNIFTY) का वॉल्यूम और VWAP yfinance पर नहीं मिलते, इसलिए वहाँ खाली रहेंगे।
# स्टॉक (RELIANCE, HDFCBANK) पर वॉल्यूम और VWAP मिलते हैं।
SIGNAL_WATCH = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "RELIANCE": "RELIANCE.NS",
    "HDFCBANK": "HDFCBANK.NS",
}
SIG_SCORE_BAND = 1.0      # स्कोर इतने से ज़्यादा बदले, तो भावना बदली मानी जाए
SIG_PRICE_BAND = 0.2      # कीमत इतने % से ज़्यादा हो, तो उसकी दिशा मानी जाए
SIG_MOVE_BAND = 0.1       # बाद की चाल इतने % से कम हो तो "लगभग स्थिर"
SIG_VOL_HIGH = 2.0        # औसत से दोगुना वॉल्यूम "ऊँचा" माना जाए
SIG_LOG_KEEP = 200

CONTRARIAN_LIMIT = 6.0
# बाज़ार बंद/छुट्टी होने पर नए इवेंट नहीं बनते (main में सेट होता है)
SKIP_EVENTS = False
# Exchange calendar is maintained separately from scanner logic and contains
# official NSE equity holidays plus notified special sessions (all times IST).
EXCHANGE_CALENDAR_FILE = "exchange_calendar.json"
DATA_FILE = "data.json"
EVENTS_FILE = "contrarian.json"
CROWD_FILE = "crowd_events.json"
DIV_FILE = "divergence_events.json"
SIG_STATE_FILE = "signal_state.json"
SIG_LOG_FILE = "signal_log.json"
HISTORY_FILE = "history.csv"
MARKET_SIGNAL_HISTORY_FILE = "market_signal_history.json"


def clean(obj):
    """NaN या infinity को 0 से बदलता है, ताकि JSON फ़ाइल सही बने।"""
    if isinstance(obj, float):
        return 0.0 if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def _word_hits(text, words):
    """शब्दों की गिनती। हर शब्द सिर्फ़ शब्द की शुरुआत से मिलता है।"""
    hits = 0
    for k, v in words.items():
        if re.search(r"(?<![a-z])" + re.escape(k), text):
            hits += v
    return hits


NEG_WORD_RE = r"(?:\bnot|\bno|\bnever|\bfails?\s+to|\bunlikely\s+to)\s+(?:\w+\s+)?$"
SOURCE_WEIGHTS = {
    "reuters": 1.5, "bloomberg": 1.5, "economic times": 1.4, "moneycontrol": 1.3,
    "livemint": 1.3, "business standard": 1.3, "ndtv profit": 1.3, "cnbc tv18": 1.3,
    "the hindu": 1.2, "business today": 1.2, "the times of india": 1.2, "hindustan times": 1.2,
    "ad-hoc-news": 0.6, "univest": 0.6, "marketsmojo": 0.6, "scanx": 0.6,
    "goodreturns": 0.7, "simply wall street": 0.7, "tradingview": 0.8,
}


def source_weight(src):
    s = (src or "").lower()
    for k, v in SOURCE_WEIGHTS.items():
        if k in s:
            return v
    return 1.0


def recency_weight(age_h):
    if age_h is None:
        return 0.5
    if age_h <= 12:
        return 1.0
    if age_h <= 48:
        return 0.6
    return 0.3


def headline_score(text):
    """खबर का स्कोर। 'not/no/fails to' के बाद का शब्द उल्टा गिना जाता है।
    'again' में 'gain' नहीं गिना जाता; शब्द की शुरुआत से मिलान होता है।"""
    t = text.lower()
    total = 0
    for words, sign in ((POS, 1), (NEG, -1)):
        for k, v in words.items():
            for m in re.finditer(r"(?<![a-z])" + re.escape(k), t):
                negated = re.search(NEG_WORD_RE, t[:m.start()])
                total += -sign * v if negated else sign * v
    return total


def _title_tokens(t):
    return set(re.findall(r"[a-z]{3,}", t.lower()))


def dedupe_heads(heads):
    """एक ही खबर कई वेबसाइट पर आती है। मिलते-जुलते शीर्षक (60%+ शब्द समान) एक बार गिने जाते हैं।"""
    kept = []
    for h in heads:
        tk = _title_tokens(h["title"])
        if not tk:
            continue
        dup = False
        for kt, _ in kept:
            if len(tk & kt) / max(1, len(tk | kt)) >= 0.6:
                dup = True
                break
        if not dup:
            kept.append((tk, h))
    return [h for _, h in kept]


def weighted_score(heads):
    """हर खबर का वज़न = स्रोत-वज़न × ताज़गी-वज़न। पूरे इंस्ट्रूमेंट का स्कोर औसत × 5।"""
    num = 0.0
    den = 0.0
    for h in heads:
        w = source_weight(h.get("source")) * recency_weight(h.get("age_h"))
        num += h["score"] * w
        den += w
    return round(num / den * 5, 1) if den > 0 else 0.0

def shadow_weighted_news_score(heads):
    """Shadow component: retain the weighted mean of headline sentiment points.

    Do not multiply the mean by five: that arbitrary amplifier saturates
    modest positive headlines at +10 and is not part of the production score.
    """
    num = 0.0
    den = 0.0
    for h in heads:
        w = source_weight(h.get("source")) * recency_weight(h.get("age_h"))
        num += h["score"] * w
        den += w
    return round(num / den, 2) if den > 0 else 0.0

def _timestamped_news_age_hours(headline, now_utc):
    """Derive news age from publisher timestamp; never trust cached age_h alone."""
    if not isinstance(headline, dict):
        return None
    published = parse_utc_timestamp(headline.get("published_at"))
    if published is None:
        return None
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    age_h = (now.astimezone(dt.timezone.utc) - published).total_seconds() / 3600.0
    if age_h < -5.0 / 60.0 or age_h > 24.0:
        return None
    return max(0.0, age_h)


def experimental_news_scores(
    instruments, index_names=("NIFTY", "SENSEX", "BANKNIFTY"), now_utc=None
):
    """Shadow-only score: publisher-timestamped <=24h headlines; cross-index duplicates excluded."""
    eligible = {}
    old_or_unknown = {}
    for name in index_names:
        item = instruments.get(name) or {}
        eligible[name] = []
        old_or_unknown[name] = 0
        for h in item.get("headlines") or []:
            age = _timestamped_news_age_hours(h, now_utc)
            if age is None:
                old_or_unknown[name] += 1
                continue
            copied = dict(h)
            copied["age_h"] = age
            eligible[name].append(copied)

    # Exclude a story shared by different index searches from BOTH candidate scores.
    shared = {name: set() for name in index_names}
    for i, left in enumerate(index_names):
        for right in index_names[i + 1:]:
            for li, lh in enumerate(eligible[left]):
                lt = _title_tokens(lh.get("title", ""))
                if not lt:
                    continue
                for ri, rh in enumerate(eligible[right]):
                    rt = _title_tokens(rh.get("title", ""))
                    if not rt:
                        continue
                    similarity = len(lt & rt) / max(1, len(lt | rt))
                    if similarity >= 0.6:
                        shared[left].add(li)
                        shared[right].add(ri)

    output = {}
    for name in index_names:
        kept = [h for i, h in enumerate(eligible[name]) if i not in shared[name]]
        output[name] = {
            "news_score": max(-10.0, min(10.0, shadow_weighted_news_score(kept))),
            "headline_count": len(kept),
            "excluded_old_or_unknown": old_or_unknown[name],
            "excluded_cross_index_duplicates": len(shared[name]),
            "eligible_published_at": sorted(
                str(h.get("published_at")).strip()
                for h in kept if h.get("published_at")
            ),
            "eligible_publishers": sorted({
                str(h.get("source")).strip() for h in kept if h.get("source")
            }),
            "eligible_ages_h": [
                _timestamped_news_age_hours(h, now_utc) for h in kept
            ],
        }
    return output


def should_refresh_asset_search(trends_scan, event_name):
    """Allow bounded asset Search refresh on manual scans and explicit validation pushes."""
    return bool(trends_scan and str(event_name or "").lower() in {"workflow_dispatch", "push"})


def attach_asset_search_snapshots(instruments, previous_instruments, now_utc, fresh_results=None):
    """Attach each asset's own one-day Trends snapshot without extra polling.

    fresh_results is supplied only by a successful scheduled Trends slot (or
    the explicitly isolated shadow workflow). Ordinary 30-minute scans only
    reuse a still-fresh saved snapshot and never call Google Trends here.
    """
    search_assets = {
        "NIFTY": "index_search_shadow",
        "SENSEX": "index_search_shadow",
        "BANKNIFTY": "index_search_shadow",
        "GOLD": "asset_search_shadow",
        "SILVER": "asset_search_shadow",
        "CRUDEOIL": "asset_search_shadow",
    }
    previous_instruments = previous_instruments or {}
    for asset, field in search_assets.items():
        item = (instruments or {}).get(asset)
        if not isinstance(item, dict):
            continue
        old = (previous_instruments.get(asset) or {}).get(field)
        if fresh_results is not None:
            # Partial refreshes must not overwrite unrequested asset snapshots.
            if asset not in fresh_results:
                old_snapshot = (previous_instruments.get(asset) or {}).get(field)
                if isinstance(old_snapshot, dict):
                    item[field] = dict(old_snapshot)
                continue
            fresh = fresh_results.get(asset)
            # A failed/under-covered refresh must not erase a still-fresh
            # verified snapshot. Keep its original observation timestamp and
            # expose the failed refresh separately; never extend its lifetime.
            if not (isinstance(fresh, dict) and fresh.get("valid")):
                stamp = (
                    old.get("source_data_time") or old.get("as_of")
                    or (old.get("retrieved_at") if old.get("timestamp_basis") == "retrieval_time" else None)
                ) if isinstance(old, dict) else None
                if isinstance(old, dict) and old.get("valid") and is_fresh_timestamp(
                    stamp, now_utc, max_age_minutes=TRENDS_MAX_AGE_MINUTES
                ):
                    cached = dict(old)
                    cached["cached"] = True
                    cached["refresh_attempted_at"] = now_utc.isoformat()
                    cached["refresh_error"] = (
                        fresh.get("reason") if isinstance(fresh, dict)
                        else "इस निर्धारित Trends स्लॉट में asset-specific reading नहीं मिली"
                    )
                    item[field] = cached
                    continue
            item[field] = fresh or {
                "valid": False,
                "seed": {
                    "NIFTY": "nifty",
                    "SENSEX": "sensex",
                    "BANKNIFTY": "bank nifty",
                    "GOLD": "gold price",
                    "SILVER": "silver price",
                    "CRUDEOIL": "crude oil",
                }[asset],
                "timeframe": "now 1-d",
                "reason": "इस निर्धारित Trends स्लॉट में asset-specific reading नहीं मिली",
                "production_score_used": False,
            }
            continue

        if isinstance(old, dict) and old.get("valid"):
            stamp = old.get("source_data_time") or old.get("as_of")
            if old.get("timestamp_basis") == "retrieval_time":
                stamp = old.get("retrieved_at")
            if is_fresh_timestamp(stamp, now_utc, max_age_minutes=TRENDS_MAX_AGE_MINUTES):
                cached = dict(old)
                cached["cached"] = True
                item[field] = cached
            else:
                item[field] = {
                    "valid": False,
                    "seed": old.get("seed"),
                    "timeframe": "now 1-d",
                    "reason": "पिछली asset-specific one-day Search reading stale है",
                    "production_score_used": False,
                }
        elif isinstance(old, dict):
            item[field] = old
        else:
            item[field] = {
                "valid": False,
                "seed": {
                    "NIFTY": "nifty",
                    "SENSEX": "sensex",
                    "BANKNIFTY": "bank nifty",
                    "GOLD": "gold price",
                    "SILVER": "silver price",
                    "CRUDEOIL": "crude oil",
                }[asset],
                "timeframe": "now 1-d",
                "reason": "अभी तक कोई asset-specific Trends reading सेव नहीं है",
                "production_score_used": False,
            }


def load_latest_stock_basket_diagnostics(scan_date, archive=None):
    """Load the latest complete dated cash-basket breadth per index for display only.

    This diagnostic is deliberately separate from the weighted component map used
    by combine_components(), so it can never enter the shadow or published Final.
    """
    if archive is None:
        try:
            with open("index_cash_basket_diagnostics.json", "r", encoding="utf-8") as handle:
                archive = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}
    records = archive.get("records", []) if isinstance(archive, dict) else []
    output = {}
    for record in sorted(
        (row for row in records if isinstance(row, dict)
         and isinstance(row.get("date"), str) and row.get("date") <= str(scan_date)),
        key=lambda row: row["date"], reverse=True,
    ):
        indices = record.get("indices") if isinstance(record.get("indices"), dict) else {}
        for index_name in ("NIFTY", "SENSEX", "BANKNIFTY"):
            if index_name in output:
                continue
            metric = indices.get(index_name)
            if not isinstance(metric, dict):
                continue
            try:
                score = float(metric.get("score"))
                expected = int(metric.get("expected"))
                matched = int(metric.get("matched"))
                coverage = float(metric.get("coverage_pct"))
            except (TypeError, ValueError, OverflowError):
                continue
            if (
                metric.get("status") != "complete_diagnostic"
                or metric.get("research_only") is not True
                or metric.get("score_eligible") is not False
                or expected <= 0 or matched != expected or coverage != 100.0
                or not math.isfinite(score) or not -10 <= score <= 10
            ):
                continue
            output[index_name] = {
                "score": round(score, 2),
                "source": "Official NSE/BSE CM UDiFF · equal-weight breadth",
                "source_date": record["date"],
                "research_only": True,
                "score_eligible": False,
                "included": False,
                "status": "complete_diagnostic",
                "expected": expected,
                "matched": matched,
                "coverage_pct": coverage,
                "advances": int(metric.get("advances", 0)),
                "declines": int(metric.get("declines", 0)),
                "unchanged": int(metric.get("unchanged", 0)),
                "method": metric.get("method") or "10 × (advances − declines) / official constituent count",
            }
            detail_rows = metric.get("constituents")
            if isinstance(detail_rows, list) and len(detail_rows) == expected:
                valid_details = True
                seen_ids = set()
                for detail in detail_rows:
                    if not isinstance(detail, dict):
                        valid_details = False
                        break
                    identity = str(detail.get("symbol") or detail.get("instrument_id") or "").strip().upper()
                    isin = str(detail.get("isin") or "").strip().upper()
                    try:
                        close = float(detail.get("close"))
                        previous_close = float(detail.get("previous_close"))
                        change_pct = float(detail.get("change_pct"))
                    except (TypeError, ValueError, OverflowError):
                        valid_details = False
                        break
                    if (
                        not identity or not isin or identity in seen_ids
                        or not math.isfinite(close) or close <= 0
                        or not math.isfinite(previous_close) or previous_close <= 0
                        or not math.isfinite(change_pct)
                    ):
                        valid_details = False
                        break
                    seen_ids.add(identity)
                if valid_details:
                    detail_up = sum(float(item["change_pct"]) > 0 for item in detail_rows)
                    detail_down = sum(float(item["change_pct"]) < 0 for item in detail_rows)
                    detail_flat = expected - detail_up - detail_down
                    if (
                        detail_up == int(metric.get("advances", 0))
                        and detail_down == int(metric.get("declines", 0))
                        and detail_flat == int(metric.get("unchanged", 0))
                    ):
                        output[index_name]["constituents"] = detail_rows
    return output


def build_asset_component_breakdowns(
    instruments, updated, now_utc, participant_today=None, participant_changes_data=None
):
    """Build per-asset shadow scores from dated, asset-scoped, verified inputs only.

    This deliberately does not modify item['score']; the published PDMP score,
    Auto Run, signals and stale-data guard remain independent.
    """
    index_names = ("NIFTY", "SENSEX", "BANKNIFTY")
    search_assets = set(index_names) | {"GOLD", "SILVER", "CRUDEOIL"}
    index_news = experimental_news_scores(instruments, now_utc=now_utc)

    try:
        scan_stamp = dt.datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        if scan_stamp.tzinfo is None:
            scan_stamp = scan_stamp.replace(tzinfo=dt.timezone.utc)
        news_source_date = scan_stamp.astimezone(
            dt.timezone(dt.timedelta(hours=5, minutes=30))
        ).date().isoformat()
    except (TypeError, ValueError):
        news_source_date = str(updated or "")[:10]

    stock_basket_diagnostics = load_latest_stock_basket_diagnostics(news_source_date)
    try:
        with open("nse_index_option_oi.json", "r", encoding="utf-8") as handle:
            index_oi_archive = json.load(handle)
    except (OSError, json.JSONDecodeError):
        index_oi_archive = {}

    for name, item in (instruments or {}).items():
        if not isinstance(item, dict):
            continue
        components = {}
        excluded = {}
        client_context = None

        # News is per-card query output. Only timestamped headlines from the
        # last 24 hours are eligible; cross-index duplicates are excluded.
        if name in index_news:
            news_info = index_news[name]
            news_count = int(news_info.get("headline_count") or 0)
            news_score = news_info.get("news_score") if news_count else None
            # Keep the displayed age aligned with the same deduplicated,
            # timestamp-verified headlines that actually contributed to News.
            newest_age = min(
                (age for age in (news_info.get("eligible_ages_h") or [])
                 if isinstance(age, (int, float)) and math.isfinite(age)),
                default=None,
            )
            duplicate_note = "24h timestamped headlines; cross-index duplicates excluded"
        else:
            eligible_news = []
            ages = []
            for headline in item.get("headlines") or []:
                if not isinstance(headline, dict):
                    continue
                age = _timestamped_news_age_hours(headline, now_utc)
                score = _num(headline.get("score"))
                if age is None or score is None:
                    continue
                copied = dict(headline)
                copied["score"] = score
                copied["age_h"] = age
                eligible_news.append(copied)
                ages.append(age)
            news_count = len(eligible_news)
            news_score = shadow_weighted_news_score(eligible_news) if eligible_news else None
            newest_age = min(ages) if ages else None
            duplicate_note = "24h timestamped headlines; asset-specific card query"

        if news_score is not None and news_count > 0:
            eligible_headlines = [
                h for h in (item.get("headlines") or [])
                if isinstance(h, dict)
                and _timestamped_news_age_hours(h, now_utc) is not None
            ]
            fresh_publishers = (
                news_info.get("eligible_publishers") or []
                if name in index_news else sorted({
                    str(h.get("source")).strip()
                    for h in eligible_headlines if h.get("source")
                })
            )
            published_stamps = (
                sorted(news_info.get("eligible_published_at") or [])
                if name in index_news else sorted(
                    parse_utc_timestamp(h.get("published_at")).isoformat().replace("+00:00", "Z")
                    for h in eligible_headlines
                )
            )
            newest_published = parse_utc_timestamp(published_stamps[-1])
            component_source_date = newest_published.astimezone(
                dt.timezone(dt.timedelta(hours=5, minutes=30))
            ).date().isoformat()
            news_component = build_component(
                news_score,
                "Google News RSS · asset-specific card query",
                component_source_date,
                DEFAULT_COMPONENT_WEIGHTS["news"],
                observed_at=updated,
                newest_headline_published_at=published_stamps[-1],
                oldest_headline_published_at=published_stamps[0],
                source_date_basis="newest eligible publisher timestamp converted to IST; observed_at is scan time",
                evidence_count=news_count,
                publishers=fresh_publishers[:10],
                query=item.get("news_query"),
                newest_headline_age_h=round(newest_age, 2) if newest_age is not None else None,
                method="source-weighted, recency-weighted mean of headline sentiment points; clamped to -10..+10; shadow calibration pending",
                note=duplicate_note,
            )
            if news_component:
                components["news"] = news_component
        else:
            excluded["news"] = {
                "applicable": True,
                "included": False,
                "reason": "24 घंटे के भीतर की तारीख़/age वाली asset-specific खबरें उपलब्ध नहीं",
            }

        search_diagnostic = None
        # Search Score accepts only the asset's own one-day related-query seed.
        # Preserve the classified mix even when a neutral-only reading is withheld from Final.
        if name in search_assets:
            search_snapshot = (
                item.get("index_search_shadow") if name in index_names
                else item.get("asset_search_shadow")
            )
            if isinstance(search_snapshot, dict):
                diagnostic_fields = (
                    "valid", "seed", "source", "timeframe", "source_data_time",
                    "raw_queries", "in_scope_queries", "out_of_scope_queries", "out_of_scope_weight", "classified_queries", "unclassified_queries",
                    "classification_coverage_pct", "informational_queries", "informational_weight", "informational_terms", "bull_pct", "bear_pct",
                    "neutral_pct", "directional_bull_pct", "reason", "terms",
                    "unclassified_terms", "rising_queries",
                    "rising_classified_queries", "rising_direction_counts",
                    "rising_terms", "directional_query_diagnostic",
                )
                search_diagnostic = {
                    key: search_snapshot.get(key)
                    for key in diagnostic_fields
                    if key in search_snapshot
                }
            expected_search_seeds = {
                "NIFTY": "nifty",
                "SENSEX": "sensex",
                "BANKNIFTY": "bank nifty",
                "GOLD": "gold price",
                "SILVER": "silver price",
                "CRUDEOIL": "crude oil",
            }
            expected_seed = expected_search_seeds.get(name)
            actual_seed = (
                str(search_snapshot.get("seed") or "").strip().lower()
                if isinstance(search_snapshot, dict) else ""
            )
            if expected_seed and actual_seed != expected_seed:
                search_component, search_reason = (
                    None,
                    f"Asset seed mismatch: {name} के लिए '{expected_seed}' चाहिए, मिला '{actual_seed or 'missing'}'; cross-asset Search data Final से बाहर",
                )
            else:
                search_component, search_reason = search_component_from_snapshot(
                    search_snapshot,
                    now_utc=now_utc,
                    max_age_minutes=TRENDS_MAX_AGE_MINUTES,
                    weight=DEFAULT_COMPONENT_WEIGHTS["search"],
                )
            if search_component:
                components["search"] = search_component
            else:
                excluded["search"] = {
                    "applicable": True,
                    "included": False,
                    "reason": search_reason or "Asset-specific current Search reading unavailable",
                }

        if name in index_names:
            if name == "SENSEX":
                excluded["eod_oi"] = {
                    "applicable": True,
                    "included": False,
                    "source": "BSE official SENSEX index-option EOD data",
                    "reason": "SENSEX के लिए BSE का dated official UDiFF FO Bhavcopy और same-date BSE contract master अभी source, parse और exact contract coverage के साथ validate नहीं हुआ। NSE UDiFF में NIFTY/BANKNIFTY की जाँच को SENSEX पर लागू नहीं किया गया; इसलिए BSE EOD OI Final से बाहर है।",
                }
                excluded["futures"] = {
                    "applicable": True,
                    "included": False,
                    "source": "BSE SENSEX index-futures contract data",
                    "reason": "BSE SENSEX futures का dated contract-level snapshot और symbol-specific chronological holdout validation उपलब्ध नहीं; NSE participant CLIENT futures market-wide aggregate को SENSEX futures score नहीं माना गया।",
                }
            else:
                excluded["eod_oi"] = {
                    "applicable": True,
                    "included": False,
                    "source": "NSE option-chain symbol/expiry contract-level OI",
                    "reason": "5-Nov-2026 के official NSE UDiFF और same-date MII Contract Master में NIFTY (2,050/2,050) तथा BANKNIFTY (975/975) contracts के ID, symbol, CE/PE, expiry और strike का exact reconciliation verify हुआ। लेकिन इस live scan में यह dated per-index snapshot wired नहीं और 60-session holdout में directional edge प्रमाणित नहीं; इसलिए EOD OI Final से बाहर है। Participant CLIENT OI अलग market-wide aggregate है, इसे index-specific CLIENT position नहीं माना गया।",
                }
                excluded["futures"] = {
                    "applicable": True,
                    "included": False,
                    "source": "NSE index-futures contract data",
                    "reason": "CLIENT Index Futures उपलब्ध NSE participant report में market-wide aggregate है; symbol-specific directional score और robust holdout validation उपलब्ध नहीं, इसलिए withheld।",
                }
            excluded["stock_basket"] = {
                "applicable": True,
                "included": False,
                "source": "NSE Indices / BSE official constituent-and-weight files",
                "reason": "NIFTY 50 और NIFTY Bank के official monthly weights तथा dated cash prices research में verify हुए हैं, लेकिन इस live scan में full-basket daily snapshot wired नहीं और 60-session directional validation अभी pending है। SENSEX के पूरे 30 stocks के official weights उपलब्ध नहीं; इसलिए कोई 9-stock proxy या अनुमान Final में शामिल नहीं।",
            }
            client_context = client_oi_context(
                participant_today, participant_changes_data
            )
        elif name in ("GOLD", "SILVER"):
            excluded["eod_oi"] = {
                "applicable": True,
                "included": False,
                "source": "MCX official category-wise EOD OI report",
                "reason": "Dated MCX category-wise OI snapshot सत्यापित नहीं; MCX total contract OI को CLIENT category OI नहीं माना गया।",
            }
            excluded["futures"] = {
                "applicable": True,
                "included": False,
                "source": "MCX FUTCOM same-expiry daily OI",
                "reason": "Current contract OI का पिछले session के उसी expiry से verified comparison उपलब्ध नहीं; futures direction score withheld।",
            }

        final = combine_components(components, DEFAULT_COMPONENT_WEIGHTS)

        # The new visible Component Score is provisional and independent from
        # both the published PDMP score and the stricter verified-only shadow.
        provisional_components = dict(components)
        basket = stock_basket_diagnostics.get(name)
        if isinstance(basket, dict):
            basket_date = basket.get("source_date")
            basket_is_verified_for_score = (
                basket.get("status") == "complete_diagnostic"
                and basket.get("score_eligible") is True
                and basket.get("research_only") is not True
                and int(basket.get("expected") or 0) > 0
                and int(basket.get("matched") or 0) == int(basket.get("expected") or 0)
                and float(basket.get("coverage_pct") or 0) == 100.0
            )
            if (
                basket_is_verified_for_score
                and source_date_is_fresh(basket_date, news_source_date, max_age_days=3)
            ):
                basket_component = build_component(
                    basket.get("score"),
                    basket.get("source") or "Official NSE/BSE weighted constituent basket",
                    basket_date,
                    PROVISIONAL_WEIGHTS["stock_basket"],
                    method=basket.get("method"),
                    advances=basket.get("advances"),
                    declines=basket.get("declines"),
                    expected=basket.get("expected"),
                    matched=basket.get("matched"),
                    coverage_pct=basket.get("coverage_pct"),
                    validation_status=basket.get("validation_status") or "पूर्ण coverage और score eligibility सत्यापित",
                    weighting_method=basket.get("weighting_method") or "official constituent weights",
                )
                if basket_component:
                    provisional_components["stock_basket"] = basket_component
            else:
                excluded["stock_basket"] = {
                    "applicable": True, "included": False,
                    "source": basket.get("source") or "Official NSE/BSE CM UDiFF · equal-weight breadth",
                    "source_date": basket_date,
                    "reason": (
                        "पूरा daily basket diagnostic उपलब्ध है, लेकिन यह research-only/equal-weight है "
                        "या official weighted score eligibility, 100% constituent coverage और 60-session directional validation सत्यापित नहीं; "
                        "इसलिए Stock Basket केवल diagnostic रहेगा, provisional Final से बाहर।"
                        if basket.get("research_only") is True or basket.get("score_eligible") is False
                        else "Stock Basket का official snapshot scan date से 3 calendar days से अधिक पुराना, missing या incomplete है; provisional Final से बाहर रखा गया।"
                    ),
                }

        if name in index_names:
            if name != "SENSEX":
                oi_component = index_oi_balance_component(
                    index_oi_archive, name, news_source_date,
                    weight=PROVISIONAL_WEIGHTS["eod_oi"], sessions=5,
                    max_age_days=3,
                )
                if oi_component:
                    provisional_components["eod_oi"] = oi_component
                else:
                    excluded["eod_oi"] = {
                        "applicable": True, "included": False,
                        "source": "NSE F&O UDiFF · nearest-expiry PE/CE open-interest balance",
                        "reason": "सबसे नया official index OI observation scan date से 3 calendar days से अधिक पुराना या अधूरा है; provisional Final से बाहर रखा गया।",
                    }
            marketwide_components = client_marketwide_components(
                client_context, scan_date=news_source_date, max_age_days=3
            )
            # NSE participant-wise CLIENT OI/Futures is a market-wide aggregate,
            # not an index-specific observation. Keep diagnostics in context only.
            # Never inject them into NIFTY, SENSEX, or BANKNIFTY provisional Finals.
            for component_name in ("client_ce_pe", "client_futures"):
                diagnostic = marketwide_components.get(component_name)
                excluded[component_name] = {
                    "applicable": True,
                    "included": False,
                    "source": (
                        diagnostic.get("source") if isinstance(diagnostic, dict)
                        else (client_context or {}).get("source")
                    ) or "NSE participant-wise OI · CLIENT",
                    "source_date": (
                        diagnostic.get("source_date") if isinstance(diagnostic, dict)
                        else (client_context or {}).get("source_date")
                    ),
                    "scope": "market-wide CLIENT aggregate; not index-specific",
                    "reason": (
                        "CLIENT CE/PE और Futures पूरे बाजार का aggregate है, "
                        "NIFTY/SENSEX/BANKNIFTY का अलग-अलग डेटा नहीं। यह केवल "
                        "client_market_context में diagnostic रहेगा; index provisional Final से बाहर।"
                    ),
                }

        provisional_final = combine_components(
            provisional_components, PROVISIONAL_WEIGHTS
        )
        applicable_names = set(components)
        applicable_names.update(
            key for key, value in excluded.items()
            if isinstance(value, dict) and value.get("applicable", True)
        )
        included_count = len(components)
        applicable_count = len(applicable_names)
        coverage_pct = (
            round(included_count / applicable_count * 100.0, 2)
            if applicable_count else 0.0
        )
        coverage_status = (
            "unavailable" if included_count == 0
            else "complete" if included_count == applicable_count
            else "partial"
        )
        coverage_label = {
            "unavailable": "कोई सत्यापित component शामिल नहीं",
            "partial": "आंशिक कवरेज — Final केवल शामिल सत्यापित components पर आधारित",
            "complete": "सभी लागू components सत्यापित",
        }[coverage_status]
        item["component_breakdown"] = {
            "version": 1,
            "scope": "per-asset shadow score; published PDMP score is unchanged",
            "score_range": "-10..+10",
            "component_weights": DEFAULT_COMPONENT_WEIGHTS,
            "provisional_weights": PROVISIONAL_WEIGHTS,
            "components": components,
            "provisional_components": provisional_components,
            "provisional_final": provisional_final,
            "stock_basket_diagnostic": stock_basket_diagnostics.get(name),
            "excluded_components": excluded,
            "coverage": {
                "status": coverage_status,
                "label": coverage_label,
                "included_count": included_count,
                "applicable_count": applicable_count,
                "coverage_pct": coverage_pct,
                "meaning": "यह data-coverage है, prediction confidence या accuracy नहीं।",
            },
            "search_diagnostic": search_diagnostic,
            "client_market_context": client_context,
            "final": final,
            "formula": "sum(component_score × user-approved provisional_weight) / sum(weights of available provisional components)",
        }

    return {
        "mode": "per_asset_verified_components_shadow",
        "weights": DEFAULT_COMPONENT_WEIGHTS,
        "provisional_weights": PROVISIONAL_WEIGHTS,
        "score_range": "-10..+10",
        "search_rule": "Only fresh asset-specific Google Trends related_queries with timeframe now 1-d; no global NIFTY or 7-day fallback.",
        "news_rule": "Only publisher-timestamped asset-specific headlines no older than 24 hours; age is recomputed from published_at; source_date is newest eligible headline date in IST; cross-index duplicate stories excluded.",
        "participant_oi_scope": "NSE participant-wise CLIENT CE/PE/Futures is market-wide aggregate context, not index-specific and not included in index final scores.",
        "published_score_changed": False,
    }


def fetch_news(query):
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    # Fetch explicitly with a browser-like User-Agent and timeout. feedparser.parse(url)
    # can silently return an empty feed when the remote request is throttled or blocked.
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; PDMPScanner/1.0)",
                 "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        timeout=20,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    entries = list(getattr(feed, "entries", []) or [])
    if not entries:
        parse_error = str(getattr(feed, "bozo_exception", "") or "")[:180]
        print(f"NEWS_FETCH_EMPTY http={response.status_code} bytes={len(response.content)} "
              f"bozo={bool(getattr(feed, 'bozo', False))} error={parse_error!r} "
              f"query={query[:100]!r}")
    else:
        print(f"NEWS_FETCH_OK entries={len(entries)} http={response.status_code} "
              f"query={query[:100]!r}")
    items = []
    now = time.time()
    for e in entries[:15]:
        age_h = None
        published_at = None
        if getattr(e, "published_parsed", None):
            published_dt = dt.datetime(
                *e.published_parsed[:6], tzinfo=dt.timezone.utc
            )
            published_at = published_dt.isoformat().replace("+00:00", "Z")
            age_h = round((now - published_dt.timestamp()) / 3600, 1)
        title = e.title
        source = ""
        if " - " in title:
            title, source = title.rsplit(" - ", 1)
        items.append({"title": title, "source": source,
                      "link": getattr(e, "link", "") or "",
                      "score": headline_score(title), "age_h": age_h,
                      "published_at": published_at})
    items.sort(key=lambda x: (x["age_h"] is None, x["age_h"] or 0))
    return items


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default



# ---- NSE official MCP quotes (primary for NSE cash market) ----
NSE_MCP_URL = "https://mcp.nseindia.in/cmmkt/mcp"
NSE_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
NSE_QUOTE_CACHE = {"stocks": None, "loaded_at": 0}

NSE_MCP_HTTP = curl_requests.Session(impersonate="chrome124")
NSE_MCP_WARMED = False
NSE_MCP_SESSION_ID = None
NSE_MCP_PROTOCOL_VERSION = "2024-11-05"
NSE_MCP_TOOLS = {}
NSE_MCP_REQUEST_ID = 0
NSE_DIRECT_WARMED = False


def _nse_mcp_headers(session=True):
    headers = dict(NSE_MCP_HEADERS)
    if session and NSE_MCP_SESSION_ID:
        headers["Mcp-Session-Id"] = NSE_MCP_SESSION_ID
    return headers


def _nse_mcp_decode_response(response):
    """Decode JSON or the JSON-RPC event from an SSE Streamable HTTP response."""
    content_type = (response.headers.get("content-type", "") or "").lower()
    if "text/event-stream" in content_type:
        events = []
        for block in response.text.replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(
                line[5:].lstrip() for line in block.splitlines()
                if line.startswith("data:")
            )
            if data.strip():
                events.append(data)
        for data in reversed(events):
            try:
                return json.loads(data)
            except (ValueError, TypeError):
                continue
        raise RuntimeError("NSE MCP returned no valid JSON-RPC event")
    try:
        return response.json()
    except (ValueError, TypeError):
        raise RuntimeError(
            f"NSE MCP returned non-JSON response: HTTP {response.status_code}, "
            f"content-type={content_type!r}, body={response.text[:180]!r}"
        )


def _nse_mcp_post(payload, timeout=30, session=True):
    headers = _nse_mcp_headers(session=session)
    response = NSE_MCP_HTTP.post(NSE_MCP_URL, headers=headers, json=payload, timeout=timeout)
    if response.status_code not in (200, 202):
        body = re.sub(r"\s+", " ", response.text or "")[:180]
        raise RuntimeError(
            f"NSE MCP {payload.get('method')} HTTP {response.status_code}; "
            f"session={'yes' if headers.get('Mcp-Session-Id') else 'no'}; body={body!r}"
        )
    if response.status_code == 202 or not response.text.strip():
        return {}
    return _nse_mcp_decode_response(response)


def _nse_mcp_initialize():
    """Initialize an NSE MCP session; the server's initialized notification is fire-and-forget."""
    global NSE_MCP_SESSION_ID, NSE_MCP_PROTOCOL_VERSION, NSE_MCP_WARMED
    NSE_MCP_SESSION_ID = None
    # Reuse the Chrome-impersonated session and warm its TLS/cookie context
    # in the same way as the independently verified NSEPython server client.
    if not NSE_MCP_WARMED:
        for warm_url in (
            "https://www.nseindia.com",
            "https://www.nseindia.com/market-data/live-equity-market",
            "https://www.nseindia.com/option-chain",
        ):
            try:
                NSE_MCP_HTTP.get(warm_url, timeout=20)
            except Exception as warm_exc:
                print(f"NSE MCP session warm-up note: {str(warm_exc)[:120]}")
            time.sleep(1.2)
        NSE_MCP_WARMED = True
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": NSE_MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "nsepythonserver", "version": "2.101"},
        },
    }
    response = NSE_MCP_HTTP.post(
        NSE_MCP_URL, headers=dict(NSE_MCP_HEADERS), json=payload, timeout=30
    )
    if response.status_code != 200:
        body = re.sub(r"\\s+", " ", response.text or "")[:180]
        raise RuntimeError(f"NSE MCP initialize HTTP {response.status_code}: {body}")
    envelope = _nse_mcp_decode_response(response)
    if envelope.get("error"):
        raise RuntimeError(f"NSE MCP initialize error: {envelope['error']}")
    negotiated = (envelope.get("result") or {}).get("protocolVersion")
    if negotiated:
        NSE_MCP_PROTOCOL_VERSION = negotiated
    NSE_MCP_SESSION_ID = (
        response.headers.get("mcp-session-id")
        or response.headers.get("Mcp-Session-Id") or ""
    )
    # NSE's Streamable HTTP server may answer 404 to this notification.
    # The verified NSEPython client deliberately treats it as fire-and-forget.
    try:
        NSE_MCP_HTTP.post(
            NSE_MCP_URL, headers=_nse_mcp_headers(),
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            timeout=15,
        )
    except Exception:
        pass


def _nse_mcp_call_http(tool_name, arguments):
    """Call an NSE MCP tool using the server's verified initialize -> tools/call sequence."""
    global NSE_MCP_SESSION_ID, NSE_MCP_REQUEST_ID
    last_error = None
    for attempt in range(2):
        try:
            if attempt == 1 or not NSE_MCP_SESSION_ID:
                _nse_mcp_initialize()
            envelope = _nse_mcp_post({
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments or {}},
            }, timeout=60)
            rpc_error = envelope.get("error")
            if rpc_error:
                message = str(rpc_error)
                if "session" in message.lower() and attempt == 0:
                    last_error = RuntimeError(message)
                    NSE_MCP_SESSION_ID = None
                    continue
                raise RuntimeError(f"NSE MCP {tool_name} JSON-RPC error: {message[:240]}")
            result = envelope.get("result") or {}
            content = result.get("content") or []
            item = next((part for part in content if part.get("type") == "text"), None)
            if item is None:
                if "structuredContent" in result:
                    return result["structuredContent"]
                raise RuntimeError(f"NSE MCP {tool_name}: response has no text content")
            raw = item.get("text", "")
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                parsed = raw
            if result.get("isError"):
                raise RuntimeError(f"NSE MCP {tool_name} tool error: {str(parsed)[:240]}")
            if isinstance(parsed, dict) and parsed.get("error"):
                raise RuntimeError(f"NSE MCP {tool_name} source error: {str(parsed['error'])[:240]}")
            return parsed
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                NSE_MCP_SESSION_ID = None
                continue
    raise RuntimeError(f"NSE MCP {tool_name} failed: {last_error}")

def nse_mcp_call(tool_name, arguments):
    """Call NSE's unauthenticated live MCP endpoint; errors never become synthetic quotes."""
    try:
        return _nse_mcp_call_http(tool_name, arguments)
    except Exception as exc:
        print(f"NSE MCP {tool_name} unavailable: {str(exc)[:360]}")
        return None

def nse_mcp_list_tool_schema(tool_name):
    """Discover the live NSE tool schema; never infer input names from memory."""
    try:
        _nse_mcp_initialize()
        envelope = _nse_mcp_post({
            "jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}
        }, timeout=30)
        tools = (envelope.get("result") or {}).get("tools") or []
        tool = next((item for item in tools if item.get("name") == tool_name), None)
        if not tool:
            raise RuntimeError(f"{tool_name} is absent from live tools/list")
        schema = tool.get("inputSchema") or {}
        print(f"NSE MCP discovered schema {tool_name}: {json.dumps(schema, ensure_ascii=False)[:1800]}")
        return schema
    except Exception as exc:
        print(f"NSE MCP tools/list discovery failed for {tool_name}: {str(exc)[:300]}")
        return None


def nse_index_quote_arguments(tool_name, index_name):
    """Build arguments only from the live input schema returned by tools/list."""
    schema = nse_mcp_list_tool_schema(tool_name)
    if not isinstance(schema, dict):
        return None
    properties = schema.get("properties") or {}
    if not properties:
        return {} if not schema.get("required") else None
    normalized_target = re.sub(r"[^A-Z0-9]", "", index_name.upper())
    candidates = []
    for key, spec in properties.items():
        spec = spec if isinstance(spec, dict) else {}
        description = str(spec.get("description") or "")
        enum = spec.get("enum")
        if isinstance(enum, list):
            for value in enum:
                normalized_value = re.sub(r"[^A-Z0-9]", "", str(value).upper())
                if normalized_value == normalized_target:
                    candidates.append((key, value, 3))
                elif normalized_target in normalized_value or normalized_value in normalized_target:
                    candidates.append((key, value, 2))
        key_hint = re.sub(r"[^a-z]", "", key.lower())
        desc_hint = (key_hint + " " + description).lower()
        if any(token in desc_hint for token in ("index", "name", "symbol")):
            candidates.append((key, index_name, 1))
    if not candidates:
        print(f"NSE MCP {tool_name}: no index input field identified from live schema")
        return None
    candidates.sort(key=lambda item: item[2], reverse=True)
    key, value, _ = candidates[0]
    args = {key: value}
    required = schema.get("required") or []
    if any(item not in args for item in required):
        print(f"NSE MCP {tool_name}: schema has additional required fields {required}")
        return None
    print(f"NSE MCP {tool_name}: using schema-derived argument {key}={value}")
    return args

def nse_stock_universe():
    now = time.time()
    if NSE_QUOTE_CACHE["stocks"] is not None and now - NSE_QUOTE_CACHE["loaded_at"] < 240:
        return NSE_QUOTE_CACHE["stocks"]
    data = nse_mcp_call("cm_get_equity_stocks", {"limit": 500, "symbolFilter": ""})
    stocks = data.get("stocks", []) if isinstance(data, dict) else []
    if stocks:
        NSE_QUOTE_CACHE["stocks"] = {str(x.get("symbol", "")).upper(): x for x in stocks}
        NSE_QUOTE_CACHE["loaded_at"] = now
        return NSE_QUOTE_CACHE["stocks"]
    # Cache a failed batch attempt briefly so each watchlist symbol does not
    # repeat the same failing request; individual quote fallback remains available.
    NSE_QUOTE_CACHE["stocks"] = {}
    NSE_QUOTE_CACHE["loaded_at"] = now
    return {}

def bse_sensex_quote():
    """Return BSE's own SENSEX quote only when its exchange timestamp is for today."""
    try:
        url = "https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w"
        headers = {"Accept": "application/json, text/plain, */*",
                   "Referer": "https://www.bseindia.com/",
                   "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                   "Cache-Control": "no-cache"}
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("Table", []) if isinstance(payload, dict) else []
        row = next((item for item in rows if isinstance(item, dict) and
                    str(item.get("indxnm") or item.get("Index") or "").lower().replace(" ", "") in
                    ("sensexvalue", "sensex")), None)
        if row is None and isinstance(payload, dict):
            row = payload
        if not isinstance(row, dict):
            raise ValueError("BSE SENSEX response row missing")
        raw_price = row.get("ltp") or row.get("LTP") or row.get("CurrentIndexValue")
        raw_pct = row.get("perchg") or row.get("Change %") or row.get("PercentChange")
        raw_stamp = row.get("dttm") or row.get("DateTime") or row.get("timestamp")
        if raw_price is None or not raw_stamp:
            raise ValueError("BSE quote price/timestamp missing")
        price = float(str(raw_price).replace(",", ""))
        stamp_text = str(raw_stamp).strip()
        stamp = None
        for fmt in ("%d %b %y | %H:%M", "%d %b %Y | %H:%M",
                    "%d-%B-%Y %H:%M:%S", "%d-%b-%Y %H:%M:%S"):
            try:
                stamp = dt.datetime.strptime(stamp_text, fmt)
                break
            except ValueError:
                continue
        if stamp is None:
            raise ValueError(f"unrecognized BSE timestamp: {stamp_text}")
        ist_tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
        now_ist = dt.datetime.now(dt.timezone.utc).astimezone(ist_tz)
        stamp = stamp.replace(tzinfo=ist_tz)
        # During the live cash session require today's quote; outside session
        # allow the most recent previous close for up to 18 hours.
        session_open = india_cash_session_open(now_ist)
        if session_open and stamp.date() != now_ist.date():
            raise ValueError(f"BSE quote is not from today's live session: {stamp_text}")
        max_age_seconds = 30 * 60 if session_open else 96 * 60 * 60
        if (now_ist - stamp).total_seconds() > max_age_seconds or stamp > now_ist + dt.timedelta(minutes=2):
            raise ValueError(f"BSE quote timestamp outside allowed session window: {stamp_text}")
        source = "BSE" if session_open or (now_ist - stamp).total_seconds() <= 15 * 60 else "BSE · पिछला बंद भाव"
        return {"price": price, "stamp": stamp.strftime("%d-%b-%Y %H:%M:%S"),
                "source": source,
                "change_pct": float(str(raw_pct).replace("%", "").replace(",", "")) if raw_pct is not None else None}
    except Exception as exc:
        print(f"BSE SENSEX quote unavailable: {exc}")
        return None


def google_finance_quote(symbol, exchange, label):
    """Read a direct Google Finance quote with its explicit exchange timestamp."""
    try:
        ticker = f"{symbol}:{exchange}"
        url = "https://www.google.com/finance/quote/" + quote_plus(ticker)
        page = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                     "Accept-Language": "en-IN,en;q=0.9",
                     "Cache-Control": "no-cache"},
            timeout=15
        )
        page.raise_for_status()
        page_text = html.unescape(re.sub(r"<[^>]+>", " ", page.text))
        page_text = re.sub(r"\s+", " ", page_text)
        match = re.search(
            r"([A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2}:\d{2}\s*[AP]M\s*GMT([+-]\d{1,2}(?::\d{2})?))",
            page_text
        )
        if not match:
            raise ValueError("Google Finance exchange timestamp missing")
        # Google Finance sometimes prints GMT-5 and sometimes GMT-5:00.
        # Parse the explicit offset rather than assuming every market is in India.
        offset_text = match.group(2)
        offset_parts = re.fullmatch(r"([+-])(\d{1,2})(?::(\d{2}))?", offset_text)
        if not offset_parts:
            raise ValueError("Google Finance exchange timezone offset is invalid")
        sign = 1 if offset_parts.group(1) == "+" else -1
        hours = int(offset_parts.group(2))
        minutes = int(offset_parts.group(3) or 0)
        exchange_tz = dt.timezone(sign * dt.timedelta(hours=hours, minutes=minutes))
        now_utc = dt.datetime.now(dt.timezone.utc)
        stamp_naive = dt.datetime.strptime(match.group(1)[:match.group(1).rfind(" GMT")], "%b %d, %I:%M:%S %p")
        stamp = stamp_naive.replace(year=now_utc.astimezone(exchange_tz).year, tzinfo=exchange_tz)
        now_exchange = now_utc.astimezone(exchange_tz)
        age_seconds = (now_utc - stamp.astimezone(dt.timezone.utc)).total_seconds()
        if age_seconds < -120:
            raise ValueError("Google Finance quote timestamp is in the future")
        if exchange == "INDEXNASDAQ" or exchange == "INDEXDJX":
            # US indices: retain the dated last close across weekends, but reject
            # any quote older than the four-day closed-market safety window.
            max_age = 96 * 60 * 60
            if age_seconds > max_age:
                raise ValueError("US index quote is older than the allowed four-day closed-market window")
            time_label = stamp.strftime("%I:%M %p ET").lstrip("0")
        else:
            # During cash session require recent data; outside session accept
            # the dated previous close for up to four days, clearly labelled.
            session_open = india_cash_session_open(now_exchange)
            max_age = 15 * 60 if session_open else 96 * 60 * 60
            if age_seconds > max_age:
                raise ValueError("Google Finance quote is outside the live/previous-close window")
            time_label = stamp.strftime("%I:%M %p") + " " + ("IST" if offset_text == "+5:30" else "local")
            if not session_open and age_seconds > 15 * 60:
                time_label += " · पिछला बंद भाव"
        # Google Finance's current 2026 quote header uses N6SYTe for price
        # and ujg0He for the daily change. Never guess from unrelated page numbers.
        price_tag = re.search(
            r"<div\b[^>]*class=['\"][^'\"]*\bN6SYTe\b[^'\"]*['\"][^>]*>(.*?)</div>",
            page.text, re.I | re.S
        )
        if not price_tag:
            raise ValueError("Google Finance quote price element N6SYTe missing")
        price_text = html.unescape(re.sub(r"<[^>]+>", " ", price_tag.group(1)))
        price_match = re.search(r"([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.\d+)?|[0-9]+\.\d+)", price_text)
        if not price_match:
            raise ValueError("Google Finance quote price is not numeric")
        price = float(price_match.group(1).replace(",", ""))
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Google Finance returned an invalid price")
        change_tag = re.search(
            r"<div\b[^>]*class=['\"][^'\"]*\bujg0He\b[^'\"]*['\"][^>]*>(.*?)</div>",
            page.text, re.I | re.S
        )
        change_text = html.unescape(re.sub(r"<[^>]+>", " ", change_tag.group(1))) if change_tag else ""
        pct_match = re.search(r"([+-]\s*\d+(?:\.\d+)?\s*%)", change_text)
        if not pct_match:
            # Google Finance can change the daily-change CSS class. Its quote
            # header still places the signed 1D percentage immediately after
            # the exact quote price; only inspect that short quote-header span,
            # never the related-assets percentages elsewhere on the page.
            quote_pos = page_text.find(price_match.group(1))
            if quote_pos >= 0:
                quote_header = page_text[quote_pos:quote_pos + 180]
                pct_match = re.search(r"([+-]\s*\d+(?:\.\d+)?\s*%)", quote_header)
        change_pct = float(pct_match.group(1).replace("%", "").replace(" ", "")) if pct_match else None
        source_label = "Google Finance direct " + label + " quote"
        if age_seconds > 15 * 60:
            source_label += " · पिछला बंद भाव"
        return {"price": price, "stamp": stamp.strftime("%d-%b-%Y %H:%M:%S"),
                "date": stamp.date().isoformat(), "time": time_label,
                "source": source_label, "change_pct": change_pct}
    except Exception as exc:
        print(f"Google Finance {label} quote unavailable: {str(exc)[:160]}")
        return None


def google_finance_sensex_quote():
    return google_finance_quote("SENSEX", "INDEXBOM", "SENSEX")


def nse_web_indices_quote(index_name):
    """Read NSE's public all-indices feed with exchange timestamp validation."""
    try:
        for page_url in ("https://www.nseindia.com",
                         "https://www.nseindia.com/market-data/live-market-indices"):
            try:
                NSE_MCP_HTTP.get(page_url, timeout=20)
            except Exception:
                pass
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/market-data/live-market-indices",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Cache-Control": "no-cache",
        }
        response = NSE_MCP_HTTP.get("https://www.nseindia.com/api/allIndices",
                                    headers=headers, timeout=20)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("NSE allIndices response has no data array")
        target = re.sub(r"[^A-Z0-9]", "", index_name.upper())
        row = None
        for item in rows:
            if not isinstance(item, dict):
                continue
            label = next((item.get(k) for k in ("index", "indexName", "name", "index_name")
                          if item.get(k)), "")
            if re.sub(r"[^A-Z0-9]", "", str(label).upper()) == target:
                row = item
                break
        if row is None:
            raise ValueError(f"{index_name} not present in NSE allIndices response")
        price = next((row.get(k) for k in ("last", "lastPrice", "lastValue", "indexValue")
                      if row.get(k) not in (None, "")), None)
        stamp = next((row.get(k) for k in ("timeVal", "timestamp", "lastUpdateTime",
                                            "dateTime", "updatedAt")
                      if row.get(k)), None) or payload.get("timestamp")
        if price is None or stamp is None:
            raise ValueError("NSE allIndices row is missing price or exchange timestamp")
        parsed_stamp = None
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M",
                    "%d %b %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed_stamp = dt.datetime.strptime(str(stamp), fmt)
                break
            except ValueError:
                pass
        if parsed_stamp is None:
            parsed_stamp = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
        if parsed_stamp.tzinfo is None:
            parsed_stamp = parsed_stamp.replace(tzinfo=ist)
        else:
            parsed_stamp = parsed_stamp.astimezone(ist)
        now_ist = dt.datetime.now(dt.timezone.utc).astimezone(ist)
        age = (now_ist - parsed_stamp).total_seconds()
        max_age = 15 * 60 if india_cash_session_open(now_ist) else 96 * 60 * 60
        if age < -120 or age > max_age:
            raise ValueError(f"NSE index timestamp outside live/previous-close window: {stamp}")
        pct = next((row.get(k) for k in ("percentChange", "perChange", "changePercent")
                    if row.get(k) not in (None, "")), None)
        source = "NSE India allIndices API"
        if not india_cash_session_open(now_ist) and age > 15 * 60:
            source += " · पिछला बंद भाव"
        return {"price": float(price), "stamp": parsed_stamp.strftime("%d-%b-%Y %H:%M:%S"),
                "source": source,
                "change_pct": float(pct) if pct not in (None, "") else None}
    except Exception as exc:
        print(f"NSE allIndices {index_name} quote unavailable: {str(exc)[:220]}")
        return None




def parse_nse_direct_equity_payload(symbol, payload, now=None):
    """Parse one NSE GetQuoteApi response only when its symbol and exchange time match."""
    expected = str(symbol or "").strip().upper()
    rows = payload.get("equityResponse") if isinstance(payload, dict) else None
    if not expected or not isinstance(rows, list):
        return None
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    current = now or dt.datetime.now(dt.timezone.utc).astimezone(ist)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ist)
    else:
        current = current.astimezone(ist)

    for entry in rows:
        if not isinstance(entry, dict):
            continue
        meta = entry.get("metaData") or {}
        trade = entry.get("tradeInfo") or {}
        sec = entry.get("secInfo") or {}
        reported_symbol = next((str(source.get(key) or "").strip().upper()
                                for source in (meta, sec, entry)
                                for key in ("symbol", "tradingSymbol", "trading_symbol")
                                if source.get(key)), "")
        if reported_symbol != expected:
            continue

        raw_price = trade.get("lastPrice")
        if raw_price in (None, ""):
            raw_price = meta.get("lastPrice", meta.get("iep"))
        price = _num(raw_price)
        raw_stamp = meta.get("lastUpdateTime") or entry.get("lastUpdateTime")
        if price is None or price <= 0 or not raw_stamp:
            continue

        parsed_stamp = None
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed_stamp = dt.datetime.strptime(str(raw_stamp).strip(), fmt)
                break
            except ValueError:
                pass
        if parsed_stamp is None:
            try:
                parsed_stamp = dt.datetime.fromisoformat(str(raw_stamp).strip().replace("Z", "+00:00"))
            except ValueError:
                continue
        if parsed_stamp.tzinfo is None:
            parsed_stamp = parsed_stamp.replace(tzinfo=ist)
        else:
            parsed_stamp = parsed_stamp.astimezone(ist)

        age_seconds = (current - parsed_stamp).total_seconds()
        max_age = 15 * 60 if india_cash_session_open(current) else 96 * 60 * 60
        if age_seconds < -120 or age_seconds > max_age:
            continue

        previous = _num(meta.get("previousClose"))
        change_pct = None
        for key in ("pChange", "pchange", "ic_pchange"):
            if meta.get(key) not in (None, ""):
                change_pct = _num(meta.get(key))
                break
        if change_pct is None and previous and previous > 0:
            change_pct = round((price / previous - 1) * 100, 2)

        source = "NSE India direct quote API"
        if not india_cash_session_open(current) and age_seconds > 15 * 60:
            source += " · पिछला बंद भाव"
        return {
            "price": round(price, 2),
            "stamp": parsed_stamp.strftime("%d-%b-%Y %H:%M:%S"),
            "source": source,
            "change_pct": change_pct,
        }
    return None


def nse_direct_equity_quote(symbol):
    """Fetch a symbol-specific quote from NSE's public GetQuoteApi endpoint."""
    global NSE_DIRECT_WARMED
    try:
        symbol = str(symbol or "").strip().upper()
        if not symbol:
            return None
        page_url = "https://www.nseindia.com/get-quotes/equity?symbol=" + quote_plus(symbol)
        if not NSE_DIRECT_WARMED:
            for warm_url in ("https://www.nseindia.com", page_url):
                try:
                    warm = NSE_MCP_HTTP.get(warm_url, timeout=20)
                    warm.raise_for_status()
                except Exception as warm_exc:
                    print(f"NSE direct quote warm-up note: {str(warm_exc)[:120]}")
            NSE_DIRECT_WARMED = True
        url = ("https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi"
               "?functionName=getSymbolData&marketType=N&series=EQ&symbol=" + quote_plus(symbol))
        response = NSE_MCP_HTTP.get(url, headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": page_url,
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Cache-Control": "no-cache",
        }, timeout=20)
        response.raise_for_status()
        quote = parse_nse_direct_equity_payload(symbol, response.json())
        if quote:
            return quote
        raise ValueError("NSE direct response did not contain a matching symbol, valid price and fresh exchange timestamp")
    except Exception as exc:
        print(f"NSE direct equity {symbol} quote unavailable: {str(exc)[:200]}")
        return None


def nse_cash_quote(name, sym):
    """Prefer official exchange quotes; use Google Finance only as a timestamp-validated backup."""
    if name == "SENSEX":
        quote = bse_sensex_quote()
        if quote:
            return quote
        quote = google_finance_sensex_quote()
        # Google Finance may expose yesterday's close as a quote. Do not
        # publish it as today's SENSEX price when the cash session is open.
        if quote and "पिछला बंद भाव" in str(quote.get("source") or ""):
            return None
        return quote
    if name in ("NIFTY", "BANKNIFTY"):
        index_name = "NIFTY 50" if name == "NIFTY" else "NIFTY BANK"
        # NSE MCP index calls are unavailable; use the public NSE feed, then a
        # separately timestamped Google Finance quote. Never walk an undefined MCP payload.
        quote = nse_web_indices_quote(index_name)
        if quote:
            return quote
        google_symbol = "NIFTY_50" if name == "NIFTY" else "NIFTY_BANK"
        return google_finance_quote(google_symbol, "INDEXNSE", index_name)
    if sym.endswith(".NS"):
        symbol = sym[:-3].upper()
        # Never accept an unlabelled bulk row for a different share.
        # Use NSE's symbol-specific quote; Google Finance is the timestamped fallback.
        return nse_direct_equity_quote(symbol) or google_finance_quote(symbol, "NSE", symbol)
    return None


def nse_stamp_fields(stamp):
    """NSE timestamps are exchange-local; output DD/MM/YYYY and 12-hour IST."""
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            value = dt.datetime.strptime(str(stamp), fmt)
            return value.strftime("%d/%m/%Y"), value.strftime("%I:%M %p IST")
        except (TypeError, ValueError):
            pass
    return None, None


PRICE_CACHE = {}
SILVER_IMPORT_DUTY = 0.15  # अंतरराष्ट्रीय भाव से अनुमानित MCX-समतुल्य भाव तक
GST_RATE = 0.03  # दुकान/खरीद का अनुमान; एक्सचेंज भाव में GST नहीं
MCX_SILVER_FILE = "mcx_silver.json"

MCX_PUBLIC_URL = "https://upstox.com/commodity-market-trading/mcx-silver-price/"

# MCX quote parser is covered by the NSE quote-validation workflow's regression test.
class _UpstoxHistoryTableParser(HTMLParser):
    """Collect HTML table rows without relying on BeautifulSoup or external packages."""
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("td", "th") and self.row is not None and self.cell is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
            self.cell = None


def _parse_upstox_table_date(value):
    value = re.sub(r"\s+", " ", str(value or "").replace(",", " ")).strip()
    for fmt in ("%d %b %y", "%d %b %Y", "%d %B %y", "%d %B %Y",
                "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _upstox_previous_session_close(page_html, quote_date, expiry):
    """Get the prior trading session CLOSE for the exact same MCX contract."""
    parser = _UpstoxHistoryTableParser()
    parser.feed(page_html or "")
    current_date = dt.date.fromisoformat(str(quote_date))
    target_expiry = dt.date.fromisoformat(str(expiry))
    matching_rows = []
    for row in parser.rows:
        if len(row) < 6:
            continue
        row_date = _parse_upstox_table_date(row[0])
        row_expiry = _parse_upstox_table_date(row[1])
        if row_date and row_expiry == target_expiry:
            matching_rows.append((row_date, row))
    current_index = next((i for i, item in enumerate(matching_rows)
                          if item[0] == current_date), None)
    if not parser.rows:
        return None, None
    if current_index is None:
        raise ValueError("Upstox historical table has no row for the MCX quote date and selected expiry")
    for row_date, row in matching_rows[current_index + 1:]:
        if row_date < current_date:
            raw_close = re.sub(r"[^0-9.]", "", row[5])
            close = float(raw_close) if raw_close else 0.0
            if math.isfinite(close) and close > 0:
                return round(close, 2), row_date.isoformat()
    raise ValueError("Upstox historical table has no previous-session close for the same MCX contract")


def parse_upstox_mcx_quote(page_html, min_price, max_price, label, require_fresh=True):
    """Extract MCX quote and calculate daily change from the same contract's prior-session CLOSE."""
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page_html)))
    matches = re.findall(
        r"(?:₹|&#8377;|&#x20b9;|INR\s*)\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]{4,6}(?:\.[0-9]{1,2})?)",
        page_html, re.I
    )
    prices = []
    for item in matches:
        try:
            value = float(item.replace(",", ""))
            if min_price <= value <= max_price:
                prices.append(value)
        except ValueError:
            continue
    if not prices:
        raise ValueError(f"{label} price missing or outside validation range")
    stamp_match = re.search(
        r"Last updated on\s*(\d{1,2}\s+[A-Za-z]{3},?\s+\d{4})\s*\|\s*(\d{1,2}:\d{2})\s*IST",
        text, re.I
    )
    if not stamp_match:
        raise ValueError(f"{label} source timestamp missing")
    stamp = dt.datetime.strptime(stamp_match.group(1).replace(",", ""), "%d %b %Y")
    hour, minute = map(int, stamp_match.group(2).split(":"))
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    stamp = stamp.replace(hour=hour, minute=minute, tzinfo=ist)
    now = dt.datetime.now(dt.timezone.utc).astimezone(ist)
    age_minutes = (now - stamp).total_seconds() / 60
    if require_fresh and (age_minutes < -2 or age_minutes > 45):
        raise ValueError(f"{label} source quote is outside the 45-minute freshness window")
    expiry_match = re.search(
        r"Expiry:\s*(\d{1,2})\s+([A-Za-z]+),?\s*(\d{2,4})", text, re.I
    )
    expiry = None
    if expiry_match:
        expiry_text = f"{expiry_match.group(1)} {expiry_match.group(2)} {expiry_match.group(3)}"
        for fmt in ("%d %B %y", "%d %B %Y", "%d %b %y", "%d %b %Y"):
            try:
                expiry = dt.datetime.strptime(expiry_text, fmt).date()
                break
            except ValueError:
                pass
    if expiry is None:
        table_probe = _UpstoxHistoryTableParser()
        table_probe.feed(page_html or "")
        if table_probe.rows:
            raise ValueError(f"{label} historical table exists but selected contract expiry could not be verified")
    previous_close, previous_close_date = (
        _upstox_previous_session_close(page_html, stamp.date().isoformat(), expiry.isoformat())
        if expiry else (None, None)
    )
    if previous_close is None:
        prev_match = re.search(r"Prev\.?\s*Close\s*₹\s*([\d,]+(?:\.\d+)?)", text, re.I)
        if not prev_match:
            raise ValueError(f"{label} verified previous-session close missing")
        previous_close = float(prev_match.group(1).replace(",", ""))
        if previous_close <= 0:
            raise ValueError(f"{label} previous close is invalid")
    change_pct = round((prices[0] / previous_close - 1) * 100, 2)
    return {
        "price": round(prices[0], 2), "previous_close": previous_close,
        "previous_close_date": previous_close_date,
        "change_pct": change_pct, "date": stamp.date().isoformat(),
        "time": stamp.strftime("%H:%M"), "source_time": stamp.strftime("%Y-%m-%d %H:%M IST"),
        "expiry": expiry.isoformat() if expiry else None,
    }

def india_cash_session_open(now=None):
    """NSE/BSE regular cash session, in IST."""
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    now = now or dt.datetime.now(dt.timezone.utc).astimezone(ist)
    return now.weekday() < 5 and dt.time(9, 15) <= now.time() < dt.time(15, 30)


def mcx_session_open(now=None):
    """MCX weekday trading session, in IST."""
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    now = now or dt.datetime.now(dt.timezone.utc).astimezone(ist)
    return now.weekday() < 5 and dt.time(9, 0) <= now.time() <= dt.time(23, 30)


MCX_MARKET_PAGE_URL = "https://www.mcxindia.com/market-data/market-watch"
MCX_BHAVCOPY_PAGE_URL = "https://www.mcxindia.com/market-data/bhavcopy"
MCX_MARKET_API_URL = "https://www.mcxindia.com/market-data/market-watch/GetMarketWatch?culture=en"
MCX_HTTP = curl_requests.Session(impersonate="chrome124")
MCX_HTTP_WARMED = False


def mcx_reference_age_minutes(data, now=None):
    try:
        stamp = dt.datetime.strptime(str(data.get("source_time") or ""), "%Y-%m-%d %H:%M IST")
        ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
        stamp = stamp.replace(tzinfo=ist)
        current = now or dt.datetime.now(dt.timezone.utc).astimezone(ist)
        if current.tzinfo is None:
            current = current.replace(tzinfo=ist)
        else:
            current = current.astimezone(ist)
        return (current - stamp).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def mcx_reference_is_fresh(data, max_age_minutes=45, now=None):
    """During MCX hours require a fresh quote; outside hours allow last session close."""
    age = mcx_reference_age_minutes(data, now)
    if age is None:
        return False
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    current = now or dt.datetime.now(dt.timezone.utc).astimezone(ist)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ist)
    else:
        current = current.astimezone(ist)
    allowed_age = max_age_minutes if mcx_session_open(current) else 96 * 60
    return -2 <= age <= allowed_age


def mcx_reference_fallback_needed(data, now=None):
    """Use public-page fallback only during MCX hours when cached quote is stale/missing."""
    return mcx_session_open(now) and not mcx_reference_is_fresh(data, now=now)


def mcx_reference_is_live(data, now=None):
    age = mcx_reference_age_minutes(data, now)
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    current = now or dt.datetime.now(dt.timezone.utc).astimezone(ist)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ist)
    else:
        current = current.astimezone(ist)
    return mcx_session_open(current) and age is not None and -2 <= age <= 45


def fetch_mcx_market_watch_rows():
    """Read MCX's own public Market Watch JSON after warming its browser-facing page."""
    global MCX_HTTP_WARMED
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Origin": "https://www.mcxindia.com",
        "Referer": MCX_MARKET_PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Cache-Control": "no-cache",
    }
    errors = []
    if not MCX_HTTP_WARMED:
        try:
            page = MCX_HTTP.get(MCX_MARKET_PAGE_URL, headers=headers, timeout=20)
            page.raise_for_status()
            MCX_HTTP_WARMED = True
        except Exception as exc:
            errors.append("page warm-up: " + str(exc)[:120])

    # Current Market Watch route first; legacy ASP.NET route is a compatibility fallback.
    try:
        response = MCX_HTTP.get(MCX_MARKET_API_URL, headers=headers, timeout=25)
        response.raise_for_status()
        payload = response.json()
        rows = ((payload.get("data") or {}).get("Data") if isinstance(payload, dict) else None)
        if not isinstance(rows, list) and isinstance(payload, dict):
            rows = (payload.get("d") or {}).get("Data")
        if isinstance(rows, list) and rows:
            MCX_HTTP_WARMED = True
            return rows
        errors.append("current route returned no Data rows")
    except Exception as exc:
        errors.append("current route: " + str(exc)[:140])

    try:
        legacy_headers = dict(headers)
        legacy_headers["Content-Type"] = "application/json"
        response = MCX_HTTP.post(
            "https://www.mcxindia.com/backpage.aspx/GetMarketWatch",
            data="",
            headers=legacy_headers,
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        rows = ((payload.get("d") or {}).get("Data") if isinstance(payload, dict) else None)
        if isinstance(rows, list) and rows:
            MCX_HTTP_WARMED = True
            return rows
        errors.append("legacy route returned no d.Data rows")
    except Exception as exc:
        errors.append("legacy route: " + str(exc)[:140])

    raise ValueError("MCX Market Watch unavailable: " + " | ".join(errors))


def fetch_mcx_bhavcopy_rows(trade_date):
    """Fetch one date's contract-wise rows from MCX's official Bhavcopy endpoint."""
    target_date = dt.date.fromisoformat(str(trade_date))
    date_display = target_date.strftime("%d/%m/%Y")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Origin": "https://www.mcxindia.com",
        "Referer": MCX_BHAVCOPY_PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Cache-Control": "no-cache",
    }
    page = MCX_HTTP.get(MCX_BHAVCOPY_PAGE_URL, headers=headers, timeout=25)
    page.raise_for_status()
    meta = re.search(
        r"<meta\b(?=[^>]*\bname\s*=\s*['\"]X-XSRF-Token['\"])[^>]*>",
        page.text, re.I
    )
    token = ""
    if meta:
        content = re.search(r"\bcontent\s*=\s*(['\"])(.*?)\1", meta.group(0), re.I | re.S)
        if content:
            token_markup = html.unescape(content.group(2))
            token_match = re.search(r"\bvalue\s*=\s*(['\"])(.*?)\1", token_markup, re.I | re.S)
            token = token_match.group(2) if token_match else token_markup.strip()
    if not token:
        try:
            token = MCX_HTTP.cookies.get("XSRF-TOKEN") or ""
        except Exception:
            token = ""
    if not token:
        raise ValueError("MCX Bhavcopy request-verification token missing")

    api_headers = dict(headers)
    api_headers["__requestverificationtoken"] = token
    api_headers["Content-Type"] = "application/json"
    endpoint = MCX_BHAVCOPY_PAGE_URL.rstrip("/") + "/GetDateWiseBhavCopy"
    response = MCX_HTTP.get(
        endpoint,
        params={"InstrumentName": "ALL", "fromDate": date_display},
        headers=api_headers,
        timeout=30,
    )
    response.raise_for_status()
    content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        # MCX sometimes returns an HTML/empty gateway response with HTTP 200.
        # Do not log the body: it may contain request tokens or session data.
        raise ValueError(
            "MCX Bhavcopy non-JSON response "
            f"(HTTP {response.status_code}, content-type={content_type or 'missing'}, "
            f"bytes={len(response.content)}): {type(exc).__name__}"
        ) from exc
    box = payload.get("d") or payload.get("data") or payload
    if isinstance(box, str):
        try:
            box = json.loads(box)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                "MCX Bhavcopy JSON envelope contains invalid nested data "
                f"(HTTP {response.status_code}, content-type={content_type or 'missing'}): "
                f"{type(exc).__name__}"
            ) from exc
    rows = box.get("Data") if isinstance(box, dict) else None
    if not isinstance(rows, list):
        raise ValueError("MCX Bhavcopy returned no contract rows")
    return rows


def mcx_bhavcopy_contract_close(rows, symbol, expiry, trade_date):
    """Return the official FUTCOM close for one exact symbol/expiry/date."""
    target_expiry = dt.date.fromisoformat(str(expiry))
    target_date = dt.date.fromisoformat(str(trade_date))
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("InstrumentName") or "").strip().upper() != "FUTCOM":
            continue
        if str(row.get("Symbol") or "").strip().upper() != str(symbol).upper():
            continue
        raw_expiry = str(row.get("ExpiryDate") or "").strip().upper()
        parsed_expiry = None
        for fmt in ("%d%b%Y", "%d%b%y", "%d-%b-%Y", "%d-%b-%y"):
            try:
                parsed_expiry = dt.datetime.strptime(raw_expiry, fmt).date()
                break
            except ValueError:
                pass
        if parsed_expiry != target_expiry:
            continue

        row_date = None
        for raw_date in (row.get("DateDisplay"), row.get("Date")):
            if raw_date in (None, ""):
                continue
            date_text = str(raw_date).strip()
            for fmt in ("%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    row_date = dt.datetime.strptime(date_text, fmt).date()
                    break
                except ValueError:
                    pass
            if row_date is None:
                epoch = re.search(r"/Date\((-?\d+)", date_text)
                if epoch:
                    row_date = dt.datetime.fromtimestamp(
                        int(epoch.group(1)) / 1000, dt.timezone.utc
                    ).astimezone(ist).date()
            if row_date is not None:
                break
        if row_date is not None and row_date != target_date:
            continue

        close = _num(row.get("Close"))
        if close is not None and math.isfinite(close) and close > 0:
            return round(close, 2)
    return None


def parse_mcx_market_watch_rows(rows, now=None):
    """Keep only timestamped MCX FUTCOM rows and select the highest-OI contract per commodity."""
    if not isinstance(rows, list):
        return {}
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    current = now or dt.datetime.now(dt.timezone.utc).astimezone(ist)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ist)
    else:
        current = current.astimezone(ist)
    bounds = {"GOLD": (50000, 500000), "SILVER": (50000, 500000), "CRUDEOIL": (3000, 30000)}
    month_numbers = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                     "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
    candidates = {key: [] for key in bounds}

    for row in rows[:1000]:
        if not isinstance(row, dict) or str(row.get("InstrumentName") or "").strip().upper() != "FUTCOM":
            continue
        symbol = str(row.get("Symbol") or "").strip().upper()
        if symbol not in bounds:
            continue
        raw_price = _num(row.get("LTP"))
        low, high = bounds[symbol]
        if raw_price is None or not low <= raw_price <= high:
            continue
        raw_stamp = str(row.get("LTTValue") or row.get("LTT") or "").strip()
        parsed_stamp = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                    "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
            try:
                parsed_stamp = dt.datetime.strptime(raw_stamp, fmt)
                break
            except ValueError:
                pass
        if parsed_stamp is None:
            continue
        if parsed_stamp.tzinfo is None:
            parsed_stamp = parsed_stamp.replace(tzinfo=ist)
        else:
            parsed_stamp = parsed_stamp.astimezone(ist)

        expiry_raw = str(row.get("ExpiryDate") or "").strip().upper()
        match = re.fullmatch(r"(\d{2})([A-Z]{3})(\d{4})", expiry_raw)
        if not match or match.group(2) not in month_numbers:
            continue
        try:
            expiry = dt.date(int(match.group(3)), month_numbers[match.group(2)], int(match.group(1)))
        except ValueError:
            continue

        oi = _num(row.get("OpenInterest")) or 0
        previous = _num(row.get("PreviousClose"))
        pct = _num(row.get("PercentChange"))
        source_time = parsed_stamp.strftime("%Y-%m-%d %H:%M IST")
        quote = {
            "price": round(raw_price, 2),
            "previous_close": round(previous, 2) if previous and previous > 0 else None,
            "change_pct": round(pct, 2) if pct is not None else None,
            "date": parsed_stamp.date().isoformat(),
            "time": parsed_stamp.strftime("%I:%M %p IST").lstrip("0"),
            "source_time": source_time,
            "expiry": expiry.isoformat(),
            "unit": str(row.get("Unit") or "").strip(),
            "open_interest": int(oi),
        }
        if mcx_reference_is_fresh(quote, now=current):
            candidates[symbol].append(quote)

    selected = {}
    for symbol, quotes in candidates.items():
        if quotes:
            quotes.sort(key=lambda item: (-item["open_interest"], item["expiry"]))
            selected[symbol] = quotes[0]
    return selected


def refresh_mcx_market_watch_quotes():
    """Refresh GOLD, SILVER and CRUDEOIL from the exchange's own FUTCOM Market Watch."""
    try:
        rows = fetch_mcx_market_watch_rows()
        quotes = parse_mcx_market_watch_rows(rows)
        files = {
            "GOLD": (GOLD_MCX_FILE, "mcx_price_per_10g", "previous_mcx_price_per_10g"),
            "SILVER": (MCX_SILVER_FILE, "mcx_price_per_kg", "previous_mcx_price_per_kg"),
            "CRUDEOIL": (CRUDE_MCX_FILE, "mcx_price_per_bbl", "previous_mcx_price_per_bbl"),
        }
        updated_symbols = set()
        bhavcopy_cache = {}
        bhavcopy_source = "MCX India official Bhavcopy · same FUTCOM contract"
        for symbol, quote in quotes.items():
            path, price_key, previous_key = files[symbol]
            data = load_json(path, {})
            verified_previous = None
            verified_change = None
            verified_previous_date = None

            # एक ही quote-date और expiry के लिए सत्यापित close को reuse करें;
            # इससे हर 30-मिनट स्कैन में Bhavcopy की अतिरिक्त request नहीं होगी।
            cached_previous = _num(data.get(previous_key))
            if (
                data.get("date") == quote["date"]
                and data.get("contract_expiry") == quote["expiry"]
                and data.get("previous_close_source") == bhavcopy_source
                and cached_previous is not None and cached_previous > 0
                and data.get("previous_close_date")
            ):
                verified_previous = cached_previous
                verified_previous_date = data.get("previous_close_date")
            else:
                target_date = dt.date.fromisoformat(quote["date"]) - dt.timedelta(days=1)
                for _ in range(7):
                    while target_date.weekday() >= 5:
                        target_date -= dt.timedelta(days=1)
                    date_key = target_date.isoformat()
                    if date_key not in bhavcopy_cache:
                        try:
                            bhavcopy_cache[date_key] = fetch_mcx_bhavcopy_rows(date_key)
                        except Exception as bhavcopy_error:
                            bhavcopy_cache[date_key] = None
                            print(f"MCX Bhavcopy {date_key} fetch failed: {str(bhavcopy_error)[:160]}")
                    rows_for_date = bhavcopy_cache[date_key]
                    if rows_for_date is None:
                        break
                    verified_previous = mcx_bhavcopy_contract_close(
                        rows_for_date, symbol, quote["expiry"], date_key
                    )
                    if verified_previous is not None:
                        verified_previous_date = date_key
                        break
                    target_date -= dt.timedelta(days=1)

            if verified_previous is not None:
                verified_change = round((quote["price"] / verified_previous - 1) * 100, 2)
            else:
                print(f"MCX {symbol} daily change withheld: official Bhavcopy has no verified prior close for the same FUTCOM expiry")
            data.update({
                price_key: quote["price"],
                previous_key: verified_previous,
                "previous_close_date": verified_previous_date,
                "previous_close_source": bhavcopy_source if verified_previous is not None else None,
                "change_pct": verified_change,
                "date": quote["date"],
                "time": quote["time"],
                "source_time": quote["source_time"],
                "source": "MCX India official Market Watch · FUTCOM",
                "source_url": MCX_MARKET_PAGE_URL,
                "contract_expiry": quote["expiry"],
                "unit": quote["unit"],
                "open_interest": quote["open_interest"],
                "note": "Official MCX futures Market Watch quote. Gold/Silver display adds a separate 3% GST estimate.",
            })
            with open(path, "w", encoding="utf-8") as out:
                json.dump(data, out, ensure_ascii=False, indent=2)
            updated_symbols.add(symbol)
            change_label = f"{verified_change:+.2f}%" if verified_change is not None else "daily change unverified"
            print(f"MCX official {symbol}: ₹{quote['price']:,.2f} ({quote['source_time']}, expiry={quote['expiry']}, {change_label}, OI={quote['open_interest']})")
        if not updated_symbols:
            print("MCX official Market Watch returned no fresh GOLD/SILVER/CRUDEOIL FUTCOM rows.")
        return updated_symbols
    except Exception as exc:
        print(f"MCX official Market Watch refresh failed; trying timestamped public-page fallback: {str(exc)[:220]}")
        return set()

def refresh_mcx_silver_reference():
    """Fetch the timestamped MCX SILVER quote from Upstox; never substitute SI=F."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
        response = requests.get(MCX_PUBLIC_URL, headers=headers, timeout=15)
        response.raise_for_status()
        quote = parse_upstox_mcx_quote(response.text, 50000, 500000, "MCX SILVER")
        data = load_json(MCX_SILVER_FILE, {})
        data.update({
            "mcx_price_per_kg": quote["price"],
            "previous_mcx_price_per_kg": quote["previous_close"],
            "change_pct": quote["change_pct"], "date": quote["date"],
            "previous_close_date": quote["previous_close_date"],
            "previous_close_source": "Upstox historical table · same MCX expiry",
            "contract_expiry": quote["expiry"], "source_time": quote["source_time"],
            "source": "Upstox public MCX Silver quote; source timestamp validated; not exchange-certified",
            "source_url": MCX_PUBLIC_URL,
            "note": "Public-page quote, not exchange-certified live feed. Dashboard display applies 3% GST estimate."
        })
        with open(MCX_SILVER_FILE, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        print(f"MCX silver quote refreshed: ₹{quote['price']:,.2f}/kg ({quote['source_time']}, {quote['change_pct']:+.2f}%)")
        return True
    except Exception as exc:
        print(f"MCX silver refresh failed; retaining source timestamp for freshness check: {str(exc)[:180]}")
        return False


def silver_display_price(international_inr_per_kg=None):
    """Show only a recent, timestamp-validated MCX quote plus the GST estimate."""
    try:
        mcx = load_json(MCX_SILVER_FILE, {})
        raw = mcx.get("mcx_price_per_kg")
        value = float(raw) if raw is not None else None
        if value is not None and math.isfinite(value) and value > 0 and mcx_reference_is_fresh(mcx):
            label = "MCX live quote + 3% GST Estimate" if mcx_reference_is_live(mcx) else "MCX पिछला बंद भाव + 3% GST Estimate"
            return round(value * (1 + GST_RATE), 2), str(mcx.get("date", "")), label
        if not mcx_reference_is_fresh(mcx):
            return None, "", "MCX SILVER quote पुराना है — नया भाव उपलब्ध नहीं"
    except Exception as exc:
        print(f"MCX silver reference unavailable: {exc}")
    return None, "", "MCX SILVER भाव उपलब्ध नहीं — अनुमान नहीं दिखाया गया"



GOLD_MCX_FILE = "mcx_gold.json"
GOLD_PUBLIC_URL = "https://upstox.com/commodity-market-trading/mcx-gold-price/"

def refresh_mcx_gold_reference():
    """Fetch the timestamped MCX GOLD quote from Upstox; never stamp scrape time as quote time."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
        response = requests.get(GOLD_PUBLIC_URL, headers=headers, timeout=15)
        response.raise_for_status()
        quote = parse_upstox_mcx_quote(response.text, 50000, 500000, "MCX GOLD")
        data = load_json(GOLD_MCX_FILE, {})
        data.update({
            "mcx_price_per_10g": quote["price"],
            "previous_mcx_price_per_10g": quote["previous_close"],
            "change_pct": quote["change_pct"], "date": quote["date"],
            "previous_close_date": quote["previous_close_date"],
            "previous_close_source": "Upstox historical table · same MCX expiry",
            "contract_expiry": quote["expiry"], "source_time": quote["source_time"],
            "source": "Upstox public MCX Gold quote; source timestamp validated; not exchange-certified",
            "source_url": GOLD_PUBLIC_URL,
            "note": "Public-page quote per 10g; dashboard display adds 3% GST estimate. Jewellery making charges are not included."
        })
        with open(GOLD_MCX_FILE, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        print(f"MCX gold quote refreshed: ₹{quote['price']:,.2f}/10g ({quote['source_time']}, {quote['change_pct']:+.2f}%)")
        return True
    except Exception as exc:
        print(f"MCX gold refresh failed; retaining source timestamp for freshness check: {str(exc)[:180]}")
        return False


def gold_display_price():
    """Show only a recent, timestamp-validated MCX quote plus the GST estimate."""
    try:
        data = load_json(GOLD_MCX_FILE, {})
        value = float(data.get("mcx_price_per_10g"))
        if math.isfinite(value) and value > 0 and mcx_reference_is_fresh(data):
            label = "MCX live quote × 3% GST" if mcx_reference_is_live(data) else "MCX पिछला बंद भाव × 3% GST Estimate"
            return round(value * (1 + GST_RATE), 2), str(data.get("date", "")), label
        if not mcx_reference_is_fresh(data):
            return None, "", "MCX GOLD quote पुराना है — नया भाव उपलब्ध नहीं"
    except Exception as exc:
        print(f"MCX gold reference unavailable: {exc}")
    return None, "", "MCX Gold भाव उपलब्ध नहीं — अनुमान नहीं दिखाया गया"



CRUDE_MCX_FILE = "mcx_crudeoil.json"
CRUDE_PUBLIC_URL = "https://upstox.com/commodity-market-trading/mcx-crudeoil-price/"

def refresh_mcx_crude_reference():
    """Fetch MCX CRUDEOIL and derive daily change from prior-session close of the same expiry."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
        response = requests.get(CRUDE_PUBLIC_URL, headers=headers, timeout=15)
        response.raise_for_status()
        quote = parse_upstox_mcx_quote(response.text, 3000, 30000, "MCX CRUDEOIL")
        data = load_json(CRUDE_MCX_FILE, {})
        data.update({
            "mcx_price_per_bbl": quote["price"],
            "previous_mcx_price_per_bbl": quote["previous_close"],
            "previous_close_date": quote["previous_close_date"],
            "previous_close_source": "Upstox historical table · same MCX expiry",
            "change_pct": quote["change_pct"],
            "date": quote["date"], "time": quote["time"],
            "source_time": quote["source_time"],
            "contract_expiry": quote["expiry"],
            "source": "Upstox public MCX CRUDEOIL quote; historical close verified; not exchange-certified",
            "source_url": CRUDE_PUBLIC_URL,
            "note": "Public MCX contract quote. Daily % is calculated against the previous trading session close for the same expiry."
        })
        with open(CRUDE_MCX_FILE, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        print(f"MCX crude quote refreshed: ₹{quote['price']:,.2f}/BBL ({quote['date']} {quote['time']}, {quote['change_pct']:+.2f}%)")
        return True
    except Exception as exc:
        print(f"MCX crude refresh failed; retaining original quote timestamp if available: {str(exc)[:180]}")
        return False

def crude_display_quote():
    """Return only a recent, source-timestamped MCX CRUDEOIL quote."""
    data = load_json(CRUDE_MCX_FILE, {})
    try:
        value = float(data.get("mcx_price_per_bbl"))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("invalid MCX crude quote")
        if not mcx_reference_is_fresh(data):
            raise ValueError("MCX CRUDEOIL source quote is older than 45 minutes")
        source = str(data.get("source") or "MCX CRUDEOIL")
        if not mcx_reference_is_live(data):
            source = "MCX पिछला बंद भाव · " + source
        return (round(value, 2), str(data.get("date") or ""),
                str(data.get("time") or ""), source, data.get("change_pct"))
    except (TypeError, ValueError):
        return None, "", "", "MCX CRUDEOIL भाव उपलब्ध नहीं", None

def compact_ist_time(value):
    """Convert a stored YYYY-MM-DD HH:MM IST timestamp to a short 12-hour label."""
    try:
        stamp = dt.datetime.strptime(str(value), "%Y-%m-%d %H:%M IST")
        return stamp.strftime("%I.%M %p IST").lstrip("0")
    except (TypeError, ValueError):
        return None


def daily_returns(sym):
    """तारीख -> उस दिन का % बदलाव; कीमत को जरूरत के अनुसार रुपये में दिखाने हेतु कैश करें।"""
    closes = yf.Ticker(sym).history(period="1mo", interval="1d")["Close"]
    today_utc = dt.datetime.now(dt.timezone.utc).date()
    # Yahoo भारतीय शेयर/इंडेक्स की daily candle तारीख IST में देता है।
    # UTC तारीख से तुलना करने पर आधी रात के बाद (IST में) पिछला पूरा दिन
    # गलती से छँट जाता था; भारतीय symbols के लिए IST की तारीख इस्तेमाल करें।
    ist_now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
    indian = sym.endswith(".NS") or sym in ("^NSEI", "^BSESN", "^NSEBANK", "^INDIAVIX")
    today_market_date = ist_now.date() if indian else today_utc
    indian_closed = indian and ist_now.weekday() < 5 and (ist_now.hour, ist_now.minute) >= (15, 45)
    # Save the previous completed session close separately. After the market
    # closes, today's close may be included for display, but it must never
    # become the comparison base (otherwise index change incorrectly becomes 0%).
    previous_session = [(stamp.date().isoformat(), float(value)) for stamp, value in closes.items()
                        if stamp.date() < today_market_date and math.isfinite(float(value))]
    previous_close_date, previous_close = previous_session[-1] if previous_session else (None, None)
    keep = [(d.date() < today_market_date) or (indian_closed and d.date() == ist_now.date()) for d in closes.index]
    closes = closes[keep]
    last_close = float(closes.iloc[-1]) if len(closes) else None
    last_close_date = closes.index[-1].date().isoformat() if len(closes) else None
    if last_close is not None and not math.isfinite(last_close):
        last_close = None
    # Yahoo GC=F और SI=F अमेरिकी डॉलर प्रति ट्रॉय औंस में हैं।
    # USD/INR से बदलकर भारत में प्रचलित इकाई दिखाएँ: Gold ₹/10 ग्राम, Silver ₹/किलो।
    if last_close is not None and sym in ("GC=F", "SI=F"):
        try:
            fx = yf.Ticker("INR=X").history(period="5d", interval="1d")["Close"].dropna()
            rate = float(fx.iloc[-1]) if len(fx) else None
            if rate is not None and math.isfinite(rate) and rate > 0:
                last_close = last_close * rate
                if sym == "GC=F":
                    last_close *= (10.0 / 31.1034768)  # INR प्रति 10 ग्राम
                else:
                    last_close *= (1000.0 / 31.1034768)  # INR प्रति किलो
            else:
                last_close = None
        except Exception:
            last_close = None
    PRICE_CACHE[sym] = round(last_close, 2) if last_close is not None else None
    PRICE_CACHE[sym + "_PREV_CLOSE"] = (previous_close if indian_closed and previous_close is not None
                                         else last_close)
    PRICE_CACHE[sym + "_PREV_CLOSE_DATE"] = (
        previous_close_date if indian_closed and previous_close is not None else last_close_date
    )
    if sym == "BZ=F":
        crude_price, crude_date, crude_time, crude_source, crude_change = crude_display_quote()
        PRICE_CACHE[sym] = crude_price
        PRICE_CACHE[sym + "_DATE"] = crude_date
        PRICE_CACHE[sym + "_TIME"] = crude_time
        PRICE_CACHE[sym + "_SOURCE"] = crude_source
        PRICE_CACHE[sym + "_CHANGE_PCT"] = crude_change
    if sym == "BTC-USD":
        # Bitcoin quote is supplied only by the 1-minute intraday path below.
        # Never fall back to an hourly/daily candle as the scan-time price.
        PRICE_CACHE[sym] = None
        PRICE_CACHE["BTC-USD_SOURCE"] = None
        PRICE_CACHE["BTC-USD_DATE"] = None
        PRICE_CACHE["BTC-USD_CHANGE_PCT"] = None
    if sym == "GC=F":
        gold_price, gold_date, gold_source = gold_display_price()
        PRICE_CACHE[sym] = gold_price
        PRICE_CACHE["GC=F_SOURCE"] = gold_source
        PRICE_CACHE["GC=F_DATE"] = gold_date
        gold_meta = load_json(GOLD_MCX_FILE, {})
        gold_stamp = str(gold_meta.get("source_time") or "")
        PRICE_CACHE["GC=F_TIME"] = compact_ist_time(gold_stamp) if mcx_reference_is_fresh(gold_meta) and gold_stamp[:10] == str(gold_meta.get("date") or "") else None
        try:
            PRICE_CACHE["GC=F_CHANGE_PCT"] = float(gold_meta.get("change_pct")) if mcx_reference_is_fresh(gold_meta) else None
        except (TypeError, ValueError):
            PRICE_CACHE["GC=F_CHANGE_PCT"] = None
    if sym == "SI=F":
        silver_price, silver_date, silver_source = silver_display_price(last_close)
        PRICE_CACHE[sym] = silver_price
        PRICE_CACHE["SI=F_SOURCE"] = silver_source
        PRICE_CACHE["SI=F_DATE"] = silver_date
        silver_meta = load_json(MCX_SILVER_FILE, {})
        silver_stamp = str(silver_meta.get("source_time") or "")
        PRICE_CACHE["SI=F_TIME"] = compact_ist_time(silver_stamp) if mcx_reference_is_fresh(silver_meta) and silver_stamp[:10] == str(silver_meta.get("date") or "") else None
        # Use Upstox's source-reported daily change, not the previous scan's quote.
        try:
            PRICE_CACHE["SI=F_CHANGE_PCT"] = float(silver_meta.get("change_pct")) if mcx_reference_is_fresh(silver_meta) else None
        except (TypeError, ValueError):
            PRICE_CACHE["SI=F_CHANGE_PCT"] = None
    out = {}
    for i in range(1, len(closes)):
        prev, cur = float(closes.iloc[i - 1]), float(closes.iloc[i])
        if math.isnan(prev) or math.isnan(cur) or prev == 0:
            continue
        d = closes.index[i].strftime("%Y-%m-%d")
        out[d] = round((cur / prev - 1) * 100, 2)
    return out



def intraday_quote(sym):
    """Best-effort fresh Yahoo 5-minute quote; timestamps are displayed in India time.
    yfinance is tried first; the public Yahoo chart endpoint is a no-key fallback."""
    indian_cash = sym.endswith(".NS") or sym in ("^NSEI", "^BSESN", "^NSEBANK")
    bitcoin = sym == "BTC-USD"
    supported = indian_cash or sym == "INR=X" or bitcoin
    if not supported:
        return None

    def validate_and_format(price, stamp_utc, source):
        now_utc = dt.datetime.now(dt.timezone.utc)
        age = (now_utc - stamp_utc).total_seconds() / 60
        bar_ist = stamp_utc + dt.timedelta(hours=5, minutes=30)
        now_ist = now_utc + dt.timedelta(hours=5, minutes=30)
        today_ist = now_ist.date()
        # Intraday candles remain subject to the strict freshness guard.
        # They are never used as the SENSEX price; SENSEX comes from BSE's direct quote.
        max_age = 3 if bitcoin else 15 if indian_cash else 60
        if age < -2 or age > max_age or (indian_cash and bar_ist.date() != today_ist):
            return None
        if not math.isfinite(price) or price <= 0:
            return None
        return {"price": round(price, 4 if sym == "INR=X" else 2),
                "date": bar_ist.date().isoformat(),
                "time": bar_ist.strftime("%I.%M %p IST").lstrip("0"),
                "source": source}

    # Bitcoin must use the latest executed spot trade, not an OHLC candle.
    # Coinbase's public ticker returns trade price and the trade timestamp.
    if bitcoin:
        try:
            response = requests.get(
                "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=12
            )
            response.raise_for_status()
            ticker = response.json()
            stamp = dt.datetime.fromisoformat(str(ticker["time"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=dt.timezone.utc)
            else:
                stamp = stamp.astimezone(dt.timezone.utc)
            result = validate_and_format(float(ticker["price"]), stamp,
                                         "Coinbase BTC-USD latest executed trade")
            if not result:
                raise ValueError("Coinbase latest trade is older than 3 minutes or has an invalid timestamp")

            # Compare the live Coinbase trade with Coinbase's own last completed
            # UTC daily candle. Never use Yahoo's BTC-USD close as the baseline:
            # exchanges can differ materially during volatile sessions.
            now_utc = dt.datetime.now(dt.timezone.utc)
            today_utc = now_utc.date()
            previous_day = today_utc - dt.timedelta(days=1)
            start = dt.datetime.combine(previous_day, dt.time.min, tzinfo=dt.timezone.utc)
            end = dt.datetime.combine(today_utc, dt.time.min, tzinfo=dt.timezone.utc)
            candle_url = (
                "https://api.exchange.coinbase.com/products/BTC-USD/candles"
                f"?start={start.isoformat().replace('+00:00', 'Z')}"
                f"&end={end.isoformat().replace('+00:00', 'Z')}&granularity=86400"
            )
            candle_response = requests.get(
                candle_url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=12
            )
            candle_response.raise_for_status()
            candles = candle_response.json()
            previous_candle = next(
                (row for row in candles if isinstance(row, list) and len(row) >= 5
                 and int(row[0]) == int(start.timestamp())),
                None
            )
            if previous_candle is None:
                raise ValueError("Coinbase previous UTC daily candle is missing")
            previous_close = float(previous_candle[4])
            if not math.isfinite(previous_close) or previous_close <= 0:
                raise ValueError("Coinbase previous UTC daily close is invalid")
            result["previous_close"] = previous_close
            result["change_pct"] = round((result["price"] / previous_close - 1) * 100, 2)
            result["previous_close_date"] = previous_day.isoformat()
            return result
        except Exception as exc:
            print(f"Bitcoin latest-trade quote unavailable: {str(exc)[:160]}")
            return None

    # Other instruments retain their existing 5-minute quote path.
    interval = "5m"
    try:
        h = yf.Ticker(sym).history(period="1d", interval=interval, prepost=False)
        if h is not None and not h.empty and "Close" in h.columns:
            stamp = h.index[-1].to_pydatetime()
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=dt.timezone.utc)
            else:
                stamp = stamp.astimezone(dt.timezone.utc)
            result = validate_and_format(float(h["Close"].iloc[-1]), stamp,
                                         "Yahoo Finance 1-minute quote" if bitcoin else "Yahoo Finance 5-minute quote")
            if result:
                return result
    except Exception as exc:
        print(f"yfinance intraday quote unavailable {sym}: {str(exc)[:120]}")

    # Direct public Yahoo chart endpoint fallback. Try query2 before query1:
    # Yahoo may rate-limit one hostname independently. No key/crumb is used.
    errors = []
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            url = ("https://" + host + "/v8/finance/chart/"
                   + quote_plus(sym) + "?range=1d&interval=" + interval + "&includePrePost=false")
            response = requests.get(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Accept": "application/json",
                "Cache-Control": "no-cache"
            }, timeout=12)
            # HTTP 429 usually reflects an IP/session-wide throttle. Trying the
            # second Yahoo hostname immediately adds another request without
            # improving the chance of success, so stop the fallback chain.
            if response.status_code == 429:
                message = "HTTP 429 rate limited; alternate Yahoo host retry skipped"
                errors.append(host + ": " + message)
                print(f"Yahoo chart intraday fallback stopped {sym}: {message}")
                break
            response.raise_for_status()
            payload = response.json()
            chart = (payload.get("chart") or {}).get("result") or []
            if not chart:
                raise ValueError("Yahoo chart response has no result")
            item = chart[0]
            stamps = item.get("timestamp") or []
            quotes = ((item.get("indicators") or {}).get("quote") or [])
            closes = quotes[0].get("close") if quotes else None
            if not stamps or not closes or len(stamps) != len(closes):
                raise ValueError("Yahoo chart timestamps/close values missing")
            valid = [(int(ts), float(close)) for ts, close in zip(stamps, closes)
                     if ts is not None and close is not None]
            if not valid:
                raise ValueError("Yahoo chart has no completed price bars")
            ts, price = valid[-1]
            stamp = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
            result = validate_and_format(price, stamp,
                                         "Yahoo Finance public 1-minute chart (" + host + ")" if bitcoin else "Yahoo Finance public 5-minute chart (" + host + ")")
            if result:
                return result
            raise ValueError("Yahoo chart quote is outside the freshness window (3 minutes for Bitcoin)")
        except Exception as exc:
            errors.append(host + ": " + str(exc)[:140])
            print(f"Yahoo chart intraday fallback unavailable {sym} via {host}: {str(exc)[:140]}")
    # SENSEX: if Yahoo's intraday feed is unavailable, try BSE's public
    # real-time index endpoint. Keep the quote only when BSE supplies a
    # parseable source timestamp within the same 15-minute freshness window.
    if sym == "^BSESN":
        try:
            response = requests.get(
                "https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w",
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.bseindia.com/"
                },
                timeout=12
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload if isinstance(payload, list) else (
                payload.get("Table") or payload.get("Table1") or
                payload.get("Data") or payload.get("data") or [payload]
            )
            for row in rows:
                if not isinstance(row, dict):
                    continue
                fields = {re.sub(r"[^a-z]", "", str(k).lower()): v for k, v in row.items()}
                raw_price = next((fields[k] for k in
                                  ("ltp", "sensexvalue", "indexvalue", "currentvalue")
                                  if fields.get(k) not in (None, "")), None)
                raw_stamp = next((fields[k] for k in
                                  ("datetime", "dttm", "timestamp", "updatedtime", "tradetime")
                                  if fields.get(k) not in (None, "")), None)
                if raw_price is None or raw_stamp is None:
                    continue
                stamp_text = str(raw_stamp).strip()
                stamp = None
                for fmt in ("%d %b %y | %H:%M", "%d %b %Y | %H:%M",
                            "%d %b %y %H:%M", "%d %b %Y %H:%M",
                            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        stamp = dt.datetime.strptime(stamp_text, fmt)
                        break
                    except ValueError:
                        pass
                if stamp is None:
                    try:
                        stamp = dt.datetime.fromisoformat(stamp_text.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
                stamp = stamp.astimezone(dt.timezone.utc)
                result = validate_and_format(float(str(raw_price).replace(",", "")), stamp,
                                             "BSE India public SENSEX quote")
                if result:
                    print("SENSEX quote recovered from BSE public endpoint")
                    return result
        except Exception as exc:
            print(f"BSE SENSEX live quote unavailable: {str(exc)[:160]}")

    # Google Finance public quote page is a no-key fallback for SENSEX.
    # Accept only a page timestamp from today's IST session and within 15 minutes.
    if sym == "^BSESN":
        try:
            page = requests.get(
                "https://www.google.com/finance/quote/SENSEX:INDEXBOM",
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                         "Accept-Language": "en-IN,en;q=0.9"},
                timeout=15
            )
            page.raise_for_status()
            html_text = html.unescape(re.sub(r"<[^>]+>", " ", page.text))
            html_text = re.sub(r"\s+", " ", html_text)
            stamp_match = re.search(
                r"([A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2}:\d{2}\s*[AP]M\s*GMT\+5:30)",
                html_text
            )
            if not stamp_match:
                raise ValueError("Google Finance quote timestamp not found")
            stamp_local = dt.datetime.strptime(stamp_match.group(1), "%b %d, %I:%M:%S %p GMT+5:30")
            now_local = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
            stamp_local = stamp_local.replace(year=now_local.year,
                                               tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
            stamp_utc = stamp_local.astimezone(dt.timezone.utc)
            price_match = re.search(
                r"BSE SENSEX.{0,500}?([0-9]{1,3}(?:,[0-9]{3})+\.\d{2})",
                html_text
            )
            if not price_match:
                # SSR page puts the quote before the overview metadata; use
                # the first formatted index-level number before the timestamp.
                prefix = html_text[:stamp_match.start()]
                candidates = re.findall(r"(?<![0-9])([0-9]{1,3}(?:,[0-9]{3})+\.\d{2})(?![0-9])", prefix)
                if not candidates:
                    raise ValueError("Google Finance SENSEX price not found")
                raw_price = candidates[-1]
            else:
                raw_price = price_match.group(1)
            result = validate_and_format(float(raw_price.replace(",", "")), stamp_utc,
                                         "Google Finance SENSEX quote")
            if result:
                print("SENSEX quote recovered from Google Finance public page")
                return result
            raise ValueError("Google Finance quote is outside today's 15-minute freshness window")
        except Exception as exc:
            print(f"Google Finance SENSEX quote unavailable: {str(exc)[:160]}")

    if errors:
        print("All Yahoo chart hosts failed for " + sym + ": " + " | ".join(errors))
    return None

def nse_special_session_dates():
    """आधिकारिक NSE calendar में दर्ज weekend trading sessions की तारीखें."""
    calendar = load_json(EXCHANGE_CALENDAR_FILE, {})
    sessions = calendar.get("special_sessions") if isinstance(calendar, dict) else {}
    if not isinstance(sessions, dict):
        return set()
    valid = set()
    for value in sessions:
        try:
            valid.add(dt.date.fromisoformat(value).isoformat())
        except (TypeError, ValueError):
            continue
    return valid


def fetch_participant_oi(base_date=None, lookback_days=7):
    """NSE official participant-wise OI: daily EOD, not a live feed.
    base_date lets the caller fetch the latest archived snapshot on/before a target date."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,text/plain,*/*",
               "Referer": "https://www.nseindia.com/"}
    last_error = "NSE participant OI CSV unavailable"
    if base_date is None:
        base_date = dt.datetime.now(dt.timezone.utc).date()
    elif isinstance(base_date, str):
        base_date = dt.date.fromisoformat(base_date)
    special_session_dates = nse_special_session_dates()
    for offset in range(0, max(0, int(lookback_days)) + 1):
        day = base_date - dt.timedelta(days=offset)
        if day.weekday() >= 5 and day.isoformat() not in special_session_dates:
            continue
        url = f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{day.strftime('%d%m%Y')}.csv"
        try:
            response = requests.get(url, headers=headers, timeout=12)
            if response.status_code != 200 or not response.text.strip():
                last_error = f"NSE returned HTTP {response.status_code}"
                continue
            # NSE archive files can include a title/preamble before the actual CSV header.
            raw_lines = [line for line in response.text.lstrip("\ufeff").splitlines() if line.strip()]
            header_at = next((i for i, line in enumerate(raw_lines)
                              if "client type" in line.lower() or "client_type" in line.lower()), None)
            if header_at is None:
                last_error = "NSE CSV header row not found"
                continue
            reader = csv.DictReader(raw_lines[header_at:])
            rows = list(reader)
            if not rows or not reader.fieldnames:
                last_error = "NSE CSV has no data rows"
                continue
            def norm(value):
                return re.sub(r"[^a-z0-9]", "", str(value).replace("\ufeff", "").lower()).strip()
            fields = {norm(k): k for k in reader.fieldnames if k}
            type_key = next((fields[k] for k in ("clienttype", "participant", "participanttype") if k in fields), None)
            if not type_key:
                last_error = "NSE CSV participant column not recognized after header row"
                continue
            wanted = {
                "future_index_long": ("futureindexlong",),
                "future_index_short": ("futureindexshort",),
                "index_call_long": ("optionindexcalllong", "indexcalllong"),
                "index_call_short": ("optionindexcallshort", "indexcallshort"),
                "index_put_long": ("optionindexputlong", "indexputlong"),
                "index_put_short": ("optionindexputshort", "indexputshort"),
                "future_stock_long": ("futurestocklong",),
                "future_stock_short": ("futurestockshort",),
                "stock_call_long": ("optionstockcalllong", "stockcalllong"),
                "stock_call_short": ("optionstockcallshort", "stockcallshort"),
                "stock_put_long": ("optionstockputlong", "stockputlong"),
                "stock_put_short": ("optionstockputshort", "stockputshort"),
            }
            colmap = {out: next((fields[k] for k in aliases if k in fields), None)
                      for out, aliases in wanted.items()}
            if not any(colmap.values()):
                last_error = "NSE CSV position columns not recognized"
                continue
            participants = {}
            for row in rows:
                label = str(row.get(type_key, "")).strip().lower()
                if label not in ("client", "dii", "fii", "pro"):
                    continue
                item = {}
                for out, col in colmap.items():
                    try:
                        item[out] = int(float(str(row.get(col, "0")).replace(",", ""))) if col else None
                    except (ValueError, TypeError):
                        item[out] = None
                for prefix in ("future_index", "index_call", "index_put", "future_stock"):
                    item[prefix + "_net"] = (item.get(prefix + "_long") or 0) - (item.get(prefix + "_short") or 0)
                participants[label.upper()] = item
            if len(participants) < 4:
                last_error = "NSE CSV missing participant rows"
                continue
            return {"ok": True, "stale": False, "date": day.isoformat(),
                    "source": "NSE official participant-wise OI",
                    "scope": "F&O participant totals; stock F&O is aggregate, not per individual stock",
                    "participants": participants}
        except Exception as exc:
            last_error = str(exc)[:180]
    return {"ok": False, "stale": True, "date": None,
            "source": "NSE official participant-wise OI", "error": last_error,
            "participants": {}}


def _completed_5m_bars(sym):
    """NSE cash instrument की केवल पूरी हुई 5-minute candles लौटाएँ (UTC end time)."""
    if not (sym.endswith(".NS") or sym in ("^NSEI", "^NSEBANK", "^BSESN")):
        return []
    try:
        frame = yf.Ticker(sym).history(period="5d", interval="5m", prepost=False)
        if frame is None or frame.empty or "Close" not in frame.columns:
            return []
        now = dt.datetime.now(dt.timezone.utc)
        bars = []
        for stamp, close in frame["Close"].dropna().items():
            bar_start = stamp.to_pydatetime() if hasattr(stamp, "to_pydatetime") else stamp
            if bar_start.tzinfo is None:
                bar_start = bar_start.replace(tzinfo=dt.timezone.utc)
            else:
                bar_start = bar_start.astimezone(dt.timezone.utc)
            bar_end = bar_start + dt.timedelta(minutes=5)
            price = float(close)
            if bar_end <= now and math.isfinite(price) and price > 0:
                bars.append({"time": bar_end, "price": price})
        return sorted(bars, key=lambda item: item["time"])
    except Exception as exc:
        print(f"Contrarian 5-minute candles unavailable {sym}: {str(exc)[:160]}")
        return []


def _update_intraday_horizon(event, field, minutes, bars):
    """लक्ष्य समय के बाद 10 मिनट के भीतर की पहली पूरी candle लें; gap को अनुमान न बनाएँ."""
    horizon = event.get(field)
    if not isinstance(horizon, dict) or horizon.get("status") != "pending":
        return
    try:
        baseline = dt.datetime.fromisoformat(event["baseline_time"].replace("Z", "+00:00"))
        if baseline.tzinfo is None:
            baseline = baseline.replace(tzinfo=dt.timezone.utc)
        baseline_price = float(event["baseline_price"])
        if not math.isfinite(baseline_price) or baseline_price <= 0:
            raise ValueError("invalid baseline price")
    except (KeyError, TypeError, ValueError):
        horizon.update({"status": "unavailable", "reason": "शुरुआती भाव/समय उपलब्ध नहीं"})
        return

    target = baseline + dt.timedelta(minutes=minutes)
    latest = bars[-1]["time"] if bars else None
    candidate = next((bar for bar in bars
                      if target <= bar["time"] <= target + dt.timedelta(minutes=10)), None)
    if candidate:
        move = round((candidate["price"] / baseline_price - 1) * 100, 2)
        if abs(move) < 0.000001:
            outcome = "neutral"
        else:
            same_sign = (move > 0) == (float(event.get("score") or 0) > 0)
            outcome = "continued" if same_sign else "reversed"
        horizon.update({
            "status": "complete", "price": round(candidate["price"], 4),
            "time": candidate["time"].isoformat(timespec="seconds").replace("+00:00", "Z"),
            "change_pct": move, "outcome": outcome,
        })
    elif dt.datetime.now(dt.timezone.utc) > target + dt.timedelta(minutes=10):
        # Yahoo 429/खाली response पर अगले Auto Run में दोबारा जाँचें।
        # लक्ष्य candle के बाद 60 मिनट तक retry करें; उसके बाद ही unavailable।
        checked_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        if dt.datetime.now(dt.timezone.utc) <= target + dt.timedelta(minutes=60):
            horizon["last_checked_at"] = checked_at
            horizon["retry_count"] = int(horizon.get("retry_count") or 0) + 1
            horizon["status"] = "pending"
            horizon["reason"] = "पूरी candle अभी स्रोत से नहीं मिली; अगले Auto Run में फिर जाँच होगी"
        else:
            horizon.update({
                "status": "unavailable",
                "reason": "लक्ष्य candle 60 मिनट की retry अवधि में भी स्रोत से नहीं मिली",
                "last_checked_at": checked_at,
            })


def update_contrarian(events, name, score, today_str, returns, sym):
    """±6 समाचार स्कोर इवेंट; अगले सत्र के साथ अलग 30m/60m परिणाम भी दर्ज करें."""
    key = f"{today_str}|{name}"
    existing = next((e for e in events if e.get("key") == key), None)
    if abs(score) >= CONTRARIAN_LIMIT and not SKIP_EVENTS and existing is None:
        event_time = dt.datetime.now(dt.timezone.utc)
        event = {"key": key, "date": today_str, "instrument": name,
                 "score": score, "event_time_utc": event_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
                 "outcome": None, "next_change": None,
                 "baseline_price": None, "baseline_time": None, "baseline_attempted": False,
                 "intraday_source": "Yahoo Finance completed 5-minute candles",
                 "after_30m": {"status": "pending", "reason": "शुरुआती पूरी candle का इंतज़ार"},
                 "after_60m": {"status": "pending", "reason": "शुरुआती पूरी candle का इंतज़ार"}}
        events.append(event)
        existing = event

    relevant = [e for e in events if e.get("instrument") == name]
    # Legacy next-session result handling is unchanged.
    for e in relevant:
        if e.get("outcome") in ("continued", "reversed") and e.get("next_change") is not None:
            try:
                if float(e["next_change"]) == 0:
                    e["outcome"] = "neutral"
            except (TypeError, ValueError):
                pass
        if e.get("outcome") is None:
            later = sorted(d for d in returns if d > e["date"])
            if later:
                nxt = returns[later[0]]
                e["next_change"] = nxt
                if nxt == 0:
                    e["outcome"] = "neutral"
                else:
                    same_sign = (nxt > 0) == (float(e.get("score") or 0) > 0)
                    e["outcome"] = "continued" if same_sign else "reversed"

    # Intraday horizons and the original baseline are retried by Auto Run.
    # Never substitute a later session's candle for the event-time baseline.
    needs_bars = any(
        e.get("baseline_time") and any(
            isinstance(e.get(field), dict) and e[field].get("status") == "pending"
            for field in ("after_30m", "after_60m")
        ) for e in relevant
    )
    new_baseline_needed = bool(
        existing and not existing.get("baseline_time")
        and existing.get("baseline_attempted") is not True
        and existing.get("event_time_utc")
    )
    bars = _completed_5m_bars(sym) if (needs_bars or new_baseline_needed) else []
    if new_baseline_needed:
        event_time = dt.datetime.fromisoformat(existing["event_time_utc"].replace("Z", "+00:00"))
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=dt.timezone.utc)
        # Pick the latest completed candle at/before the signal timestamp.
        # A candle after the signal would introduce look-ahead bias.
        candidates = [bar for bar in bars if bar["time"] <= event_time]
        baseline = candidates[-1] if candidates else None
        baseline_age = ((event_time - baseline["time"]).total_seconds() / 60
                        if baseline else None)
        event_age = (dt.datetime.now(dt.timezone.utc) - event_time).total_seconds() / 60
        if baseline and 0 <= baseline_age <= 15:
            existing["baseline_attempted"] = True
            existing["baseline_price"] = round(baseline["price"], 4)
            existing["baseline_time"] = baseline["time"].isoformat(timespec="seconds").replace("+00:00", "Z")
            existing["after_30m"] = {"status": "pending"}
            existing["after_60m"] = {"status": "pending"}
        elif event_age > 30:
            existing["baseline_attempted"] = True
            reason = "सिग्नल समय के आसपास की पूरी 5-मिनट candle 30 मिनट में नहीं मिली"
            existing["after_30m"] = {"status": "unavailable", "reason": reason}
            existing["after_60m"] = {"status": "unavailable", "reason": reason}
        else:
            # Keep it retryable while the event-time candle may still be fetched.
            existing["after_30m"] = {"status": "pending", "reason": "सिग्नल समय की पूरी candle फिर खोजी जाएगी"}
            existing["after_60m"] = {"status": "pending", "reason": "सिग्नल समय की पूरी candle फिर खोजी जाएगी"}
    # Run the horizon state machine even when Yahoo returns no bars:
    # pending checks must still retry and eventually time out honestly.
    for e in relevant:
        if not e.get("baseline_time"):
            continue
        _update_intraday_horizon(e, "after_30m", 30, bars)
        _update_intraday_horizon(e, "after_60m", 60, bars)


def update_divergence(events, name, score, change, today_str, returns, headlines=None):
    """⚡ संकेत दर्ज करें: स्कोर और कीमत की दिशा अलग हो।
    नतीजा उसी दिन के सत्र से भरता है जिस दिन संकेत बना।
    'sentiment' = खबर की दिशा में चाल, 'price' = कीमत की दिशा में चाल।
    यह इतिहास का मिलान है, भविष्य की गारंटी नहीं।"""
    # A missing live quote has no valid price direction; skip divergence
    # bookkeeping rather than aborting the entire market-data scan.
    if change is None:
        return
    try:
        change = float(change)
    except (TypeError, ValueError):
        return
    if not math.isfinite(change):
        return
    diverging = (abs(score) >= DIV_SCORE_MIN and abs(change) >= DIV_CHANGE_MIN
                 and (score > 0) != (change > 0) and not SKIP_EVENTS)
    key = f"{today_str}|{name}|div"
    if diverging and not any(e["key"] == key for e in events):
        events.append({
            "key": key, "date": today_str, "instrument": name,
            "score": score, "price_change": change,
            "sentiment_up": score > 0,
            "headlines": [
                {"title": h.get("title", ""), "source": h.get("source", ""),
                 "link": h.get("link", ""), "score": h.get("score", 0)}
                for h in (headlines or [])[:5]
            ],
            "outcome": None, "next_change": None,
        })

    for e in events:
        if e.get("outcome") is not None or e["instrument"] != name:
            continue
        same_or_later = sorted(d for d in returns if d >= e["date"])
        if not same_or_later:
            continue
        nxt = returns[same_or_later[0]]
        e["next_change"] = nxt
        move_up = nxt >= 0
        e["outcome"] = "sentiment" if move_up == e["sentiment_up"] else "price"


def _rsi_series(closes, n=14):
    """Wilder RSI हर बार के लिए (पहले n बार None)।"""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _pivots(values, kind, k=3):
    """स्थानीय निम्न (kind='low') या उच्च (kind='high') बिंदु। आख़िरी k बार पर पुष्टि नहीं होती।"""
    idx = []
    for i in range(k, len(values) - k):
        win = values[i - k:i + k + 1]
        if kind == "low" and values[i] == min(win) and win.count(values[i]) == 1:
            idx.append(i)
        if kind == "high" and values[i] == max(win) and win.count(values[i]) == 1:
            idx.append(i)
    return idx


def rsi_divergence(closes, recent_bars=40, timeframe_label="दैनिक", source_label="Yahoo Finance"):
    """पुष्ट pivot पर bullish और bearish RSI divergence स्वतंत्र रूप से जाँचें."""
    if len(closes) < 60:
        return []
    rsi = _rsi_series(closes)
    if rsi[-1] is None:
        return []
    last = len(closes) - 1
    lows = [i for i in _pivots(closes, "low") if i >= last - recent_bars and rsi[i] is not None]
    highs = [i for i in _pivots(closes, "high") if i >= last - recent_bars and rsi[i] is not None]
    signals = []
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if closes[b] < closes[a] and rsi[b] > rsi[a]:
            signals.append({
                "label": "⚡ Bullish divergence",
                "reason": f"{timeframe_label} कीमत lower low, RSI higher low ({rsi[a]:.1f} → {rsi[b]:.1f}) · स्रोत: {source_label}"
            })
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if closes[b] > closes[a] and rsi[b] < rsi[a]:
            signals.append({
                "label": "⚡ Bearish divergence",
                "reason": f"{timeframe_label} कीमत higher high, RSI lower high ({rsi[a]:.1f} → {rsi[b]:.1f}) · स्रोत: {source_label}"
            })
    return signals


def derive_card_indicator(name, sym, score, change):
    """केवल पुष्ट तकनीकी संकेत लौटाएँ; कोई संकेत न हो तो UI में कुछ न दिखे."""
    if name == "SILVER":
        try:
            h = yf.Ticker(sym).history(period="5d", interval="30m")
            if h is None or len(h) < 4 or "Open Interest" not in h.columns:
                return {"indicator_label": "BUILDUP DATA UNAVAILABLE",
                        "indicator_reason": "एक ही कॉन्ट्रैक्ट का भरोसेमंद Open Interest डेटा उपलब्ध नहीं"}
            oi = h["Open Interest"].dropna()
            close = h["Close"].dropna()
            if len(oi) < 3 or len(close) < 3:
                return {"indicator_label": "BUILDUP DATA UNAVAILABLE",
                        "indicator_reason": "Open Interest/कीमत के पर्याप्त पूरे बार नहीं"}
            oi_delta = float(oi.iloc[-1] - oi.iloc[-2])
            price_delta = float(close.iloc[-1] / close.iloc[-2] - 1)
            if oi_delta > 0 and price_delta < 0:
                return {"indicator_label": "BEARISH BUILDUP",
                        "indicator_reason": "पूरे हुए 30-मिनट बार में कीमत नीचे और Open Interest ऊपर"}
            if oi_delta > 0 and price_delta > 0:
                return {"indicator_label": "BULLISH BUILDUP",
                        "indicator_reason": "पूरे हुए 30-मिनट बार में कीमत और Open Interest दोनों ऊपर"}
            return {"indicator_label": "NO CLEAR BUILDUP",
                    "indicator_reason": "कीमत और Open Interest से स्पष्ट नया buildup नहीं मिला"}
        except Exception as exc:
            return {"indicator_label": "BUILDUP DATA UNAVAILABLE",
                    "indicator_reason": str(exc)[:120]}

    if name == "BITCOIN":
        closes = []
        source = "Yahoo Finance"
        try:
            h = yf.Ticker(sym).history(period="5d", interval="30m")
            if h is not None and not h.empty and "Close" in h.columns:
                idx = h.index
                last_time = idx[-1].to_pydatetime()
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=dt.timezone.utc)
                if (dt.datetime.now(dt.timezone.utc) - last_time.astimezone(dt.timezone.utc)).total_seconds() < 30 * 60:
                    h = h.iloc[:-1]
                closes = [float(v) for v in h["Close"].dropna().tolist()]
        except Exception:
            closes = []
        if len(closes) < 60:
            try:
                url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=30m&limit=100"
                response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
                rows = response.json()
                now_ms = int(time.time() * 1000)
                closes = [float(row[4]) for row in rows if len(row) > 6 and int(row[6]) < now_ms]
                source = "Binance public spot candles"
            except Exception:
                return {}
        signals = rsi_divergence(closes, recent_bars=40, timeframe_label="30-मिनट", source_label=source)
        return {"indicator_signals": signals} if signals else {}

    # SENSEX RSI के लिए सत्यापित BSE ऐतिहासिक candles उपलब्ध नहीं हैं।
    # इसलिए Yahoo OHLC से SENSEX का कोई RSI संकेत नहीं बनाया जाएगा।
    if name == "SENSEX":
        return {}

    if name in ("NIFTY", "BANKNIFTY") or sym.endswith(".NS"):
        signals = []

        # 30-मिनट: केवल पूरी हो चुकी candles लें; चलती candle से संकेत न बनाएँ।
        try:
            h30 = yf.Ticker(sym).history(period="10d", interval="30m")
            if h30 is not None and not h30.empty and "Close" in h30.columns:
                now_ist = dt.datetime.now(dt.timezone.utc).astimezone(
                    dt.timezone(dt.timedelta(hours=5, minutes=30)))
                while not h30.empty:
                    last_time = h30.index[-1].to_pydatetime()
                    if last_time.tzinfo is None:
                        last_time = last_time.replace(tzinfo=now_ist.tzinfo)
                    else:
                        last_time = last_time.astimezone(now_ist.tzinfo)
                    if last_time + dt.timedelta(minutes=30) <= now_ist:
                        break
                    h30 = h30.iloc[:-1]
                closes30 = [float(v) for v in h30["Close"].dropna().tolist()]
                signals.extend(rsi_divergence(
                    closes30, recent_bars=40, timeframe_label="30-मिनट",
                    source_label="Yahoo Finance पूरी हुई candles"))
        except Exception as exc:
            print(f"30-minute RSI divergence skipped {name}: {exc}")

        # Daily: आज की अधूरी candle को 15:45 IST से पहले शामिल न करें।
        try:
            hd = yf.Ticker(sym).history(period="6mo", interval="1d")
            if hd is not None and not hd.empty and "Close" in hd.columns:
                now_ist = dt.datetime.now(dt.timezone.utc).astimezone(
                    dt.timezone(dt.timedelta(hours=5, minutes=30)))
                if now_ist.time() < dt.time(15, 45) and hd.index[-1].date() == now_ist.date():
                    hd = hd.iloc[:-1]
                closes_daily = [float(v) for v in hd["Close"].dropna().tolist()]
                signals.extend(rsi_divergence(
                    closes_daily, recent_bars=40, timeframe_label="दैनिक",
                    source_label="Yahoo Finance पूरी हुई candles"))
        except Exception as exc:
            print(f"Daily RSI divergence skipped {name}: {exc}")

        return {"indicator_signals": signals} if signals else {}
    return {}

def process(name, sym, query, kind, events, today_str, instruments, div_events, all_returns):
    returns = {}
    change = None if name == "SENSEX" else 0.0
    try:
        returns = daily_returns(sym)
        if returns:
            change = returns[max(returns)]
    except Exception as e:
        print(f"price error {name}: {e}")
    all_returns[name] = returns

    # NSE official quote is primary for Indian cash indices/stocks; Yahoo is backup.
    nse_quote = nse_cash_quote(name, sym)
    # SENSEX uses BSE's direct quote first; Google Finance's timestamped direct
    # quote is a fallback. Yahoo intraday is deliberately not a cash quote fallback.
    yahoo_quote = intraday_quote(sym) if name in ("USDINR", "BITCOIN") else None
    global_quote = google_finance_sensex_quote() if name == "SENSEX" and not nse_quote else None
    if not nse_quote and not yahoo_quote and name == "NASDAQ":
        global_quote = google_finance_quote(".IXIC", "INDEXNASDAQ", "NASDAQ")
    elif not nse_quote and not yahoo_quote and name == "DJI":
        global_quote = google_finance_quote(".DJI", "INDEXDJX", "DOW JONES")
    live_quote = nse_quote or yahoo_quote or global_quote
    if live_quote:
        quote_stamp = live_quote.get("stamp") or (
            str(live_quote.get("date", "")) + " " + str(live_quote.get("time", ""))
        )
        print(
            f"MARKET_QUOTE {name}: price={live_quote.get('price')} "
            f"change_pct={live_quote.get('change_pct')} "
            f"source={live_quote.get('source')} as_of={quote_stamp}"
        )
    else:
        print(f"MARKET_QUOTE {name}: unavailable; no validated intraday quote")
    if live_quote:
        PRICE_CACHE[sym] = live_quote["price"]
        if sym == "BTC-USD":
            PRICE_CACHE["BTC-USD_DATE"] = live_quote["date"] + " " + live_quote["time"]
            PRICE_CACHE["BTC-USD_SOURCE"] = live_quote["source"]
            # Never carry yesterday's BTC percentage into a fresh quote.
            # Publish a change only when this run verifies the matching previous close.
            PRICE_CACHE["BTC-USD_CHANGE_PCT"] = None
            verified_change = live_quote.get("change_pct")
            PRICE_CACHE["BTC-USD_CHANGE_PCT"] = (
                round(float(verified_change), 2)
                if verified_change is not None and math.isfinite(float(verified_change))
                else None
            )
        if nse_quote and nse_quote.get("change_pct") is not None:
            change = round(nse_quote["change_pct"], 2)
        elif global_quote:
            if name == "SENSEX":
                # Prefer the percentage supplied with this exact Google Finance quote.
                # If the provider omits it, derive the daily change only when the
                # quote date exactly matches Yahoo's completed daily candle date.
                # Never compare against a cached or mismatched previous close.
                pct = global_quote.get("change_pct")
                if pct is not None and math.isfinite(float(pct)):
                    change = round(float(pct), 2)
                else:
                    quote_date = global_quote.get("date")
                    if not quote_date and global_quote.get("stamp"):
                        try:
                            quote_date = dt.datetime.strptime(
                                str(global_quote["stamp"]), "%d-%b-%Y %H:%M:%S"
                            ).date().isoformat()
                        except ValueError:
                            quote_date = None
                    latest_return_date = max(returns) if returns else None
                    previous_close = PRICE_CACHE.get(sym + "_PREV_CLOSE")
                    previous_close_date = PRICE_CACHE.get(sym + "_PREV_CLOSE_DATE")
                    current_ist_date = (
                        dt.datetime.now(dt.timezone.utc)
                        + dt.timedelta(hours=5, minutes=30)
                    ).date().isoformat()
                    if latest_return_date and quote_date == latest_return_date:
                        # Quote is the last completed session close.
                        change = round(returns[latest_return_date], 2)
                    elif (
                        quote_date == current_ist_date
                        and previous_close_date == latest_return_date
                        and previous_close is not None
                        and previous_close > 0
                    ):
                        # Intraday quote vs the exact previous completed BSE session close.
                        change = round((live_quote["price"] / previous_close - 1) * 100, 2)
                    else:
                        change = None
            elif global_quote.get("change_pct") is not None:
                change = round(global_quote["change_pct"], 2)
            elif returns and global_quote.get("date") == max(returns):
                # Google Finance may publish the last US session close before
                # the next US session opens; use that completed candle's daily
                # return rather than comparing the close with itself.
                change = round(returns[max(returns)], 2)
            else:
                prev_close = PRICE_CACHE.get(sym + "_PREV_CLOSE")
                if prev_close and prev_close > 0:
                    change = round((live_quote["price"] / prev_close - 1) * 100, 2)
        elif name == "SENSEX":
            # प्रतिशत केवल उसी तारीख के सत्यापित quote/candle से लें।
            # आज का live quote अपना प्रतिशत न दे तो कल का Yahoo previous close
            # लगाकर आज का बदलाव कभी न निकालें।
            quote_date = live_quote.get("date")
            if not quote_date and live_quote.get("stamp"):
                try:
                    quote_date = dt.datetime.strptime(
                        str(live_quote["stamp"]), "%d-%b-%Y %H:%M:%S"
                    ).date().isoformat()
                except ValueError:
                    quote_date = None
            latest_return_date = max(returns) if returns else None
            change = (
                round(returns[latest_return_date], 2)
                if latest_return_date and quote_date == latest_return_date
                else None
            )
        else:
            prev_close = PRICE_CACHE.get(sym + "_PREV_CLOSE")
            if prev_close and prev_close > 0:
                change = round((live_quote["price"] / prev_close - 1) * 100, 2)
    elif sym == "BTC-USD":
        # Do not expose a previous hourly/daily cached BTC value as current.
        PRICE_CACHE[sym] = None
        PRICE_CACHE["BTC-USD_DATE"] = None
        PRICE_CACHE["BTC-USD_SOURCE"] = None
        PRICE_CACHE["BTC-USD_CHANGE_PCT"] = None
    elif sym == "INR=X":
        # USD/INR must have a fresh intraday quote; its separately dated daily
        # reference is attached later and is never promoted to a live price.
        PRICE_CACHE[sym] = None
        change = None
    elif sym.endswith(".NS") or sym in ("^NSEI", "^NSEBANK"):
        # Daily Yahoo candles remain available to historical indicators only.
        # Never publish Yahoo as the cash quote when the exchange/validated
        # direct quote path failed; leave the card explicitly unavailable.
        PRICE_CACHE[sym] = None
        change = None
    elif name == "SENSEX":
        # SENSEX must never fall back to yesterday's daily Yahoo/cache close.
        # Keep trying BSE + fresh Yahoo intraday above; if both fail, publish
        # no quote fields rather than a stale value or stale daily change.
        PRICE_CACHE[sym] = None
        change = None
    quote_date, quote_time = nse_stamp_fields(live_quote["stamp"]) if nse_quote else (
        (live_quote["date"], live_quote["time"]) if live_quote else (None, None))
    price_time = quote_time if live_quote else (
        PRICE_CACHE.get("GC=F_TIME") if sym == "GC=F" else
        PRICE_CACHE.get("SI=F_TIME") if sym == "SI=F" else
        PRICE_CACHE.get("BZ=F_TIME") if sym == "BZ=F" else
        compact_ist_time(PRICE_CACHE.get("BTC-USD_DATE")) if sym == "BTC-USD" else None
    )

    try:
        heads = fetch_news(query)
    except Exception as e:
        print(f"news error {name}: {e}")
        heads = []

    heads = dedupe_heads(heads)
    score = weighted_score(heads)

    instruments[name] = {
        "type": kind,
        "change_pct": PRICE_CACHE.get("SI=F_CHANGE_PCT") if sym == "SI=F" else PRICE_CACHE.get("GC=F_CHANGE_PCT") if sym == "GC=F" else PRICE_CACHE.get("BTC-USD_CHANGE_PCT") if sym == "BTC-USD" else PRICE_CACHE.get("BZ=F_CHANGE_PCT") if sym == "BZ=F" else change,
        "price": PRICE_CACHE.get(sym),
        "price_time": price_time,
        "price_as_of": quote_date if nse_quote else live_quote["date"] if live_quote else PRICE_CACHE.get("BZ=F_DATE") if sym == "BZ=F" else PRICE_CACHE.get("GC=F_DATE") if sym == "GC=F" else (PRICE_CACHE.get("SI=F_DATE") or max(returns)) if sym == "SI=F" and (PRICE_CACHE.get("SI=F_DATE") or returns) else PRICE_CACHE.get("BTC-USD_DATE") if sym == "BTC-USD" else (max(returns) if returns else None),
        "price_unit": ("₹/kg (Estimate)" if sym == "SI=F" else "₹/10g" if sym == "GC=F" else "₹/BBL" if sym == "BZ=F" else ""),
        "price_source": live_quote["source"] if live_quote else PRICE_CACHE.get("BZ=F_SOURCE") if sym == "BZ=F" else PRICE_CACHE.get("SI=F_SOURCE") if sym == "SI=F" else PRICE_CACHE.get("GC=F_SOURCE") if sym == "GC=F" else PRICE_CACHE.get("BTC-USD_SOURCE") if sym == "BTC-USD" else ("Yahoo Finance · LAST CLOSING PRICE" if PRICE_CACHE.get(sym) is not None and sym != "INR=X" else None),
        "news_query": query,
        "score": score,
        "headline_score": score,
        "headlines": heads[:8],
        "pos_n": sum(1 for h in heads if h["score"] > 0),
        "neg_n": sum(1 for h in heads if h["score"] < 0),
        **derive_card_indicator(name, sym, score, change),
    }
    update_contrarian(events, name, score, today_str, returns, sym)
    update_divergence(div_events, name, score, change, today_str, returns, heads)


# ---- संकेत-बदलाव लॉग ----

def intraday_snapshot(sym):
    """30-मिनट के बार से ताज़ा कीमत, आज का VWAP और वॉल्यूम का अनुपात।
    डेटा न मिले तो None लौटता है।"""
    try:
        h = yf.Ticker(sym).history(period="5d", interval="30m")
        if h is None or h.empty:
            return None

        # अधूरी चलती 30-मिनट कैंडल को संकेत में शामिल न करें।
        # Yahoo candle index आम तौर पर bar-start होता है; केवल वही bar लें
        # जिसका 30-मिनट समय पूरा हो चुका है।
        idx_utc = h.index
        if getattr(idx_utc, "tz", None) is None:
            idx_utc = idx_utc.tz_localize("UTC")
        else:
            idx_utc = idx_utc.tz_convert("UTC")
        now_utc = dt.datetime.now(dt.timezone.utc)
        completed = idx_utc + dt.timedelta(minutes=30) <= now_utc
        h = h.loc[completed]
        if h.empty:
            return None

        last = h.iloc[-1]
        price = float(last["Close"])
        vol_total = float(h["Volume"].sum())
        snap = {"price": price, "vwap": None, "vol_ratio": None, "vol_ok": vol_total > 0}
        if snap["vol_ok"]:
            today = h.index[-1].date()
            td = h[[d.date() == today for d in h.index]]
            tv = float(td["Volume"].sum())
            if tv > 0:
                tp = (td["High"] + td["Low"] + td["Close"]) / 3
                snap["vwap"] = float((tp * td["Volume"]).sum() / tv)
            avg = float(h["Volume"].mean())
            if avg > 0:
                snap["vol_ratio"] = float(last["Volume"]) / avg
        return snap
    except Exception as e:
        print(f"intraday error {sym}: {e}")
        return None


def _band(x, band):
    if x >= band:
        return 1
    if x <= -band:
        return -1
    return 0


def update_signals(instruments, state, log, now_iso):
    """हर देखे जाने वाले इंस्ट्रूमेंट का संकेत-स्नैपशॉट बनाता है।
    अगर भावना, कीमत-दिशा, VWAP-पक्ष या वॉल्यूम बदले, तो लॉग में दर्ज होता है।
    पिछले बदलाव के बाद की कीमत अगले रन पर भर जाती है।"""
    now = dt.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))

    for name, sym in SIGNAL_WATCH.items():
        d = instruments.get(name)
        if not d:
            continue
        snap = intraday_snapshot(sym)
        price_now = snap["price"] if snap else None

        # 1) पिछले बदलावों की बाद की कीमत भरें (नए इवेंट से पहले, ताकि नया इवेंट उसी रन में न भरे)
        if price_now is not None:
            for ev in log:
                if ev["instrument"] != name or ev.get("price_after") is not None:
                    continue
                if not ev.get("price_at_change"):
                    continue
                mv = (price_now / ev["price_at_change"] - 1) * 100
                ev["price_after"] = round(price_now, 4)
                ev["move_pct"] = round(mv, 2)
                ev["after_minutes"] = round(
                    (now - dt.datetime.fromisoformat(ev["time"].replace("Z", "+00:00"))).total_seconds() / 60)
                if mv >= SIG_MOVE_BAND:
                    ev["direction"] = "ऊपर"
                elif mv <= -SIG_MOVE_BAND:
                    ev["direction"] = "नीचे"
                else:
                    ev["direction"] = "लगभग स्थिर"

        vwap_side = None
        vol_hi = None
        if snap:
            if snap["vwap"] is not None:
                vwap_side = 1 if snap["price"] > snap["vwap"] else -1
            if snap["vol_ratio"] is not None:
                vol_hi = snap["vol_ratio"] >= SIG_VOL_HIGH

        cur = {
            "score": d["score"],
            "sent": _band(d["score"], SIG_SCORE_BAND),
            "price_dir": _band(d["change_pct"], SIG_PRICE_BAND),
            "vwap_side": vwap_side,
            "vol_hi": vol_hi,
            "vol_ok": bool(snap and snap["vol_ok"]),
            "price_now": price_now,
            "time": now_iso,
        }

        prev = state.get(name)
        if prev is None:
            cur["since"] = now_iso
            state[name] = cur
            continue

        changed = []
        if cur["sent"] != prev["sent"] or abs(cur["score"] - prev["score"]) >= SIG_SCORE_BAND:
            changed.append("भावना")
        if cur["price_dir"] != prev["price_dir"]:
            changed.append("कीमत")
        if cur["vwap_side"] is not None and prev.get("vwap_side") is not None \
                and cur["vwap_side"] != prev["vwap_side"]:
            changed.append("VWAP")
        if cur["vol_hi"] is not None and prev.get("vol_hi") is not None \
                and cur["vol_hi"] != prev["vol_hi"]:
            changed.append("वॉल्यूम")

        if changed:
            since = dt.datetime.fromisoformat(prev["since"].replace("Z", "+00:00"))
            log.append({
                "time": now_iso,
                "instrument": name,
                "prev_score": prev["score"],
                "new_score": cur["score"],
                "changed": changed,
                "vol_data": cur["vol_ok"],
                "held_minutes": round((now - since).total_seconds() / 60),
                "price_at_change": price_now,
                "price_after": None,
                "move_pct": None,
                "after_minutes": None,
                "direction": None,
            })
            if len(log) > SIG_LOG_KEEP:
                del log[:len(log) - SIG_LOG_KEEP]
            cur["since"] = now_iso
        else:
            cur["since"] = prev["since"]
        state[name] = cur


def signal_summary(state):
    out = {}
    for name, s in state.items():
        out[name] = {
            "score": s.get("score"),
            "sent": s.get("sent"),
            "price_dir": s.get("price_dir"),
            "vwap_side": s.get("vwap_side"),
            "vol_hi": s.get("vol_hi"),
            "vol_ok": s.get("vol_ok"),
            "since": s.get("since"),
        }
    return out


# ---- बाकी हिस्से ----

def is_market_news(title):
    """खबर बाज़ार से जुड़ी है या नहीं, यह पूरे शब्द या वाक्यांश मिलाकर तय होता है।"""
    t = title.lower()
    return any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in MARKET_IMPACT_WORDS)


def impact_label(score):
    if score >= 2:
        return "सकारात्मक असर"
    if score <= -2:
        return "नकारात्मक असर"
    return "तटस्थ"


def fetch_market_news():
    """बाज़ार पर असर डालने वाली ताज़ा खबरें, कई विषयों से।"""
    seen = set()
    items = []
    for topic, query in MARKET_NEWS_TOPICS:
        try:
            heads = fetch_news(query)
        except Exception as e:
            print(f"market news error {topic}: {e}")
            continue
        for h in heads[:8]:
            key = h["title"].lower()[:80]
            if key in seen or not is_market_news(h["title"]):
                continue
            seen.add(key)
            items.append({
                "topic": topic,
                "title": h["title"],
                "source": h["source"],
                "link": h["link"],
                "score": h["score"],
                "impact": impact_label(h["score"]),
                "age_h": h["age_h"],
            })
    if not items:
        return {"ok": False, "error": "बाज़ार से जुड़ी खबरें इस बार नहीं मिलीं"}
    items.sort(key=lambda x: (x["age_h"] is None, x["age_h"] or 0))
    return {"ok": True, "items": items[:12]}


def _num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def fetch_usdinr_reference(previous=None):
    """Daily USD/INR reference only; use two free Frankfurter routes, then a dated cache."""
    today = dt.datetime.now(dt.timezone.utc).date()
    headers = {"User-Agent": "PDMP-Scanner/1.0", "Accept": "application/json"}
    endpoints = (
        ("https://api.frankfurter.dev/v2/rate/USD/INR", "v2"),
        ("https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR", "v1"),
    )
    errors = []
    for url, version in endpoints:
        try:
            response = requests.get(url, headers=headers, timeout=12)
            response.raise_for_status()
            payload = response.json()
            if version == "v2":
                if str(payload.get("base", "")).upper() != "USD" or str(payload.get("quote", "")).upper() != "INR":
                    raise ValueError("Unexpected Frankfurter currency pair")
                raw_rate = payload.get("rate")
                raw_date = payload.get("date")
            else:
                if str(payload.get("base", "")).upper() != "USD":
                    raise ValueError("Unexpected Frankfurter base currency")
                raw_rate = (payload.get("rates") or {}).get("INR")
                raw_date = payload.get("date")
            rate = float(raw_rate)
            rate_date = dt.date.fromisoformat(str(raw_date))
            age_days = (today - rate_date).days
            if not math.isfinite(rate) or rate <= 0 or age_days < 0 or age_days > 4:
                raise ValueError("Frankfurter daily reference rate is invalid or too old")
            print(f"USDINR_REFERENCE: rate={rate:.4f} date={rate_date.isoformat()} source=Frankfurter daily reference (not live)")
            return {
                "reference_price": round(rate, 4),
                "reference_date": rate_date.isoformat(),
                "reference_source": "Frankfurter · दैनिक संदर्भ दर (लाइव नहीं)",
                "reference_stale": False,
            }
        except Exception as exc:
            errors.append(str(exc)[:120])

    # Keep the last verified daily reference visible over weekends/API outages.
    # It is date-checked and always labelled as a non-live cached reference.
    if isinstance(previous, dict):
        try:
            rate = float(previous.get("reference_price"))
            rate_date = dt.date.fromisoformat(str(previous.get("reference_date")))
            age_days = (today - rate_date).days
            if math.isfinite(rate) and rate > 0 and 0 <= age_days <= 4:
                return {
                    "reference_price": round(rate, 4),
                    "reference_date": rate_date.isoformat(),
                    "reference_source": "Frankfurter · सुरक्षित पिछली दैनिक संदर्भ दर (लाइव नहीं)",
                    "reference_stale": True,
                }
        except (TypeError, ValueError):
            pass
    print("USDINR daily reference unavailable: " + " | ".join(errors)[:200])
    return {
        "reference_price": None, "reference_date": None,
        "reference_source": None, "reference_stale": False,
    }


def summarise_fundamentals(info, price):
    """yfinance के info से कंपनी के आँकड़े। जो फ़ील्ड नहीं मिलता, वह None रहता है; कुछ भी बनाया नहीं जाता।
    'ग्राहक' और 'प्रमोटर/FII/DII' का पूरा विभाजन यहाँ नहीं मिलता, इसलिए वह नहीं भरा जाता।"""
    mcap = _num(info.get("marketCap"))
    target = _num(info.get("targetMeanPrice"))
    hi = _num(info.get("fiftyTwoWeekHigh"))
    lo = _num(info.get("fiftyTwoWeekLow"))
    out = {
        "market_cap_cr": round(mcap / 1e7, 0) if mcap else None,
        "pe_trailing": _num(info.get("trailingPE")),
        "pe_forward": _num(info.get("forwardPE")),
        "eps_trailing": _num(info.get("trailingEps")),
        "roe_pct": round(_num(info.get("returnOnEquity")) * 100, 1) if _num(info.get("returnOnEquity")) is not None else None,
        "operating_margin_pct": round(_num(info.get("operatingMargins")) * 100, 1) if _num(info.get("operatingMargins")) is not None else None,
        "revenue_growth_pct": round(_num(info.get("revenueGrowth")) * 100, 1) if _num(info.get("revenueGrowth")) is not None else None,
        "earnings_growth_pct": round(_num(info.get("earningsGrowth")) * 100, 1) if _num(info.get("earningsGrowth")) is not None else None,
        "insiders_pct": round(_num(info.get("heldPercentInsiders")) * 100, 1) if _num(info.get("heldPercentInsiders")) is not None else None,
        "institutions_pct": round(_num(info.get("heldPercentInstitutions")) * 100, 1) if _num(info.get("heldPercentInstitutions")) is not None else None,
        "analyst_target": round(target, 2) if target else None,
        "upside_to_target_pct": None,
        "w52_high": round(hi, 2) if hi else None,
        "w52_low": round(lo, 2) if lo else None,
        "position_in_52w_pct": None,
        "sector": info.get("sector") or "अज्ञात",
        "industry": info.get("industry") or "",
        "customers": None,
        "customers_note": "ग्राहक डेटा का भरोसेमंद मुफ़्त स्रोत अभी नहीं जुड़ा है",
    }
    if price and target:
        out["upside_to_target_pct"] = round((target / price - 1) * 100, 1)
    if price and hi and lo and hi > lo:
        out["position_in_52w_pct"] = round((price - lo) / (hi - lo) * 100, 1)
    return out


def fetch_stock_fundamentals(sym, price):
    try:
        info = yf.Ticker(sym).info or {}
        if price is None:
            price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
        return {"ok": True, **summarise_fundamentals(info, price)}
    except Exception as e:
        return {"ok": False, "error": f"कंपनी के आँकड़े नहीं मिले: {str(e)[:120]}"}



OPP_STOCKS = {
    "SUZLON": ("SUZLON.NS", "Suzlon Energy"),
    "DLINKINDIA": ("DLINKINDIA.NS", "D-Link (India)"),
    "VEDL": ("VEDL.NS", "Vedanta"),
    "APOLLOMICRO": ("APOLLO.NS", "Apollo Micro Systems"),
    "MSUMI": ("MSUMI.NS", "Motherson Sumi Wiring India"),
    "PARAS": ("PARAS.NS", "Paras Defence and Space Technologies"),
    "IOC": ("IOC.NS", "Indian Oil Corporation"),
    "GULPOLY": ("GULPOLY.NS", "Gulshan Polyols"),
    "GPPL": ("GPPL.NS", "Gujarat Pipavav Port"),
    "JAGRAN": ("JAGRAN.NS", "Jagran Prakashan"),
}
OPP_FACTORS = ["valuation", "growth", "profitability", "trend", "rsi", "analyst_upside"]


def _rsi14(closes):
    if len(closes) < 15:
        return None
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    ag = sum(gains[:14]) / 14
    al = sum(losses[:14]) / 14
    for i in range(14, len(gains)):
        ag = (ag * 13 + gains[i]) / 14
        al = (al * 13 + losses[i]) / 14
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def _sma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def opportunity_raw(sym):
    """एक स्टॉक के कच्चे आँकड़े (कोई खबर या भीड़ नहीं)। जो नहीं मिलता वह None।"""
    out = {"ok": False}
    try:
        t = yf.Ticker(sym)
        info = t.info or {}
        hist = t.history(period="1y", interval="1d")["Close"].dropna()
        closes = [float(x) for x in hist.tolist()]
        price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice")) or (closes[-1] if closes else None)
        pe = _num(info.get("trailingPE"))
        rg = _num(info.get("revenueGrowth"))
        eg = _num(info.get("earningsGrowth"))
        roe = _num(info.get("returnOnEquity"))
        om = _num(info.get("operatingMargins"))
        tgt = _num(info.get("targetMeanPrice"))
        s50, s200 = _sma(closes, 50), _sma(closes, 200)
        trend = None
        if price and s50 and s200:
            trend = (1 if price > s50 else 0) * 0.5 + (1 if price > s200 else 0) * 0.5
        growth_vals = [x for x in (rg, eg) if x is not None]
        prof_vals = [x for x in (roe, om) if x is not None]
        out.update({
            "ok": True,
            "price": round(price, 2) if price else None,
            "sector": info.get("sector") or "अज्ञात",
            "industry": info.get("industry") or "अज्ञात",
            "valuation": pe if (pe is not None and pe > 0) else None,
            "growth": (sum(growth_vals) / len(growth_vals)) if growth_vals else None,
            "growth_factor": (sum(growth_vals) / len(growth_vals)) if growth_vals else None,
            "profitability": (sum(prof_vals) / len(prof_vals)) if prof_vals else None,
            "trend": trend,
            "rsi": _rsi14(closes),
            "analyst_upside": ((tgt / price - 1) * 100) if (tgt and price) else None,
            "_holding": {
                "insiders_pct": round(_num(info.get("heldPercentInsiders")) * 100, 1) if _num(info.get("heldPercentInsiders")) is not None else None,
                "institutions_pct": round(_num(info.get("heldPercentInstitutions")) * 100, 1) if _num(info.get("heldPercentInstitutions")) is not None else None,
            },
        })
    except Exception as e:
        out["error"] = f"आँकड़े नहीं मिले: {str(e)[:120]}"
    return out


def _cr(v):
    """रुपये -> करोड़ (2 दशमलव)। नहीं मिला तो None।"""
    try:
        x = float(v)
        return round(x / 1e7, 2) if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _series_val(df, row_names):
    if df is None or getattr(df, "empty", True):
        return None
    for rn in row_names:
        if rn in df.index:
            return df.loc[rn]
    return None


def opportunity_extra(sym, market_1y, info_holding):
    """केवल वे आँकड़े जो सच में मिलें; बाकी कुछ नहीं जोड़ा जाता।"""
    out = {}
    try:
        t = yf.Ticker(sym)
        hist = t.history(period="1y", interval="1d")["Close"].dropna()
        if len(hist) >= 200 and float(hist.iloc[0]) > 0:
            out["return_1y_pct"] = round((float(hist.iloc[-1]) / float(hist.iloc[0]) - 1) * 100, 2)
        if market_1y is not None:
            out["market_1y_pct"] = market_1y

        q = None
        for attr in ("quarterly_financials", "quarterly_income_stmt"):
            try:
                q = getattr(t, attr)
                if q is not None and not q.empty:
                    break
            except Exception:
                q = None
        rev_q = _series_val(q, ["Total Revenue"])
        prf_q = _series_val(q, ["Net Income", "Net Income Common Stockholders"])
        quarters = []
        if q is not None and not q.empty:
            for c in list(q.columns)[:5]:
                r = _cr(rev_q[c]) if rev_q is not None else None
                pr = _cr(prf_q[c]) if prf_q is not None else None
                if r is None and pr is None:
                    continue
                quarters.append({"period": c.strftime("%b '%y"), "revenue_cr": r, "profit_cr": pr})
            quarters.reverse()
        if quarters:
            out["quarterly"] = quarters

        a = None
        for attr in ("financials", "income_stmt"):
            try:
                a = getattr(t, attr)
                if a is not None and not a.empty:
                    break
            except Exception:
                a = None
        rev_a = _series_val(a, ["Total Revenue"])
        prf_a = _series_val(a, ["Net Income", "Net Income Common Stockholders"])
        growth = {}
        def _vals(series):
            if series is None:
                return []
            return [float(series[c]) for c in series.index if series[c] == series[c]]
        rv, pv = _vals(rev_a), _vals(prf_a)
        if len(rv) >= 2 and rv[1] > 0:
            growth["revenue_1y_pct"] = round((rv[0] / rv[1] - 1) * 100, 1)
        if len(pv) >= 2 and pv[1] > 0:
            growth["profit_1y_pct"] = round((pv[0] / pv[1] - 1) * 100, 1)
        if len(rv) >= 4 and rv[0] > 0 and rv[3] > 0:
            growth["revenue_3y_cagr_pct"] = round(((rv[0] / rv[3]) ** (1 / 3) - 1) * 100, 1)
        if len(pv) >= 4 and pv[0] > 0 and pv[3] > 0:
            growth["profit_3y_cagr_pct"] = round(((pv[0] / pv[3]) ** (1 / 3) - 1) * 100, 1)
        if growth:
            out["growth"] = growth
    except Exception:
        pass

    holding = {k: v for k, v in info_holding.items() if v is not None}
    if holding:
        out["holding"] = holding
    return out


def _pct_rank(value, values, higher_is_better=True):
    """बाकी स्टॉक के मुकाबले 0–100 का स्थान। बराबर मान पर आधा अंक।"""
    if value is None or not values:
        return None
    if len(values) == 1:
        return 50.0
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    rank = (below + 0.5 * equal) / len(values) * 100
    return round(rank if higher_is_better else 100 - rank, 1)


def score_opportunities(raws):
    """हर वैक्टर का 0–100 स्कोर सूची के भीतर तुलना से। उपलब्ध वैक्टर का औसत = कुल स्कोर।
    RSI: कम RSI (ज़्यादा बिका हुआ) को ज़्यादा अंक; ज़्यादा RSI को कम अंक।"""
    spec = {
        "valuation": False,   # P/E कम हो तो बेहतर
        "growth": True,
        "profitability": True,
        "trend": True,
        "rsi": False,         # RSI कम हो तो बेहतर (ज़्यादा बिका)
        "analyst_upside": True,
    }
    ok = {k: v for k, v in raws.items() if v.get("ok")}
    for name, r in ok.items():
        scores = {}
        for f in OPP_FACTORS:
            source_key = "growth_factor" if f == "growth" else f
            vals = [x[source_key] for x in ok.values()
                    if isinstance(x.get(source_key), (int, float)) and math.isfinite(x[source_key])]
            scores[f] = _pct_rank(r.get(source_key), vals, spec[f])
        avail = [s for s in scores.values() if s is not None]
        r["scores"] = scores
        r["total"] = round(sum(avail) / len(avail), 1) if avail else None
        r["missing"] = [f for f in OPP_FACTORS if scores[f] is None]
    return raws


def nifty_range():
    """India VIX से अगले सत्र का 68% संभावना वाला दायरा।
    सूत्र: दैनिक σ = VIX/100 ÷ √252, फिर अंतिम बंद × σ।"""
    try:
        vix_s = yf.Ticker("^INDIAVIX").history(period="5d")["Close"].dropna()
        nifty_s = yf.Ticker("^NSEI").history(period="5d")["Close"].dropna()
        if vix_s.empty or nifty_s.empty:
            raise ValueError("VIX या निफ़्टी का डेटा खाली है")
        vix = float(vix_s.iloc[-1])
        last = float(nifty_s.iloc[-1])
        pct = vix / 100 / math.sqrt(252)
        pts = last * pct
        return {"ok": True, "vix": round(vix, 2), "last_close": round(last, 2),
                "move_pts": round(pts, 1), "move_pct": round(pct * 100, 2),
                "low": round(last - pts, 1), "high": round(last + pts, 1)}
    except Exception as e:
        return {"ok": False, "error": f"रेंज नहीं निकली: {e}"}


def build_levels(range_info):
    """Nifty के वॉच-स्तर और अंतिम बंद से उनकी दूरी (%)।"""
    if not range_info or not range_info.get("ok"):
        return []
    last = range_info["last_close"]
    out = []
    for lvl in NIFTY_WATCH_LEVELS:
        out.append({"level": lvl, "dist_pct": round((lvl / last - 1) * 100, 2)})
    return out


def fetch_fii_dii():
    """NSE से FII/DII नेट फ़्लो। NSE अक्सर क्लाउड सर्वर को ब्लॉक करता है,
    इसलिए फ़ेल होने पर {"ok": False} लौटता है।"""
    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/",
        })
        s.get("https://www.nseindia.com", timeout=15)
        r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
        r.raise_for_status()
        rows = r.json()

        fii = dii = None
        date = None
        for row in rows:
            cat = str(row.get("category", "")).upper()
            net_raw = str(row.get("netValue", "0")).replace(",", "").strip()
            net = float(net_raw) if net_raw not in ("", "-") else 0.0
            date = row.get("date") or date
            if "FII" in cat or "FPI" in cat:
                fii = net
            elif "DII" in cat:
                dii = net

        if fii is None or dii is None:
            raise ValueError("FII या DII की संख्या नहीं मिली")
        return {"ok": True, "as_of": date, "fii": fii, "dii": dii}
    except Exception as e:
        return {"ok": False, "error": f"FII/DII नहीं मिला: {e}"}


def match_relevant(query):
    """उभरती खोज को तभी स्वीकार करता है जब वह Nifty/Sensex से जुड़ी हो
    या हमारी वॉचलिस्ट के किसी स्टॉक से।"""
    q = query.lower()
    for stock, aliases in STOCK_ALIASES.items():
        if any(a in q for a in aliases):
            return True, stock
    if "nifty" in q or "sensex" in q or "निफ़्टी" in q or "सेंसेक्स" in q:
        return True, None
    return False, None


def crowd_decision(bull_pct_sum, bear_pct_sum):
    """भीड़ की सोच: EXTREMELY BULLISH / EXTREMELY BEARISH / NEUTRAL।
    Google Trends सापेक्ष खोज रुचि है, वास्तविक search count नहीं।"""
    if bull_pct_sum < MIN_SIDE_PCT or bear_pct_sum < MIN_SIDE_PCT:
        return None, "डेटा अपर्याप्त — NO TRADE"
    total = bull_pct_sum + bear_pct_sum
    pct = round(bull_pct_sum / total * 100)
    if pct >= CROWD_EXTREME:
        return pct, "EXTREMELY BULLISH"
    if pct <= CROWD_LOW:
        return pct, "EXTREMELY BEARISH"
    return pct, "NEUTRAL"


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _trends_observation_time(df, label="Google Trends"):
    """हर payload का आख़िरी वास्तविक observation UTC में लौटाएँ; scan time इसका विकल्प नहीं।"""
    if df is None or df.empty:
        raise ValueError(f"{label}: hourly observation खाली है")
    last_value = df.index[-1]
    last_dt = last_value.to_pydatetime() if hasattr(last_value, "to_pydatetime") else last_value
    if last_dt.tzinfo is None:
        # pytrends pandas index naive UTC होता है।
        last_dt = last_dt.replace(tzinfo=dt.timezone.utc)
    last_utc = last_dt.astimezone(dt.timezone.utc)
    age_minutes = (dt.datetime.now(dt.timezone.utc) - last_utc).total_seconds() / 60
    if age_minutes < -10 or age_minutes > TRENDS_MAX_AGE_MINUTES:
        raise ValueError(
            f"{label}: आख़िरी वास्तविक observation {age_minutes:.0f} मिनट पुराना/भविष्य का है; "
            f"सीमा {TRENDS_MAX_AGE_MINUTES} मिनट"
        )
    return last_utc

def _trends_snapshot_timestamp(observed, label="Google Trends"):
    """Return a truthful snapshot clock: source observation when present, retrieval clock otherwise."""
    try:
        stamp = _trends_observation_time(observed, label)
        return stamp.isoformat(), "source_observation"
    except Exception as exc:
        # related_queries is a separate endpoint. If it succeeded but hourly
        # interest data is empty/unavailable, retain its freshly retrieved
        # snapshot without pretending retrieval time is source observation.
        retrieved = dt.datetime.now(dt.timezone.utc)
        print(f"{label}: source observation timestamp unavailable; using retrieval timestamp: {str(exc)[:160]}")
        return retrieved.isoformat(), "retrieval_time"


def _trends_request(py, terms, timeframe="now 7-d"):
    """एक Google Trends अनुरोध: ANCHOR + ज़्यादा से ज़्यादा 4 शब्द।"""
    py.build_payload([ANCHOR] + terms, timeframe=timeframe, geo="IN")
    df = py.interest_over_time()
    if df is None or df.empty:
        raise ValueError("Google से खाली डेटा मिला")
    return df[[ANCHOR] + terms].fillna(0)


def _ratio(df, term, recent_points=24):
    """शब्द की खोज nifty के अनुपात में हाल की अवधि और पूरे समय के औसत के रूप में।"""
    a_recent = float(df[ANCHOR].tail(recent_points).mean())
    a_avg = float(df[ANCHOR].mean())
    if a_recent <= 0 or a_avg <= 0:
        return 0.0, 0.0
    t_recent = float(df[term].tail(recent_points).mean())
    t_avg = float(df[term].mean())
    return t_recent / a_recent, t_avg / a_avg


def _period_ratio(df, term, day_str):
    """IST कैलेंडर दिन में शब्द की औसत रुचि / anchor की औसत रुचि (%); raw search count नहीं।"""
    idx = df.index
    try:
        if getattr(idx, "tz", None) is None:
            idx = idx.tz_localize("Asia/Kolkata")
        else:
            idx = idx.tz_convert("Asia/Kolkata")
        mask = idx.strftime("%Y-%m-%d") == day_str
        part = df.loc[mask]
        if part.empty:
            return None
        anchor_mean = float(part[ANCHOR].mean())
        if anchor_mean <= 0:
            return None
        return round(float(part[term].mean()) / anchor_mean * 100, 2)
    except Exception as e:
        print(f"daily Trends ratio error for {term}: {e}")
        return None


TQ_BASE_TERMS = ["nifty", "sensex"]
TQ_BULL_WORDS = ["target", "rally", "rise", "up", "high", "record", "buy", "bull", "bullish",
                 "jump", "surge", "gain", "breakout", "recovery", "recover", "bounce", "uptrend",
                 "teji", "tez", "badhega", "badhegi", "upar", "chadhega", "chadhav",
                 "टारगेट", "रैली", "तेज़ी", "तेजी", "उछाल", "ऊपर", "बुलिश", "खरीद", "बढ़ेगा", "बढ़ेगी", "रिकवरी", "ब्रेकआउट"]
TQ_BEAR_WORDS = ["fall", "crash", "down", "drop", "low", "sell", "bear", "bearish", "slump",
                 "decline", "sell-off", "selloff", "correction", "correct", "downtrend", "weakness",
                 "girawat", "girega", "giregi", "neeche", "mandi", "tutega", "girawat",
                 "गिरावट", "गिरेगा", "गिरेगी", "नीचे", "मंदी", "बेयरिश", "बिकवाली", "टूटेगा", "करेक्शन"]
# केवल वास्तविक flat/sideways queries neutral mood हैं।
TQ_NEUTRAL_WORDS = ["sideways", "sideway", "flat", "stable", "stability", "rangebound",
                    "range-bound", "consolidation", "consolidating", "unchanged", "steady",
                    "सपाट", "स्थिर", "बिना बदलाव", "सीमित दायरा", "दायरे में", "एक ही स्तर"]
# Navigation/information intent is tracked separately and never counted as neutral mood.
TQ_INFORMATION_WORDS = ["today", "live", "price", "news", "chart", "index", "market", "stock",
                        "share", "sensex", "nifty", "bank", "option", "chain", "prediction", "expiry",
                        "what", "meaning", "history", "hours", "volume", "oi", "fii", "dii",
                        "आज", "भाव", "समाचार", "चार्ट", "शेयर", "बाजार", "बाज़ार", "निफ्टी", "सेंसेक्स",
                        "बैंक", "ऑप्शन", "चेन", "भविष्यवाणी"]
TQ_MIN_WEIGHT = 0.01  # कोई भी वास्तविक non-zero reading स्वीकार; शून्य/अनुपलब्ध डेटा अस्वीकार


def tq_dir(q):
    """खोज-वाक्यांश की दिशा; जानकारी/नेविगेशन को neutral mood न मानें।"""
    text = str(q or "").lower()
    tk = set(re.findall(r"[\w\u0900-\u097F-]+", text))
    bull = any(w.lower() in tk for w in TQ_BULL_WORDS)
    bear = any(w.lower() in tk for w in TQ_BEAR_WORDS)
    if bull and not bear:
        return "bull"
    if bear and not bull:
        return "bear"
    if not bull and not bear and any(w.lower() in tk for w in TQ_NEUTRAL_WORDS):
        return "neutral"
    if not bull and not bear and any(w.lower() in tk for w in TQ_INFORMATION_WORDS):
        return "informational"
    return None


def tq_weight(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 100.0  # 'Breakout' जैसे मान


def three_way_crowd_mood(bull_pct, bear_pct, neutral_pct):
    """Classify directional crowd bias; neutral information searches remain separately visible."""
    values = (bull_pct, bear_pct, neutral_pct)
    try:
        bull, bear, neutral = (float(value) for value in values)
    except (TypeError, ValueError):
        return "NO DATA", "पर्याप्त खोज डेटा नहीं"
    if (not all(math.isfinite(value) and 0 <= value <= 100 for value in (bull, bear, neutral))
            or abs(bull + bear + neutral - 100) > 2):
        return "NO DATA", "पर्याप्त खोज डेटा नहीं"
    directional_total = bull + bear
    if directional_total < 1.0:
        return "NEUTRAL", "दिशात्मक खोज रुचि 1% से कम; मूड तय करने के लिए अपर्याप्त"
    directional_bull_pct = bull / directional_total * 100.0
    if directional_bull_pct >= CROWD_EXTREME:
        return "BULLISH", "दिशात्मक खोजों में बेहद बुलिश झुकाव"
    if directional_bull_pct <= CROWD_LOW:
        return "BEARISH", "दिशात्मक खोजों में बेहद बियरिश झुकाव"
    if directional_bull_pct > 50:
        return "BULLISH", "दिशात्मक खोजों में बुलिश झुकाव"
    if directional_bull_pct < 50:
        return "BEARISH", "दिशात्मक खोजों में बियरिश झुकाव"
    return "NEUTRAL", "बुलिश और बियरिश खोजें बराबर"


def three_way_crowd_component(bull_pct, bear_pct, neutral_pct):
    """Map the bull-vs-bear directional ratio to -10..+10; neutral searches stay contextual."""
    mood, _label = three_way_crowd_mood(bull_pct, bear_pct, neutral_pct)
    if mood == "NO DATA":
        return None
    bull, bear = float(bull_pct), float(bear_pct)
    directional_total = bull + bear
    if directional_total < 1.0:
        return None
    return round(max(-10.0, min(10.0, (bull - bear) / directional_total * 10.0)), 1)


def tq_aggregate(queries):
    """असली खोजें (related queries) -> भीड़ का मूड, स्कोर और सूचियाँ।"""
    bull_w = bear_w = neutral_w = informational_w = 0.0
    crowd_terms, spikes, informational_terms = [], [], []
    for item in queries.values():
        d = tq_dir(item["term"])
        if d == "bull":
            bull_w += item["weight"]
        elif d == "bear":
            bear_w += item["weight"]
        elif d == "neutral":
            neutral_w += item["weight"]
        elif d == "informational":
            informational_w += item["weight"]
            informational_terms.append({"term": item["term"], "weight": round(item["weight"], 1)})
        if d:
            crowd_terms.append({"term": item["term"], "dir": d, "now": round(item["weight"], 1),
                                "avg": round(item["weight"], 1), "today_pct": None, "yesterday_pct": None})
        if item.get("rising"):
            ok, stock = match_relevant(item["term"])
            if ok:
                spikes.append({"query": item["term"], "value": str(round(item["weight"])), "stock": stock})
    crowd_terms.sort(key=lambda r: r["now"], reverse=True)
    if bull_w < TQ_MIN_WEIGHT or bear_w < TQ_MIN_WEIGHT:
        pct, label = None, "पर्याप्त खोज डेटा नहीं"
        bull_score = bear_score = neutral_score = None
        sentiment = "NO DATA"
    else:
        total = bull_w + bear_w
        pct = round(bull_w / total * 100)
        if pct >= CROWD_EXTREME:
            label = "ज़्यादातर बुलिश सोच"
        elif pct <= CROWD_LOW:
            label = "ज़्यादातर बियरिश सोच"
        else:
            label = "सोच बँटी हुई"
        # Three-way mood percentages use the actual weight of each query group.
        # crowd_bull_pct remains a separate bull-vs-bear ratio for the Fear-vs-Greed display only.
        mood_total = bull_w + bear_w + neutral_w
        bull_score = round(bull_w / mood_total * 100, 1) if mood_total else None
        bear_score = round(bear_w / mood_total * 100, 1) if mood_total else None
        neutral_score = round(neutral_w / mood_total * 100, 1) if mood_total else None
        sentiment, label = three_way_crowd_mood(bull_score, bear_score, neutral_score)
    rising_all = [it for it in queries.values() if it.get("rising")]
    return {
        "crowd_bull_pct": pct, "crowd_label": label,
        "bull_sum_pct": round(bull_w, 1), "bear_sum_pct": round(bear_w, 1),
        "min_side_pct": TQ_MIN_WEIGHT,
        "crowd_terms": crowd_terms,
        "spikes": spikes[:10],
        "hidden_spikes": max(0, len(rising_all) - len(spikes)),
        "bull_score_pct": bull_score, "bear_score_pct": bear_score,
        "neutral_score_pct": neutral_score, "sentiment_label": sentiment,
        "informational_weight": round(informational_w, 1),
        "informational_queries": len(informational_terms),
        "informational_terms": informational_terms,
        "today_bull_pct": None, "today_label": "डेटा उपलब्ध नहीं", "today_basis": "related_queries_7d",
        "yesterday_bull_pct": None, "yesterday_label": "कल का डेटा उपलब्ध नहीं",
        "queries_total": len(queries),
    }


def _trends_once(timeframe="now 7-d", recent_points=24):
    """Google Trends: anchor के साथ संतुलित bull/bear शब्दों की सापेक्ष रुचि।
    7-दिन डेटा अपर्याप्त हो तो caller 3-महीने के दैनिक डेटा पर fallback करता है।"""
    from pytrends.request import TrendReq

    py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
    py.build_payload(TQ_BASE_TERMS, timeframe=timeframe, geo="IN")
    base_df = py.interest_over_time()
    if base_df is None or base_df.empty:
        raise ValueError("Google Trends से खाली आधार डेटा मिला")
    base_df = base_df[TQ_BASE_TERMS].fillna(0)
    if float(base_df.values.max()) <= 0:
        raise ValueError("Google Trends का आधार डेटा शून्य है")
    # दोनों timeframe में Google का आख़िरी वास्तविक observation 30 मिनट के भीतर होना चाहिए।
    last_utc = _trends_observation_time(base_df, "Google Trends base")
    source_data_time = last_utc.isoformat()
    # _trends_observation_time validated this exact source observation; keep
    # its provenance explicit so downstream freshness checks do not fail.
    timestamp_basis = "source_observation"
    base = float(base_df.mean(axis=1).mean())
    recent = float(base_df.tail(recent_points).mean(axis=1).mean())
    attention = round(recent - base, 1)

    queries = {}
    for direction, terms in (("bull", BULL_TERMS), ("bear", BEAR_TERMS), ("neutral", NEUTRAL_TERMS)):
        for chunk in _chunks(terms, TERM_CHUNK):
            df = _trends_request(py, chunk, timeframe=timeframe)
            chunk_time = _trends_observation_time(df, f"Google Trends {direction} keywords")
            if abs((chunk_time - last_utc).total_seconds()) > TRENDS_MAX_AGE_MINUTES * 60:
                raise ValueError(
                    f"Google Trends {direction} keywords का observation base data से "
                    "6 घंटे से अधिक अलग है"
                )
            for term in chunk:
                recent_ratio, average_ratio = _ratio(df, term, recent_points=recent_points)
                queries[term.lower()] = {
                    "term": term, "weight": round(max(0.0, recent_ratio) * 100, 2),
                    "avg_weight": round(max(0.0, average_ratio) * 100, 2),
                    "rising": False, "direction": direction
                }

    # Classify each phrase by its actual intent, not merely by the request batch.
    for item in queries.values():
        item["direction"] = tq_dir(item["term"])
    bull_total = sum(x["weight"] for x in queries.values() if x["direction"] == "bull")
    bear_total = sum(x["weight"] for x in queries.values() if x["direction"] == "bear")
    neutral_total = sum(x["weight"] for x in queries.values() if x["direction"] == "neutral")
    informational_items = [x for x in queries.values() if x["direction"] == "informational"]
    informational_total = sum(x["weight"] for x in informational_items)
    total = bull_total + bear_total + neutral_total
    if total <= 0:
        raise ValueError("Google Trends के directional/explicit-neutral समूहों का कुल डेटा शून्य है")
    directional_complete = (
        bull_total >= TQ_MIN_WEIGHT and bear_total >= TQ_MIN_WEIGHT
    )
    if not directional_complete and neutral_total < TQ_MIN_WEIGHT:
        raise ValueError(
            f"Google Trends में पर्याप्त वर्गीकृत खोज-रुचि नहीं "
            f"(bull={bull_total:.3f}, bear={bear_total:.3f}, "
            f"neutral={neutral_total:.3f}, minimum={TQ_MIN_WEIGHT})"
        )
    bull_pct = bull_total / total * 100
    bear_pct = bear_total / total * 100
    neutral_pct = neutral_total / total * 100
    bull_score = round(bull_pct, 1)
    bear_score = round(bear_pct, 1)
    neutral_score = round(neutral_pct, 1)
    crowd_direction_pct = (
        bull_total / (bull_total + bear_total) * 100
        if directional_complete else 50.0
    )
    if directional_complete:
        sentiment, label = three_way_crowd_mood(bull_score, bear_score, neutral_score)
    else:
        label, sentiment = "दिशात्मक खोज स्पष्ट नहीं — तटस्थ", "NEUTRAL"

    crowd_terms = [{
        "term": x["term"], "dir": x["direction"], "now": x["weight"],
        "avg": x["avg_weight"], "today_pct": None, "yesterday_pct": None
    } for x in queries.values()]
    crowd_terms.sort(key=lambda x: x["now"], reverse=True)
    print(f"Google Trends validated ({timeframe}): bull={bull_total:.2f}, bear={bear_total:.2f}, crowd_bull={crowd_direction_pct:.1f}%")
    return {
        "ok": True, "unit": "anchor-relative points", "fear_vs_avg": attention,
        "crowd_bull_pct": round(crowd_direction_pct, 1), "crowd_label": label,
        "bull_sum_pct": round(bull_total, 2), "bear_sum_pct": round(bear_total, 2),
        "min_side_pct": TQ_MIN_WEIGHT, "crowd_terms": crowd_terms,
        "spikes": [], "hidden_spikes": 0,
        "bull_score_pct": bull_score, "bear_score_pct": bear_score,
        "neutral_score_pct": neutral_score, "sentiment_label": sentiment,
        "informational_weight": round(informational_total, 2),
        "informational_queries": len(informational_items),
        "informational_terms": [x["term"] for x in informational_items],
        "today_bull_pct": round(crowd_direction_pct, 1) if timeframe == "now 1-d" else None,
        "today_label": "पिछले 24 घंटे में तेजी बनाम मंदी खोज-रुचि" if timeframe == "now 1-d" else "डेटा उपलब्ध नहीं",
        "today_basis": "now_1d_anchor_relative" if timeframe == "now 1-d" else timeframe + "_anchor_relative",
        "source_timeframe": timeframe,
        "source_data_time": source_data_time if timestamp_basis == "source_observation" else None,
            "retrieved_at": source_data_time if timestamp_basis == "retrieval_time" else None,
            "timestamp_basis": timestamp_basis,
        "yesterday_label": "कल का डेटा उपलब्ध नहीं",
        "queries_total": len(queries)
    }


def _trends_related_queries(timeframe="now 1-d"):
    """Google Trends की असली related searches से भीड़ का मूड निकालें।
    हर seed की अपनी 0-100 scale होती है, इसलिए पहले हर seed के भीतर प्रतिशत
    निकालकर फिर seed percentages का औसत लिया जाता है; अलग scales को सीधे नहीं जोड़ते।
    """
    from pytrends.request import TrendReq

    # पाँच व्यापक भारतीय बाजार seed: Nifty, Sensex, Bank Nifty, Share Market, Stock Market.
    # एक ही payload/related-query pass; प्रत्येक seed से मिले वास्तविक queries को
    # तेजी/मंदी/सामान्य में वर्गीकृत किया जाता है। कोई काल्पनिक प्रतिशत नहीं।
    seeds = ["nifty", "sensex", "bank nifty", "share market", "stock market"]
    py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
    py.build_payload(seeds, timeframe=timeframe, geo="IN")
    related = py.related_queries()

    # related_queries() में अपना observation timestamp नहीं आता।
    # उसी Google Trends payload का interest_over_time() लेकर आख़िरी वास्तविक
    # observation का समय सत्यापित करें; workflow का scan time इसका विकल्प नहीं है।
    observed = py.interest_over_time()
    if observed is None or observed.empty:
        raise ValueError("Google Trends का timestamp सत्यापित करने के लिए hourly data खाली है")
    last_value = observed.index[-1]
    last_dt = last_value.to_pydatetime() if hasattr(last_value, "to_pydatetime") else last_value
    if last_dt.tzinfo is None:
        # pytrends index naive UTC होता है।
        last_dt = last_dt.replace(tzinfo=dt.timezone.utc)
    last_utc = last_dt.astimezone(dt.timezone.utc)
    age_minutes = (dt.datetime.now(dt.timezone.utc) - last_utc).total_seconds() / 60
    if age_minutes < -10 or age_minutes > TRENDS_MAX_AGE_MINUTES:
        raise ValueError(
            f"Google Trends का आख़िरी वास्तविक observation {age_minutes:.0f} मिनट पुराना/भविष्य का है"
        )
    source_data_time = last_utc.isoformat()

    per_seed = []
    all_terms = {}

    for seed in seeds:
        pack = (related or {}).get(seed) or {}
        top = pack.get("top")
        if top is None or top.empty or "query" not in top or "value" not in top:
            continue

        bull = bear = neutral = informational = 0.0
        rows = 0
        for _, row in top.iterrows():
            term = str(row.get("query", "")).strip()
            if not term:
                continue
            try:
                weight = float(row.get("value", 0) or 0)
            except (TypeError, ValueError):
                continue
            if weight <= 0:
                continue
            direction = tq_dir(term)
            if direction is None:
                continue
            key = term.casefold()
            entry = {"term": term, "weight": weight, "direction": direction}
            if key not in all_terms or weight > all_terms[key]["weight"]:
                all_terms[key] = entry
            if direction == "informational":
                informational += weight
                continue
            rows += 1
            if direction == "bull":
                bull += weight
            elif direction == "bear":
                bear += weight
            elif direction == "neutral":
                neutral += weight

        total = bull + bear + neutral
        if rows >= 3 and total > 0:
            per_seed.append((bull / total * 100, bear / total * 100, neutral / total * 100))
    if len(per_seed) < 3:
        raise ValueError(
            f"Google Trends related searches में 5 में से कम-से-कम 3 बाजार विषयों का "
            f"वर्गीकृत डेटा चाहिए; उपलब्ध विषय={len(per_seed)}"
        )

    bull_pct = round(sum(x[0] for x in per_seed) / len(per_seed), 1)
    bear_pct = round(sum(x[1] for x in per_seed) / len(per_seed), 1)
    neutral_pct = round(sum(x[2] for x in per_seed) / len(per_seed), 1)
    directional_complete = (
        bull_pct >= TQ_MIN_WEIGHT and bear_pct >= TQ_MIN_WEIGHT
    )
    if not directional_complete and neutral_pct < TQ_MIN_WEIGHT:
        raise ValueError(
            f"Google Trends में पर्याप्त वर्गीकृत खोज नहीं "
            f"(bull={bull_pct:.1f}%, bear={bear_pct:.1f}%, "
            f"neutral={neutral_pct:.1f}%, minimum={TQ_MIN_WEIGHT}%)"
        )
    # Keep the two-way ratio only for Fear-vs-Greed; mood classification uses all three groups.
    directional_total = bull_pct + bear_pct
    crowd_bull_pct = round(bull_pct / directional_total * 100) if directional_total > 0 else 50
    if directional_complete:
        label, sentiment = three_way_crowd_mood(bull_pct, bear_pct, neutral_pct)
    else:
        # Neutral-only (or one-sided) results must not be misread as directional crowd evidence.
        label, sentiment = "दिशात्मक खोज स्पष्ट नहीं — तटस्थ", "NEUTRAL"

    terms = []
    for item in all_terms.values():
        terms.append({
            "term": item["term"], "dir": item["direction"],
            "now": round(item["weight"], 1), "avg": round(item["weight"], 1),
            "today_pct": None, "yesterday_pct": None
        })
    terms.sort(key=lambda x: x["now"], reverse=True)

    return {
        "ok": True, "unit": "Google Trends related-query share (%)",
        "crowd_bull_pct": crowd_bull_pct, "crowd_label": label,
        "bull_sum_pct": bull_pct, "bear_sum_pct": bear_pct,
        "min_side_pct": None, "crowd_terms": terms[:20],
        "spikes": [], "hidden_spikes": 0,
        "bull_score_pct": bull_pct, "bear_score_pct": bear_pct,
        "neutral_score_pct": neutral_pct, "sentiment_label": sentiment,
        "informational_weight": round(sum(
            item["weight"] for item in all_terms.values()
            if item["direction"] == "informational"
        ), 1),
        "informational_queries": sum(
            1 for item in all_terms.values() if item["direction"] == "informational"
        ),
        "informational_terms": [
            item["term"] for item in all_terms.values()
            if item["direction"] == "informational"
        ][:20],
        "today_bull_pct": crowd_bull_pct, "today_label": "पिछले 24 घंटे की related searches",
        "today_basis": "now_1d_related_queries" if timeframe == "now 1-d" else "related_queries_other",
        "source_timeframe": timeframe + " related queries",
        "source_data_time": source_data_time,
        "fallback_used": True, "queries_total": len(all_terms),
        "related_seed_count": len(per_seed)
    }


def _asset_search_is_out_of_scope(term, asset):
    """Return True only when a related query clearly belongs to another tracked asset."""
    text = str(term or "").lower().replace("़", "").replace("ँ", "ं")
    tokens = set(re.findall(r"[\w\u0900-\u097F-]+", text))
    has_bank = bool(tokens & {"bank", "बैंक", "banknifty", "बैंकनिफ्टी"})
    has_nifty = bool(tokens & {"nifty", "निफ्टी", "banknifty", "बैंकनिफ्टी"})
    has_sensex = bool(tokens & {"sensex", "सेंसेक्स"})
    has_gold = bool(tokens & {"gold", "गोल्ड", "सोना", "सोने", "स्वर्ण"})
    has_silver = bool(tokens & {"silver", "सिल्वर", "चांदी", "रजत"})
    if asset == "NIFTY":
        return has_bank or has_sensex or has_gold or has_silver
    if asset == "SENSEX":
        return has_nifty or has_bank or has_gold or has_silver
    if asset == "BANKNIFTY":
        return not (has_bank and has_nifty) or has_sensex or has_gold or has_silver
    if asset == "GOLD":
        return has_silver
    if asset == "SILVER":
        return has_gold
    if asset == "CRUDEOIL":
        non_crude_oil = {
            "gold", "silver", "nifty", "sensex", "bank", "bitcoin",
            "sunflower", "soybean", "palm", "edible", "cooking",
            "vegetable", "mustard", "groundnut",
            "सोना", "सोने", "चांदी", "रजत", "निफ्टी", "सेंसेक्स", "बैंक",
            "सूरजमुखी", "सोयाबीन", "पाम", "खाद्य", "सरसों", "मूंगफली",
        }
        return bool(tokens & non_crude_oil)
    return False


def _asset_search_direction(term, asset):
    """Classify asset-specific directional/explicit-flat queries; information intent is unclassified."""
    text = str(term or "").lower().replace("़", "").replace("ँ", "ं")
    tokens = set(re.findall(r"[\w\u0900-\u097F-]+", text))

    # Match common Hindi names as well as English asset names. Normalize
    # nukta/chandrabindu variants first; keep neighboring assets isolated.
    bank_compound = "banknifty" in tokens or "बैंकनिफ्टी" in tokens
    nifty_name = "nifty" in tokens or "निफ्टी" in tokens or bank_compound
    bank_name = "bank" in tokens or "बैंक" in tokens or bank_compound
    sensex_name = "sensex" in tokens or "सेंसेक्स" in tokens
    gold_name = bool(tokens & {"gold", "गोल्ड", "सोना", "सोने", "स्वर्ण"})
    silver_name = bool(tokens & {"silver", "सिल्वर", "चांदी", "रजत"})

    if asset == "NIFTY":
        if not nifty_name or bank_name:
            return None
    elif asset == "SENSEX":
        if not sensex_name or nifty_name:
            return None
    elif asset == "BANKNIFTY":
        if not (bank_name and nifty_name):
            return None
    elif asset == "GOLD":
        if not gold_name or silver_name:
            return None
    elif asset == "SILVER":
        if not silver_name or gold_name:
            return None
    elif asset == "CRUDEOIL":
        if _asset_search_is_out_of_scope(term, asset):
            return None
        # The "crude oil" seed scopes related searches; Google often omits seed words.
    else:
        return None

    # Shadow-only directional vocabulary is intentionally stricter than the
    # legacy global crowd classifier. Ambiguous intent words such as
    # "target", "high", "low", "buy" and "sell" must not become mood votes.
    # Negated or mixed-direction phrases are left unclassified.
    bullish_terms = {
        "bull", "bullish", "rally", "surge", "gain", "breakout",
        "recovery", "recover", "bounce", "uptrend", "rise", "rises",
        "rising", "jump", "jumps", "up", "upside", "higher", "positive",
        "outperform", "bullrun", "bull", "buying", "teji", "tez", "badhega",
        "badhegi", "badhne", "upar", "chadhega", "chadhav", "chadhne", "बढ़ने", "बढने",
        "बुलिश", "तेज़ी", "तेजी", "उछाल", "बढ़ेगा", "बढ़ेगी",
        "ऊपर", "बढ़त", "चढ़ा", "चढ़ेगा", "महंगा", "महंगी",
        "रिकवरी", "ब्रेकआउट", "रैली",
    }
    bearish_terms = {
        "bear", "bearish", "crash", "drop", "fall", "falls",
        "falling", "down", "downtrend", "selloff", "sell-off",
        "correction", "correct", "slump", "decline", "weakness",
        "downside", "lower", "weak", "negative", "underperform", "sell",
        "selling", "bearrun", "girawat", "girega", "giregi", "neeche", "mandi",
        "tutega", "गिरावट", "गिरेगा", "गिरेगी", "नीचे",
        "मंदी", "बेयरिश", "बिकवाली", "टूटेगा", "करेक्शन",
        "गिरा", "कमजोर", "कमज़ोर", "कमजोरी", "कमज़ोरी", "सस्ता", "सस्ती",
    }
    negation_terms = {"not", "no", "without", "never", "नहीं", "मत", "बिना"}
    if tokens & negation_terms:
        return None
    # A dated asset-specific "all-time/record/new high" query is directional
    # bullish intent; the corresponding low phrase is bearish. Keep bare
    # "high", "low", and "52 week high" ambiguous to avoid false positives.
    bullish_record_phrases = ("all time high", "record high", "new high", "lifetime high")
    bearish_record_phrases = ("all time low", "record low", "new low", "lifetime low")
    has_bull = bool(tokens & bullish_terms) or any(
        phrase in text for phrase in bullish_record_phrases
    )
    has_bear = bool(tokens & bearish_terms) or any(
        phrase in text for phrase in bearish_record_phrases
    )
    if has_bull and has_bear:
        # Mixed directional wording is ambiguous, not a neutral vote.
        return None
    if has_bull != has_bear:
        return "bull" if has_bull else "bear"

    # Explicit flat/range-bound language is neutral crowd intent.
    # Only explicit flat/range-bound wording is neutral crowd intent.
    # Navigation and information-seeking queries are not a mood vote.
    explicit_neutral = {
        "sideways", "sideway", "rangebound", "range-bound", "flat",
        "unchanged", "steady", "stable", "consolidation", "consolidating",
        "स्थिर", "सपाट", "सीमित", "दायरे", "साइडवेज",
    }
    if tokens & explicit_neutral:
        return "neutral"
    ambiguous = {"range", "target", "targets", "high", "low", "52"}
    if tokens & ambiguous:
        return None
    informational = {
        # Explicit navigation/time/analysis intent. Bare price/rate/quote terms
        # are deliberately excluded: "gold price" alone is not a mood vote.
        "today", "live", "current", "chart", "index", "market", "prediction",
        "predictions", "forecast", "forecasts", "option", "options", "chain",
        "expiry", "weekly", "monthly", "analysis", "technical", "support",
        "resistance", "level", "levels", "news", "tomorrow", "trading",
        "आज", "लाइव", "वर्तमान", "चार्ट", "अनुमान", "भविष्यवाणी",
        "ऑप्शन", "चेन", "एक्सपायरी", "विश्लेषण", "समाचार", "कल",
    }
    # Index/instrument lookup phrases are information intent, not neutral mood.
    informational_phrases = (
        "nifty 50", "gift nifty", "sgx nifty", "nse nifty",
        "nifty share", "nifty stock", "sensex share", "sensex stock",
        "bse sensex", "bank nifty 50",
    )
    if tokens & informational or any(phrase in text for phrase in informational_phrases):
        return "informational"
    return None



def _asset_rising_diagnostics(rising, asset):
    """Keep Google Trends rising queries as separate evidence, never as top-query weights."""
    if rising is None or getattr(rising, "empty", True) or "query" not in rising:
        return {
            "rising_queries": 0,
            "rising_classified_queries": 0,
            "rising_direction_counts": {"bull": 0, "bear": 0, "neutral": 0, "informational": 0, "unclassified": 0},
            "rising_terms": [],
        }

    counts = {"bull": 0, "bear": 0, "neutral": 0, "informational": 0, "unclassified": 0}
    terms = []
    for _, row in rising.iterrows():
        term = str(row.get("query", "")).strip()
        if not term:
            continue
        direction = _asset_search_direction(term, asset)
        category = direction if direction in ("bull", "bear", "neutral", "informational") else "unclassified"
        counts[category] += 1
        raw_value = row.get("value", "")
        value = str(raw_value).strip()
        terms.append({
            "term": term,
            "value": value,
            "direction": category,
            "breakout": value.lower() == "breakout",
        })
    terms.sort(key=lambda item: item["term"].lower())
    return {
        "rising_queries": len(terms),
        "rising_classified_queries": counts["bull"] + counts["bear"] + counts["neutral"],
        "rising_direction_counts": counts,
        "rising_terms": terms[:10],
    }


ASSET_DIRECTIONAL_TRENDS_QUERIES = {
    # Search-interest diagnostics only. Query volume is not proof of trader positioning.
    "NIFTY": {"seed": "nifty", "bull": "nifty breakout", "bear": "nifty crash", "neutral": "nifty sideways"},
    "SENSEX": {"seed": "sensex", "bull": "sensex rally", "bear": "sensex crash", "neutral": "sensex sideways"},
    "BANKNIFTY": {"seed": "bank nifty", "bull": "bank nifty breakout", "bear": "bank nifty crash", "neutral": "bank nifty sideways"},
    "GOLD": {"seed": "gold price", "bull": "gold price rise", "bear": "gold price fall", "neutral": "gold price stable"},
    "SILVER": {"seed": "silver price", "bull": "silver price rise", "bear": "silver price fall", "neutral": "silver price stable"},
    "CRUDEOIL": {"seed": "crude oil", "bull": "crude oil price rise", "bear": "crude oil price fall", "neutral": "crude oil price stable"},
}


def _summarize_asset_directional_trends(df, asset, spec):
    """Summarize asset-specific directional phrase interest; diagnostic only, never a crowd score."""
    if df is None or getattr(df, "empty", True):
        raise ValueError("Google Trends hourly directional-query data is empty")
    stamp = _trends_observation_time(df, f"Google Trends {asset} directional-query timestamp")
    seed = spec["seed"]
    required = (seed, spec["bull"], spec["bear"], spec["neutral"])
    missing = [term for term in required if term not in df.columns]
    if missing:
        raise ValueError("Google Trends columns missing: " + ", ".join(missing))
    anchor_recent = float(df[seed].tail(24).mean())
    if not math.isfinite(anchor_recent) or anchor_recent <= 0:
        raise ValueError(f"Google Trends {asset} anchor का ताज़ा search-interest शून्य है")
    ratios = {}
    for direction in ("bull", "bear", "neutral"):
        term_recent = float(df[spec[direction]].tail(24).mean())
        if not math.isfinite(term_recent) or term_recent < 0:
            raise ValueError(f"Google Trends {asset} {direction} phrase का डेटा अमान्य है")
        ratios[direction] = round((term_recent / anchor_recent) * 100.0, 2)
    total = sum(ratios.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("तीनों asset-specific directional phrases का ताज़ा search-interest शून्य है")
    mix = {key: round(value / total * 100.0, 1) for key, value in ratios.items()}
    return {
        "available": True,
        "diagnostic_only": True,
        "asset": asset,
        "seed": seed,
        "source": "Google Trends interest_over_time · India",
        "timeframe": "now 1-d",
        "source_data_time": stamp.isoformat(),
        "anchor_relative_interest_pct": ratios,
        "query_interest_mix_pct": mix,
        "query_terms": {key: spec[key] for key in ("bull", "bear", "neutral")},
        "interpretation": (
            "ये तीन चुने हुए search phrases की seed-relative खोज-रुचि है; "
            "यह सभी traders/खोजों का प्रतिशत या वास्तविक position नहीं है। "
            "इसे component Final में शामिल नहीं किया जाता।"
        ),
    }


def fetch_asset_directional_trends_diagnostics():
    """One fresh, asset-scoped phrase batch per asset; scheduled slots only in production."""
    from pytrends.request import TrendReq

    output = {}
    try:
        py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
    except Exception as exc:
        reason = str(exc)[:200]
        return {
            asset: {"available": False, "diagnostic_only": True, "reason": reason}
            for asset in ASSET_DIRECTIONAL_TRENDS_QUERIES
        }

    assets = list(ASSET_DIRECTIONAL_TRENDS_QUERIES.items())
    for position, (asset, spec) in enumerate(assets):
        try:
            # Space independent asset payloads to reduce burst pressure.
            if position:
                time.sleep(2)
            terms = [spec["seed"], spec["bull"], spec["bear"], spec["neutral"]]
            py.build_payload(terms, timeframe="now 1-d", geo="IN")
            frame = py.interest_over_time()
            output[asset] = _summarize_asset_directional_trends(frame, asset, spec)
        except Exception as exc:
            reason = str(exc)[:220]
            output[asset] = {
                "available": False,
                "diagnostic_only": True,
                "asset": asset,
                "seed": spec["seed"],
                "source": "Google Trends interest_over_time · India",
                "timeframe": "now 1-d",
                "reason": reason,
            }
            # Google Trends throttling is a hard stop. Do not continue with
            # the remaining four-phrase batches after a 429/rate-limit response.
            lowered = reason.lower()
            if "429" in lowered or "too many requests" in lowered or "rate limit" in lowered:
                for pending_asset, pending_spec in assets[position + 1:]:
                    output[pending_asset] = {
                        "available": False,
                        "diagnostic_only": True,
                        "asset": pending_asset,
                        "seed": pending_spec["seed"],
                        "source": "Google Trends interest_over_time · India",
                        "timeframe": "now 1-d",
                        "reason": "Google Trends rate limit; remaining asset requests stopped to protect quota",
                    }
                break
    return output


def _attach_asset_directional_trends_diagnostics(output, seeds, enabled=False):
    """Attach optional phrase diagnostics without extra Trends calls by default."""
    directional_diagnostics = (
        fetch_asset_directional_trends_diagnostics() if enabled else {}
    )
    for asset in seeds:
        record = output.setdefault(asset, {
            "valid": False, "scope": "asset_specific_google_related_queries_shadow",
            "seed": seeds[asset], "source": "Google Trends related_queries · India",
            "timeframe": "now 1-d", "reason": "Related-query snapshot unavailable",
            "production_score_used": False,
        })
        if enabled:
            record["directional_query_diagnostic"] = directional_diagnostics.get(asset, {
                "available": False, "diagnostic_only": True,
                "reason": "Directional diagnostic result missing",
            })
        else:
            record["directional_query_diagnostic"] = {
                "available": False,
                "diagnostic_only": True,
                "reason": "अतिरिक्त Google Trends अनुरोध बचाने के लिए वैकल्पिक phrase diagnostic बंद है",
            }
    return output


def _summarize_asset_related_query_snapshot(related, asset, seed, source_data_time, source, timestamp_basis="source_observation"):
    """Classify one seed's real related queries; no cross-seed score mixing."""
    pack = (related or {}).get(seed) or {}
    top = pack.get("top")
    rising_diagnostics = _asset_rising_diagnostics(pack.get("rising"), asset)
    totals = {"bull": 0.0, "bear": 0.0, "neutral": 0.0}
    classified_terms = []
    informational_terms = []
    raw_query_count = unclassified_count = out_of_scope_count = in_scope_count = 0
    unclassified_weight = out_of_scope_weight = informational_weight = 0.0
    unclassified_terms = []
    if top is not None and not top.empty and "query" in top and "value" in top:
        for _, row in top.iterrows():
            term = str(row.get("query", "")).strip()
            try:
                value = float(row.get("value", 0) or 0)
            except (TypeError, ValueError):
                continue
            if not term or not math.isfinite(value) or value <= 0:
                continue
            raw_query_count += 1
            if _asset_search_is_out_of_scope(term, asset):
                out_of_scope_count += 1
                out_of_scope_weight += value
                continue
            in_scope_count += 1
            direction = _asset_search_direction(term, asset)
            if direction == "informational":
                informational_weight += value
                informational_terms.append({"term": term, "weight": round(value, 1)})
                continue
            if direction not in totals:
                unclassified_count += 1
                unclassified_weight += value
                unclassified_terms.append({"term": term, "weight": round(value, 1)})
                continue
            totals[direction] += value
            classified_terms.append({"term": term, "direction": direction, "weight": round(value, 1)})
    bull, bear, neutral = totals["bull"], totals["bear"], totals["neutral"]
    total = bull + bear + neutral
    coverage_denominator = total + unclassified_weight + informational_weight
    if len(classified_terms) < 3 or total <= 0:
        return {
            "valid": False, "scope": "asset_specific_google_related_queries_shadow",
            "seed": seed, "source": source, "timeframe": "now 1-d",
            "source_data_time": source_data_time,
            "raw_queries": raw_query_count, "in_scope_queries": in_scope_count,
            "out_of_scope_queries": out_of_scope_count,
            "out_of_scope_weight": round(out_of_scope_weight, 1),
            "classified_queries": len(classified_terms),
            "unclassified_queries": unclassified_count,
            "unclassified_weight": round(unclassified_weight, 1),
            "classification_coverage_pct": round((total + informational_weight) / coverage_denominator * 100.0, 1) if coverage_denominator > 0 else None,
            "unclassified_terms": sorted(unclassified_terms, key=lambda x: x["weight"], reverse=True)[:10],
            "informational_queries": len(informational_terms),
            "informational_weight": round(informational_weight, 1),
            "informational_terms": sorted(informational_terms, key=lambda x: x["weight"], reverse=True)[:10],
            **rising_diagnostics,
            "reason": f"पर्याप्त directional/explicit-neutral queries नहीं (classified={len(classified_terms)}, informational={len(informational_terms)}, total_weight={total:.1f})",
            "production_score_used": False,
        }
    bull_pct, bear_pct, neutral_pct = bull / total * 100.0, bear / total * 100.0, neutral / total * 100.0
    directional_total = bull + bear
    return {
        "valid": True, "scope": "asset_specific_google_related_queries_shadow",
        "seed": seed, "source": source, "timeframe": "now 1-d",
        "source_data_time": source_data_time if timestamp_basis == "source_observation" else None,
        "as_of": source_data_time if timestamp_basis == "source_observation" else None,
        "retrieved_at": source_data_time if timestamp_basis == "retrieval_time" else None,
        "timestamp_basis": timestamp_basis,
        "unit": "classified related-query relative-weight share",
        "denominator": "same seed's classified related-query relative weights only; not all searches or population percentages",
        "raw_queries": raw_query_count, "in_scope_queries": in_scope_count,
        "out_of_scope_queries": out_of_scope_count, "out_of_scope_weight": round(out_of_scope_weight, 1),
        "classified_queries": len(classified_terms), "unclassified_queries": unclassified_count,
        "unclassified_weight": round(unclassified_weight, 1),
        "unclassified_terms": sorted(unclassified_terms, key=lambda x: x["weight"], reverse=True)[:10],
        "informational_queries": len(informational_terms),
        "informational_weight": round(informational_weight, 1),
        "informational_terms": sorted(informational_terms, key=lambda x: x["weight"], reverse=True)[:10],
        "classification_coverage_pct": round((total + informational_weight) / coverage_denominator * 100.0, 1) if coverage_denominator > 0 else None,
        "bull_pct": round(bull_pct, 1), "bear_pct": round(bear_pct, 1), "neutral_pct": round(neutral_pct, 1),
        "directional_bull_pct": round(bull / directional_total * 100.0, 1) if directional_total > 0 else None,
        "neutral_aware_score": round(max(-10.0, min(10.0, (bull_pct - bear_pct) / 100.0 * 10.0)), 2) if directional_total > 0 else None,
        "terms": sorted(classified_terms, key=lambda x: x["weight"], reverse=True)[:8],
        **rising_diagnostics, "production_score_used": False,
    }


def fetch_crude_trends_shadow():
    """Refresh only CRUDEOIL one-day related queries in a scheduled slot.

    This independent path prevents a primary index Crowd Trends outage from
    suppressing CRUDEOIL Search data. It makes exactly one isolated payload
    and is never used by ordinary 30-minute scans.
    """
    from pytrends.request import TrendReq

    seed = "crude oil"
    source = "Google Trends related_queries · India"
    try:
        time.sleep(2)
        py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
        py.build_payload([seed], timeframe="now 1-d", geo="IN")
        related = py.related_queries()
        try:
            observed = py.interest_over_time()
        except Exception as timestamp_error:
            observed = None
            print(f"Google Trends CRUDEOIL hourly timestamp request unavailable: {str(timestamp_error)[:160]}")
        source_time, timestamp_basis = _trends_snapshot_timestamp(
            observed, "Google Trends CRUDEOIL batch timestamp"
        )
        return {"CRUDEOIL": _summarize_asset_related_query_snapshot(
            related, "CRUDEOIL", seed, source_time, source, timestamp_basis
        )}
    except Exception as exc:
        reason = str(exc)[:220]
        print(f"Google Trends CRUDEOIL independent batch unavailable: {reason}")
        return {"CRUDEOIL": {
            "valid": False,
            "scope": "asset_specific_google_related_queries_shadow",
            "seed": seed, "source": source, "timeframe": "now 1-d",
            "reason": reason, "production_score_used": False,
        }}

def fetch_asset_trends_shadow(include_directional_diagnostics=False, include_crude=False):
    """Refresh five asset seeds together; optionally refresh CRUDEOIL separately.

    Scheduled slots may opt into phrase diagnostics. Manual scans refresh the
    five asset seeds plus CRUDEOIL but leave the six extra phrase batches off.
    """
    from pytrends.request import TrendReq

    seeds = {
        "NIFTY": "nifty",
        "SENSEX": "sensex",
        "BANKNIFTY": "bank nifty",
        "GOLD": "gold price",
        "SILVER": "silver price",
    }
    source = "Google Trends related_queries · India"
    output = {}
    try:
        py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
        py.build_payload(list(seeds.values()), timeframe="now 1-d", geo="IN")
        related = py.related_queries()
        try:
            observed = py.interest_over_time()
        except Exception as timestamp_error:
            observed = None
            print(f"Google Trends asset batch hourly timestamp request unavailable: {str(timestamp_error)[:160]}")
        source_data_time, timestamp_basis = _trends_snapshot_timestamp(
            observed, "Google Trends asset batch timestamp"
        )
        for asset, seed in seeds.items():
            output[asset] = _summarize_asset_related_query_snapshot(
                related, asset, seed, source_data_time, source, timestamp_basis
            )

        if include_crude:
            crude_seed = "crude oil"
            try:
                # One additional asset-only batch; callers enable it only for
                # scheduled slots or an explicit manual refresh after primary success.
                time.sleep(2)
                crude_py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
                crude_py.build_payload([crude_seed], timeframe="now 1-d", geo="IN")
                crude_related = crude_py.related_queries()
                try:
                    crude_observed = crude_py.interest_over_time()
                except Exception as timestamp_error:
                    crude_observed = None
                    print(f"Google Trends CRUDEOIL hourly timestamp request unavailable: {str(timestamp_error)[:160]}")
                crude_source_time, crude_timestamp_basis = _trends_snapshot_timestamp(
                    crude_observed, "Google Trends CRUDEOIL batch timestamp"
                )
                output["CRUDEOIL"] = _summarize_asset_related_query_snapshot(
                    crude_related, "CRUDEOIL", crude_seed, crude_source_time, source,
                    crude_timestamp_basis
                )
            except Exception as crude_error:
                reason = str(crude_error)[:220]
                output["CRUDEOIL"] = {
                    "valid": False, "scope": "asset_specific_google_related_queries_shadow",
                    "seed": crude_seed, "source": source, "timeframe": "now 1-d",
                    "reason": reason, "production_score_used": False,
                }
                print(f"Google Trends CRUDEOIL batch unavailable: {reason}")
    except Exception as exc:
        reason = str(exc)[:240]
        for asset, seed in seeds.items():
            output[asset] = {
                "valid": False,
                "scope": "asset_specific_google_related_queries_shadow",
                "seed": seed,
                "source": source,
                "timeframe": "now 1-d",
                "reason": reason,
                "production_score_used": False,
            }
    # Optional only: one bounded phrase payload per requested asset. Keep
    # disabled by default; scheduled scans explicitly enable it. Include crude
    # only when its independent related-query payload was requested.
    diagnostic_seeds = dict(seeds)
    if include_crude:
        diagnostic_seeds["CRUDEOIL"] = "crude oil"
    return _attach_asset_directional_trends_diagnostics(
        output, diagnostic_seeds, enabled=include_directional_diagnostics
    )


def fetch_index_trends_shadow():
    """Backward-compatible wrapper; reuse the single five-seed one-day batch."""
    all_assets = fetch_asset_trends_shadow()
    return {
        name: all_assets.get(name) or {"valid": False, "reason": "asset Search reading unavailable"}
        for name in ("NIFTY", "SENSEX", "BANKNIFTY")
    }


def is_google_trends_rate_limited(message):
    """Recognize provider throttling so fallback calls do not amplify a 429."""
    lowered = str(message or "").lower()
    return any(token in lowered for token in ("429", "too many requests", "rate limit", "ratelimit"))


def should_run_asset_directional_diagnostics(slot_id):
    """Run the six extra phrase batches once daily, in the final scheduled slot."""
    return str(slot_id or "").strip() == "1900"


def fetch_trends():
    """पहले 1-दिन/7-दिन hourly डेटा; विफल होने पर असली related searches से सीमित fallback."""
    try:
        import pytrends  # noqa: F401
    except Exception as e:
        return {"ok": False, "error": f"pytrends नहीं मिला: {e}"}

    errors = []
    attempts = (
        ("hourly_1d", lambda: _trends_once(timeframe="now 1-d", recent_points=24)),
        ("hourly_7d", lambda: _trends_once(timeframe="now 7-d", recent_points=24)),
        ("related_1d", lambda: _trends_related_queries(timeframe="now 1-d")),
        ("related_7d", lambda: _trends_related_queries(timeframe="now 7-d")),
    )
    result = None
    selected = None
    for name, fetch in attempts:
        try:
            result = fetch()
            selected = name
            break
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            if is_google_trends_rate_limited(exc):
                print(f"Google Trends {name} hit provider rate limit; stopping fallback requests: {exc}")
                break
            print(f"Google Trends {name} failed; trying next real-data source: {exc}")

    if result is None:
        return {
            "ok": False, "stale": False,
            "error": "नया Google Trends डेटा नहीं मिला। " + " | ".join(errors)
        }

    used_fallback = selected != "hourly_1d"
    if selected == "hourly_1d":
        result["today_label"] = "पिछले 24 घंटे की Google Trends खोज-रुचि"
        result["today_basis"] = result.get("today_basis", "now_1d_anchor_relative")
        result["source_timeframe"] = "now 1-d"
    elif selected == "hourly_7d":
        result["today_label"] = "7-दिन श्रृंखला के अंतिम 24 वास्तविक observations"
        result["today_basis"] = "now_7d_last_24_observations"
        result["source_timeframe"] = "now 7-d · last 24 observations"
    elif selected == "related_1d":
        result["today_label"] = "पिछले 24 घंटे की वास्तविक related searches"
        result["today_basis"] = "now_1d_related_queries"
        result["source_timeframe"] = "now 1-d related queries"
    else:
        result["today_label"] = "7-दिन की वास्तविक related searches"
        result["today_basis"] = "now_7d_related_queries"
        result["source_timeframe"] = "now 7-d related queries"

    result.setdefault("fear_vs_avg", None)
    result.setdefault("per_term", [])
    result["fallback_used"] = used_fallback
    if selected.startswith("related_"):
        result["fallback_source"] = "Google Trends related_queries"
        result["fallback_attempts_failed"] = errors
    else:
        result["fallback_source"] = "Google Trends hourly interest_over_time"
        result["fallback_attempts_failed"] = errors
    result["today_bull_pct"] = result.get("crowd_bull_pct") if selected.endswith("1d") else None
    result["search_groups"] = {
        "bullish": BULL_TERMS, "bearish": BEAR_TERMS, "neutral": NEUTRAL_TERMS
    }
    result["request_policy"] = (
        "timestamp-validated real Google Trends data: hourly 1-d, hourly 7-d, "
        "related 1-d, related 7-d; stop at first valid result"
    )
    return result

def update_crowd(events, crowd_pct, today_str, nifty_ret):
    """भीड़ एकतरफ़ा हो तो उस दिन दर्ज करें। अगले सत्र की Nifty चाल से नतीजा भरें।
    crowd_pct None हो (पर्याप्त डेटा नहीं) तो कुछ दर्ज नहीं होता।"""
    if crowd_pct is not None and (crowd_pct >= CROWD_EXTREME or crowd_pct <= CROWD_LOW) and not SKIP_EVENTS:
        key = f"{today_str}|crowd"
        if not any(e["key"] == key for e in events):
            events.append({
                "key": key, "date": today_str,
                "direction": "bull" if crowd_pct >= CROWD_EXTREME else "bear",
                "crowd_pct": crowd_pct, "next_change": None, "outcome": None,
            })

    for e in events:
        if e.get("outcome") is not None:
            continue
        later = sorted(d for d in nifty_ret if d > e["date"])
        if not later:
            continue
        nxt = nifty_ret[later[0]]
        e["next_change"] = nxt
        crowd_up = e["direction"] == "bull"
        price_up = nxt >= 0
        e["outcome"] = "followed" if crowd_up == price_up else "trap"


def pick_with_fallback(fresh, prev):
    """ताज़ा सफल हो तो वही; वरना पिछला सफल डेटा 'stale' चिह्न के साथ।"""
    if fresh.get("ok"):
        fresh["stale"] = False
        return fresh
    if prev.get("ok"):
        stale = dict(prev)
        stale["stale"] = True
        stale["error"] = fresh.get("error", "")
        return stale
    fresh["stale"] = False
    return fresh

def trends_within_freshness(data, now_utc=None):
    """Google Trends fetch timestamp की उम्र जाँचें; पुराना डेटा कभी ताज़ा न मानें।"""
    if not data or not data.get("ok") or not data.get("as_of"):
        return False
    try:
        stamp = dt.datetime.fromisoformat(str(data["as_of"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        now = now_utc or dt.datetime.now(dt.timezone.utc)
        age_minutes = (now - stamp.astimezone(dt.timezone.utc)).total_seconds() / 60
        return -5 <= age_minutes <= TRENDS_MAX_AGE_MINUTES
    except (TypeError, ValueError):
        return False



def market_closed_today(now_utc=None):
    """भारतीय बाज़ार आज बंद है? (सप्ताहांत, सूची में दी गई छुट्टी, या शाम 4 बजे के बाद
    भी आज का NIFTY बार न होना)। सुबह की छुट्टी सूची के बिना नहीं पकड़ी जा सकती।
    now_utc वैकल्पिक है ताकि market-status tests deterministic रहें।"""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    ist = now.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    today = ist.date().isoformat()
    calendar = load_json(EXCHANGE_CALENDAR_FILE, {})
    holidays = {
        str(item.get("date"))
        for item in calendar.get("holidays", [])
        if isinstance(item, dict) and item.get("date")
    }
    special_session = (calendar.get("special_sessions") or {}).get(today)
    if special_session:
        # Only the continuous trading window counts as live for scanner signals;
        # pre-open and post-close remain closed for price/signal processing.
        start = dt.time.fromisoformat(special_session["regular_start"])
        end = dt.time.fromisoformat(special_session["regular_end"])
        return not (start <= ist.time() < end)
    if today in holidays or ist.weekday() >= 5:
        return True
    if ist.hour < 16:
        return False
    try:
        h = yf.Ticker("^NSEI").history(period="5d", interval="1d")
        dates = {d.date().isoformat() for d in h.index}
        return today not in dates
    except Exception as e:
        print(f"market status check failed: {e}")
        return False


STOCK_REFRESH_HOURS_IST = (10, 16)


def stock_refresh_slot(now_utc):
    """अभी की स्टॉक-विश्लेषण स्लॉट (IST 10:00 या 16:00 में से पिछली)। इससे पहले का स्लॉट कल का होता है।"""
    ist = (now_utc + dt.timedelta(hours=5, minutes=30)).replace(tzinfo=None)
    slots = []
    for day_off in (0, -1):
        day = (ist + dt.timedelta(days=day_off)).date()
        for h in STOCK_REFRESH_HOURS_IST:
            slots.append(dt.datetime(day.year, day.month, day.day, h))
    past = [x for x in slots if x <= ist]
    return max(past).isoformat() if past else None


def retail_adjust(po):
    """CLIENT option-position adjustment kept as a dated diagnostic, not a score input."""
    if not po or not po.get("ok"):
        return 0.0, None
    c = (po.get("participants") or {}).get("CLIENT") or {}
    def share(l, sh):
        l, sh = c.get(l), c.get(sh)
        if l is None or sh is None or (l + sh) <= 0:
            return None
        return round(l / (l + sh) * 100, 1)
    ce = share("index_call_long", "index_call_short")
    pe = share("index_put_long", "index_put_short")
    if ce is None or pe is None:
        return 0.0, None
    adj = round(max(-2.0, min(2.0, (ce - pe) / 10)), 2)
    bias = "Bullish" if adj > 0 else ("Bearish" if adj < 0 else "Neutral")
    return adj, {"ce_pct": ce, "pe_pct": pe, "bias": bias, "date": po.get("date"), "adj": adj}


def validated_news_crowd_score(news_component, crowd_component=None, crowd_valid=False):
    """Score only validated News and crowd components; participant OI stays diagnostic."""
    news = finite_number(news_component)
    if news is None:
        raise ValueError("news component must be a finite number")
    crowd = finite_number(crowd_component)
    if crowd_valid and crowd is not None:
        combined = news * 0.50 + crowd * 0.50
        mode = "news_crowd"
        normalized_weights = {"news": 50.0, "crowd": 50.0}
    else:
        combined = news
        mode = "news_only"
        normalized_weights = {"news": 100.0}
    return round(max(-10.0, min(10.0, combined)), 1), mode, normalized_weights


def participant_changes(today, prev):
    """आज और पिछले उपलब्ध दिन के NSE participant आँकड़ों का अंतर (बदलाव)।
    पिछला दिन data.json से लिया जाता है; उसी तारीख का हो तो कुछ नहीं बनता।"""
    if not today.get("ok") or not prev.get("ok") or prev.get("date") == today.get("date"):
        return {"ok": False, "prev_date": None, "by_group": {}}
    P, Q = today.get("participants", {}), prev.get("participants", {})
    keys = ["future_index_long", "future_index_short", "index_call_long",
            "index_call_short", "index_put_long", "index_put_short"]
    out = {}
    for grp in ["FII", "DII", "PRO", "CLIENT"]:
        if grp in P and grp in Q:
            d = {}
            for k in keys:
                a, b = P[grp].get(k), Q[grp].get(k)
                d[k] = (a - b) if (a is not None and b is not None) else None
            out[grp] = d
    return {"ok": bool(out), "prev_date": prev.get("date"), "by_group": out}


PARTICIPANT_HISTORY_FILE = "participant_oi_history.json"
PARTICIPANT_HISTORY_KEEP = 520
PARTICIPANT_OI_BACKFILL_VERSION = 8
PARTICIPANT_OI_BACKFILL_TARGET = 500
PARTICIPANT_OI_BACKFILL_MAX_REQUESTS = 3
PARTICIPANT_OI_BACKFILL_RETRY_SECONDS = 86400
PARTICIPANT_OI_BACKFILL_CALENDAR_DAYS = 421


def update_participant_oi_history(*snapshots):
    """सत्यापित NSE EOD participant snapshots को तारीख-वार सुरक्षित रखें."""
    try:
        archive = load_json(PARTICIPANT_HISTORY_FILE, {})
    except Exception as exc:
        print(f"participant OI history read failed; starting safe archive: {exc}")
        archive = {}
    if not isinstance(archive, dict):
        archive = {}
    records = archive.get("records")
    if not isinstance(records, list):
        records = []

    by_date = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        date = record.get("date")
        participants = record.get("participants")
        if (isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
                and isinstance(participants, dict) and participants):
            by_date[date] = {
                "date": date,
                "source": record.get("source", "NSE participant-wise OI archive"),
                "scope": record.get("scope", "Index F&O participant totals"),
                "participants": participants,
            }

    added = 0
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or not snapshot.get("ok") or snapshot.get("stale"):
            continue
        date = snapshot.get("date")
        participants = snapshot.get("participants")
        if (not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
                or not isinstance(participants, dict)
                or not all(group in participants for group in ("FII", "DII", "PRO", "CLIENT"))):
            continue
        if date not in by_date:
            added += 1
        by_date[date] = {
            "date": date,
            "source": snapshot.get("source", "NSE participant-wise OI archive"),
            "scope": snapshot.get("scope", "Index F&O participant totals"),
            "participants": participants,
        }

    # One-time, rate-limited backfill toward 500 official NSE trading sessions.
    # Exact-date archive requests only; retry at most once per 24 hours if incomplete.
    backfill_state = archive.get("backfill") if isinstance(archive.get("backfill"), dict) else {}
    now = dt.datetime.now(dt.timezone.utc)
    last_attempt = None
    try:
        raw_attempt = backfill_state.get("attempted_at")
        last_attempt = dt.datetime.fromisoformat(raw_attempt.replace("Z", "+00:00")) if raw_attempt else None
        if last_attempt and last_attempt.tzinfo is None:
            last_attempt = last_attempt.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        last_attempt = None

    backfilled = 0
    special_session_dates = sorted(
        date for date in nse_special_session_dates()
        if date <= now.date().isoformat()
    )
    missing_special_dates = [
        date for date in special_session_dates if date not in by_date
    ]
    # Keep the ordinary PDMP scan from issuing hundreds of historical NSE
    # requests in one run. Resume a dated cursor and make at most three
    # exact-session requests per 24-hour backfill window.
    retry_due = (backfill_state.get("version") != PARTICIPANT_OI_BACKFILL_VERSION
                  or last_attempt is None
                  or (now - last_attempt).total_seconds() >= PARTICIPANT_OI_BACKFILL_RETRY_SECONDS)
    needs_backfill = len(by_date) < PARTICIPANT_OI_BACKFILL_TARGET or bool(missing_special_dates)
    if needs_backfill and retry_due:
        if backfill_state.get("version") == PARTICIPANT_OI_BACKFILL_VERSION:
            try:
                cursor_date = dt.date.fromisoformat(backfill_state.get("next_date", ""))
                days_remaining = max(0, int(backfill_state.get("calendar_days_remaining", 0)))
            except (TypeError, ValueError):
                cursor_date = dt.date.fromisoformat(min(by_date)) - dt.timedelta(days=1) if by_date else now.date() - dt.timedelta(days=1)
                days_remaining = PARTICIPANT_OI_BACKFILL_CALENDAR_DAYS
        else:
            cursor_date = dt.date.fromisoformat(min(by_date)) - dt.timedelta(days=1) if by_date else now.date() - dt.timedelta(days=1)
            days_remaining = PARTICIPANT_OI_BACKFILL_CALENDAR_DAYS

        requests_this_run = 0
        special_sessions_checked = []
        # Special weekend sessions are explicit exchange-calendar entries.
        # Check them even when the ordinary 500-session target is already met.
        for special_date in missing_special_dates:
            if requests_this_run >= PARTICIPANT_OI_BACKFILL_MAX_REQUESTS:
                break
            requests_this_run += 1
            special_sessions_checked.append(special_date)
            historical = fetch_participant_oi(base_date=special_date, lookback_days=0)
            if (not isinstance(historical, dict) or not historical.get("ok")
                    or historical.get("stale") or historical.get("date") != special_date):
                continue
            participants = historical.get("participants")
            if (not isinstance(participants, dict)
                    or not all(group in participants for group in ("FII", "DII", "PRO", "CLIENT"))
                    or special_date in by_date):
                continue
            by_date[special_date] = {
                "date": special_date,
                "source": historical.get("source", "NSE official participant-wise OI"),
                "scope": historical.get("scope", "Index F&O participant totals"),
                "participants": participants,
            }
            backfilled += 1

        while (len(by_date) < PARTICIPANT_OI_BACKFILL_TARGET and requests_this_run < PARTICIPANT_OI_BACKFILL_MAX_REQUESTS
               and days_remaining > 0):
            target_day = cursor_date
            cursor_date -= dt.timedelta(days=1)
            days_remaining -= 1
            if (target_day.weekday() >= 5
                    and target_day.isoformat() not in special_session_dates):
                continue
            requests_this_run += 1
            historical = fetch_participant_oi(base_date=target_day, lookback_days=0)
            if not isinstance(historical, dict) or not historical.get("ok") or historical.get("stale"):
                continue
            date = historical.get("date")
            participants = historical.get("participants")
            if (not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
                    or not isinstance(participants, dict)
                    or not all(group in participants for group in ("FII", "DII", "PRO", "CLIENT"))
                    or date in by_date):
                continue
            by_date[date] = {
                "date": date,
                "source": historical.get("source", "NSE official participant-wise OI"),
                "scope": historical.get("scope", "Index F&O participant totals"),
                "participants": participants,
            }
            backfilled += 1

        missing_special_dates = [
            date for date in special_session_dates if date not in by_date
        ]
        backfill_state = {
            "version": PARTICIPANT_OI_BACKFILL_VERSION,
            "status": "complete" if len(by_date) >= PARTICIPANT_OI_BACKFILL_TARGET and not missing_special_dates else "partial",
            "attempted_at": now.isoformat(timespec="minutes").replace("+00:00", "Z"),
            "sessions_added": backfilled,
            "requests_this_run": requests_this_run,
            "target_sessions": PARTICIPANT_OI_BACKFILL_TARGET,
            "special_sessions_checked": special_sessions_checked,
            "missing_special_dates": missing_special_dates,
            "next_date": cursor_date.isoformat(),
            "calendar_days_remaining": days_remaining,
        }

    ordered = [by_date[d] for d in sorted(by_date)][-PARTICIPANT_HISTORY_KEEP:]
    return {
        "schema_version": 1,
        "source": "NSE participant-wise Open Interest daily EOD CSV",
        "retention_sessions": PARTICIPANT_HISTORY_KEEP,
        "backfill": backfill_state,
        "records": ordered,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z"),
        "added_this_run": added,
    }



def compact_trends_slot_evidence(trends):
    """Keep compact, point-in-time proof for each scheduled Google Trends slot."""
    labels = {"0915": "09:15", "1100": "11:00", "1300": "13:00", "1900": "19:00"}
    daily = trends.get("daily_slots") if isinstance(trends, dict) else {}
    daily = daily if isinstance(daily, dict) else {}
    records = daily.get("slots") if isinstance(daily.get("slots"), dict) else {}
    evidence = []
    for key, label in labels.items():
        source = records.get(key)
        if not isinstance(source, dict):
            evidence.append({"id": key, "time": label, "status": "pending"})
            continue
        status = source.get("status") if source.get("status") in ("success", "failed") else "pending"
        row = {"id": key, "time": label, "status": status}
        if status == "success":
            row.update({
                "source_data_time": source.get("source_data_time"),
                "basis": source.get("basis"),
                "timeframe": source.get("timeframe"),
                "bull_pct": source.get("bull_pct"),
                "bear_pct": source.get("bear_pct"),
                "neutral_pct": source.get("neutral_pct"),
                "crowd_pct": source.get("crowd_pct"),
            })
        elif source.get("checked_at"):
            row["checked_at"] = source.get("checked_at")
        if status == "failed" and source.get("error"):
            row["error"] = str(source.get("error"))[:240]
        evidence.append(row)
    return {"date": daily.get("date"), "slots": evidence}


def update_market_signal_history(result):
    """Capture one point-in-time EOD snapshot per trading date for honest future testing."""
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    now_ist = dt.datetime.now(ist)
    if now_ist.time() < dt.time(20, 0) or SKIP_EVENTS:
        return

    date = now_ist.date().isoformat()
    oi = result.get("participant_oi") or {}
    instruments = result.get("instruments") or {}
    # Component-history capture must not depend on participant OI availability.
    # Preserve the same-session component scores and closes even when OI is
    # missing; the archive validator still excludes that session from any
    # combined News/Trends/OI backtest unless dated OI and its prior session exist.

    def as_market_date(value):
        if not isinstance(value, str):
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return dt.datetime.strptime(value[:10], fmt).date().isoformat()
            except ValueError:
                pass
        return None

    index_names = ("NIFTY", "SENSEX", "BANKNIFTY")
    index_records = {}
    for name in index_names:
        item = instruments.get(name)
        if not isinstance(item, dict):
            item = {}
        try:
            close_value = float(item.get("price"))
            close_valid = (
                math.isfinite(close_value) and close_value > 0
                and as_market_date(item.get("price_as_of")) == date
            )
        except (TypeError, ValueError):
            close_value = None
            close_valid = False
        headlines = item.get("headlines") or []
        index_records[name] = {
            "close": close_value if close_valid else None,
            "close_as_of": item.get("price_as_of"),
            "close_valid": close_valid,
            "day_change_pct": item.get("change_pct"),
            "price_source": item.get("price_source"),
            "score_mode": item.get("score_mode"),
            "component_breakdown": item.get("component_breakdown"),
            "headline_score": item.get("headline_score"),
            "experimental_news_score": item.get("experimental_news_score"),
            "experimental_score": item.get("experimental_score"),
            "experimental_score_mode": item.get("experimental_score_mode"),
            "experimental_headline_count": item.get("experimental_headline_count"),
            "experimental_excluded_old_or_unknown": item.get("experimental_excluded_old_or_unknown"),
            "experimental_excluded_cross_index_duplicates": item.get("experimental_excluded_cross_index_duplicates"),
            "headline_count": len(headlines),
            "headlines": [
                {
                    "title": h.get("title"),
                    "source": h.get("source"),
                    "score": h.get("score"),
                    "age_hours": h.get("age_h"),
                }
                for h in headlines[:8] if isinstance(h, dict)
            ],
            "client_retail_adjustment": item.get("retail_adj"),
            "published_score": item.get("score"),
            "published_score_mode": item.get("score_mode"),
        }

    # GOLD and SILVER are captured from the same already-fetched scan result.
    # This adds no provider request; a close is eligible only when its source date
    # matches this exchange-local session.
    other_asset_records = {}
    for name in ("GOLD", "SILVER"):
        item = instruments.get(name)
        if not isinstance(item, dict):
            continue
        try:
            close_value = float(item.get("price"))
            close_valid = (
                math.isfinite(close_value) and close_value > 0
                and as_market_date(item.get("price_as_of")) == date
            )
        except (TypeError, ValueError):
            close_value = None
            close_valid = False
        headlines = item.get("headlines") or []
        other_asset_records[name] = {
            "close": close_value if close_valid else None,
            "close_as_of": item.get("price_as_of"),
            "close_valid": close_valid,
            "price_source": item.get("price_source"),
            "day_change_pct": item.get("change_pct"),
            "headline_score": item.get("headline_score"),
            "published_score": item.get("score"),
            "component_breakdown": item.get("component_breakdown"),
            "asset_search_shadow": item.get("asset_search_shadow"),
            "headline_count": len(headlines),
            "headlines": [
                {"title": h.get("title"), "source": h.get("source"),
                 "score": h.get("score"), "age_hours": h.get("age_h")}
                for h in headlines[:8] if isinstance(h, dict)
            ],
        }

    trends = result.get("trends") or {}
    trends_valid = bool(
        trends.get("ok") and not trends.get("stale")
        and isinstance(trends.get("crowd_bull_pct"), (int, float))
        and isinstance(trends.get("bull_score_pct"), (int, float))
        and isinstance(trends.get("bear_score_pct"), (int, float))
        and isinstance(trends.get("neutral_score_pct"), (int, float))
    )
    market_news = result.get("market_news") or {}
    record = {
        "date": date,
        "captured_at_utc": result.get("updated"),
        "captured_at_ist": now_ist.isoformat(timespec="minutes"),
        "price_source_note": "Index close must be dated to this trading session",
        "news_capture_time_utc": result.get("updated"),
        "trends": ({
            "valid": True,
            "as_of": trends.get("as_of"),
            "source_data_time": trends.get("source_data_time"),
            "daily_label": trends.get("daily_label"),
            "crowd_bull_pct": trends.get("crowd_bull_pct"),
            "bull_score_pct": trends.get("bull_score_pct"),
            "bear_score_pct": trends.get("bear_score_pct"),
            "neutral_score_pct": trends.get("neutral_score_pct"),
            "daily_complete": trends.get("daily_complete") is True,
            "daily_slot_evidence": compact_trends_slot_evidence(trends),
        } if trends_valid else {
            "valid": False,
            "reason": trends.get("error") or trends.get("daily_status_note") or "No fresh validated Trends reading",
            "daily_complete": trends.get("daily_complete") is True,
            "daily_slot_evidence": compact_trends_slot_evidence(trends),
        }),
        "market_news_context": {
            "ok": bool(market_news.get("ok")),
            "as_of": market_news.get("as_of"),
            "items": [
                {"topic": x.get("topic"), "title": x.get("title"),
                 "source": x.get("source"), "score": x.get("score"),
                 "age_hours": x.get("age_h")}
                for x in (market_news.get("items") or [])[:12] if isinstance(x, dict)
            ],
        },
        "indices": index_records,
        "other_assets": other_asset_records,
        "participant_oi": {
            "date": oi.get("date"),
            "source": oi.get("source"),
            "scope": oi.get("scope"),
            "changes": oi.get("changes"),
            "participants": oi.get("participants"),
        },
        "score_method": result.get("index_score_method"),
    }

    archive = load_json(MARKET_SIGNAL_HISTORY_FILE, {
        "schema_version": 1,
        "description": "Point-in-time EOD News, Google Trends, participant OI, three index closes and GOLD/SILVER closes; not backfilled",
        "retention_sessions": 260,
        "records": [],
    })
    records = archive.get("records") if isinstance(archive.get("records"), list) else []
    by_date = {
        x.get("date"): x for x in records
        if isinstance(x, dict) and isinstance(x.get("date"), str)
    }
    previous = by_date.get(date)
    # A complete four-slot Trends snapshot must never be replaced by a partial scan.
    if previous is None or (
        market_snapshot_completeness(record, date)
        >= market_snapshot_completeness(previous, date)
    ):
        by_date[date] = record

    ordered = [by_date[d] for d in sorted(by_date)][-260:]
    archive.update({
        "schema_version": 1,
        "description": "Point-in-time EOD News, Google Trends, participant OI and index close snapshots; not backfilled",
        "retention_sessions": 260,
        "records": ordered,
        "updated_at": result.get("updated"),
    })
    with open(MARKET_SIGNAL_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(clean(archive), f, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    global SKIP_EVENTS
    mcx_updated = refresh_mcx_market_watch_quotes()
    # Public-page fallbacks are only needed during MCX hours when the cached
    # exchange quote is missing/stale. Keep the last valid close on weekends,
    # after hours, and while a recent quote is still within its freshness window.
    if "SILVER" not in mcx_updated:
        if mcx_reference_fallback_needed(load_json(MCX_SILVER_FILE, {})):
            refresh_mcx_silver_reference()
        else:
            print("MCX SILVER fallback skipped: cached quote is fresh or market is closed.")
    if "GOLD" not in mcx_updated:
        if mcx_reference_fallback_needed(load_json(GOLD_MCX_FILE, {})):
            refresh_mcx_gold_reference()
        else:
            print("MCX GOLD fallback skipped: cached quote is fresh or market is closed.")
    if "CRUDEOIL" not in mcx_updated:
        if mcx_reference_fallback_needed(load_json(CRUDE_MCX_FILE, {})):
            refresh_mcx_crude_reference()
        else:
            print("MCX CRUDEOIL fallback skipped: cached quote is fresh or market is closed.")
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    updated = now_utc.isoformat(timespec="minutes").replace("+00:00", "Z")
    events = load_json(EVENTS_FILE, [])
    crowd_events = load_json(CROWD_FILE, [])
    div_events = load_json(DIV_FILE, [])
    sig_state = load_json(SIG_STATE_FILE, {})
    sig_log = load_json(SIG_LOG_FILE, [])
    previous = load_json(DATA_FILE, {})

    # Resolve the exchange calendar before publishing the flag or processing signals.
    # Previously result captured the previous global SKIP_EVENTS value (often False),
    # then updated SKIP_EVENTS afterward; weekend scans were therefore mislabeled open.
    SKIP_EVENTS = market_closed_today()
    result = {"updated": updated, "instruments": {}, "market_closed": SKIP_EVENTS}
    all_returns = {}

    for name, (sym, query) in INDEXES.items():
        process(name, sym, query, "index", events, today_str, result["instruments"],
                div_events, all_returns)

    for name, (sym, query) in STOCKS.items():
        process(name, sym, query, "stock", events, today_str, result["instruments"],
                div_events, all_returns)

    # Add a clearly separate daily reference rate when the intraday FX quote is unavailable.
    # The live price field remains null unless a validated intraday quote exists.
    if "USDINR" in result["instruments"]:
        result["instruments"]["USDINR"].update(fetch_usdinr_reference((previous.get("instruments") or {}).get("USDINR")))

    # सक्रिय वॉचलिस्ट से हटे शेयरों के पुराने Pending रिकॉर्ड भी अगले पूरे
    # कारोबारी दिन के Yahoo daily close से मिलाएँ; नए Dashboard कार्ड न बनाएँ।
    pending_archive_names = {
        e.get("instrument") for e in events
        if e.get("outcome") is None and e.get("instrument") in ARCHIVE_PENDING_SYMBOLS
    }
    for name in sorted(pending_archive_names):
        if name in all_returns:
            continue
        try:
            archived_returns = daily_returns(ARCHIVE_PENDING_SYMBOLS[name])
            all_returns[name] = archived_returns
            update_contrarian(events, name, 0, today_str, archived_returns)
            print(f"Archived Contrarian history checked: {name} ({len(archived_returns)} daily returns)")
        except Exception as exc:
            print(f"Archived Contrarian history unavailable {name}: {str(exc)[:160]}")

    # संकेतों का स्नैपशॉट अंतिम संयुक्त स्कोर बनने के बाद नीचे बनाया जाएगा।

    result["contrarian"] = {
        "events": events[-30:],
        # केवल दिशा साफ़ होने वाले रिकॉर्ड Accuracy में गिने जाते हैं।
        "tracked": len([e for e in events if e.get("outcome") in ("reversed", "continued")]),
        "reversed": len([e for e in events if e.get("outcome") == "reversed"]),
        "continued": len([e for e in events if e.get("outcome") == "continued"]),
        "neutral": len([e for e in events if e.get("outcome") == "neutral"]),
    }

    div_done = [e for e in div_events if e.get("outcome")]
    result["divergence"] = {
        "tracked": len(div_done),
        "sentiment": len([e for e in div_done if e["outcome"] == "sentiment"]),
        "price": len([e for e in div_done if e["outcome"] == "price"]),
        "events": div_events[-12:],
    }

    try:
        slot_now = stock_refresh_slot(now_utc)
        prev_sa = previous.get("stock_analysis") or {}
        expected_keys = set(STOCKS.keys()) | set(OPP_STOCKS.keys())
        if (prev_sa and slot_now and previous.get("stock_analysis_slot") == slot_now
                and set(prev_sa.keys()) == expected_keys):
            # इसी स्लॉट का डेटा पहले से है: कंपनी के आँकड़े दोबारा नहीं माँगते
            result["stock_analysis"] = prev_sa
            result["stock_analysis_slot"] = slot_now
            result["stock_analysis_as_of"] = previous.get("stock_analysis_as_of")
        else:
            result["stock_analysis"] = {}
            sector_universe = {k: (v[0], v[1]) for k, v in STOCKS.items()}
            for k, (sym, _n) in OPP_STOCKS.items():
                sector_universe[k] = (sym, _n)
            for name, (sym, _q) in sector_universe.items():
                price = result["instruments"].get(name, {}).get("price")
                result["stock_analysis"][name] = fetch_stock_fundamentals(sym, price)
            result["stock_analysis_slot"] = slot_now
            result["stock_analysis_as_of"] = updated
        prev_opp = previous.get("opportunity") or {}
        if prev_opp and slot_now and previous.get("opportunity_slot") == slot_now:
            result["opportunity"] = prev_opp
            result["opportunity_slot"] = slot_now
            result["opportunity_as_of"] = previous.get("opportunity_as_of")
        else:
            market_1y = None
            try:
                mh = yf.Ticker("^NSEI").history(period="1y", interval="1d")["Close"].dropna()
                if len(mh) >= 200 and float(mh.iloc[0]) > 0:
                    market_1y = round((float(mh.iloc[-1]) / float(mh.iloc[0]) - 1) * 100, 2)
            except Exception:
                market_1y = None
            raws = {k: opportunity_raw(sym) for k, (sym, _n) in OPP_STOCKS.items()}
            for k, (sym, _n) in OPP_STOCKS.items():
                r = raws[k]
                holding = r.pop("_holding", {}) if isinstance(r, dict) else {}
                if r.get("ok"):
                    r.update(opportunity_extra(sym, market_1y, holding))
            score_opportunities(raws)
            for k, r in raws.items():
                r.pop("growth_factor", None)  # scoring-only field; keep Dashboard growth details unchanged
                r["name"] = OPP_STOCKS[k][1]
            result["opportunity"] = raws
            result["opportunity_slot"] = slot_now
            result["opportunity_as_of"] = updated
    except Exception as e:
        print(f"stock and opportunity analysis skipped: {e}")
        result.setdefault("stock_analysis", {})
        result.setdefault("opportunity", {})
    result["range"] = nifty_range()
    result["levels"] = build_levels(result["range"])

    # संयुक्त इंडेक्स समाचार में समान/मिलते-जुलते शीर्षक को एक ही बार गिनें।
    # हर कार्ड का अपना समाचार और स्कोर अलग रहता है; यह केवल कुल भावना सारांश है।
    index_heads = []
    for index_name in ("NIFTY", "SENSEX", "BANKNIFTY"):
        index_heads.extend(result["instruments"].get(index_name, {}).get("headlines", []))
    unique_index_heads = dedupe_heads(index_heads)
    idx_pos = sum(1 for h in unique_index_heads if h.get("score", 0) > 0)
    idx_neg = sum(1 for h in unique_index_heads if h.get("score", 0) < 0)
    result["headline_split"] = {
        "pos": idx_pos, "neg": idx_neg,
        "unique_headlines": len(unique_index_heads),
        "scope": "NIFTY+SENSEX+BANKNIFTY; duplicate titles removed",
    }

    fii = pick_with_fallback(fetch_fii_dii(), previous.get("fii_dii") or {})
    if fii.get("ok") and not fii.get("stale"):
        fii["as_of_run"] = updated
    result["fii_dii"] = fii
    # NSE participant-wise OI daily EOD data है, live feed नहीं।
    # आज उपलब्ध नवीनतम archive से पहले की तारीख का archive अलग fetch करें,
    # ताकि बार-बार उसी दिन का data.json snapshot होने पर भी daily change न खोए।
    participant_today = fetch_participant_oi()
    prior_snapshot = {}
    if participant_today.get("ok") and participant_today.get("date"):
        try:
            target_prev = dt.date.fromisoformat(participant_today["date"]) - dt.timedelta(days=1)
            prior_snapshot = fetch_participant_oi(base_date=target_prev)
        except (TypeError, ValueError):
            prior_snapshot = {}
    # अगर NSE का पिछला archive अस्थायी रूप से उपलब्ध न हो, तो केवल सही पुराना
    # snapshot fallback में लें; समान/नई तारीख को पिछला दिन न मानें।
    if not prior_snapshot.get("ok"):
        candidates = [
            previous.get("participant_oi_previous_day") or {},
            previous.get("participant_oi") or {},
        ]
        today_date = participant_today.get("date") or ""
        prior_snapshot = next(
            (p for p in candidates if p.get("ok") and p.get("date") and p.get("date") < today_date),
            {}
        )
    # तीसरे बॉक्स की तारीख भी NSE archive से लें, weekday अनुमान से नहीं।
    # इससे NSE holidays के बाद भी तारीख सही रहेगी।
    prior_prior_snapshot = {}
    if prior_snapshot.get("ok") and prior_snapshot.get("date"):
        try:
            target_two_days_ago = dt.date.fromisoformat(prior_snapshot["date"]) - dt.timedelta(days=1)
            prior_prior_snapshot = fetch_participant_oi(base_date=target_two_days_ago)
        except (TypeError, ValueError):
            prior_prior_snapshot = {}
    if not prior_prior_snapshot.get("ok"):
        cached_two_days_ago = previous.get("participant_oi_two_days_ago") or {}
        if (cached_two_days_ago.get("ok") and cached_two_days_ago.get("date")
                and cached_two_days_ago.get("date") < (prior_snapshot.get("date") or "")):
            prior_prior_snapshot = cached_two_days_ago
    participant_today["two_days_ago_date"] = prior_prior_snapshot.get("date") if prior_prior_snapshot.get("ok") else None

    result["participant_oi"] = participant_today
    result["participant_oi_previous_day"] = prior_snapshot
    result["participant_oi_two_days_ago"] = prior_prior_snapshot
    result["participant_oi"]["changes"] = participant_changes(
        participant_today, prior_snapshot)
    participant_oi_history = update_participant_oi_history(
        participant_today, prior_snapshot, prior_prior_snapshot)
    adj, rinfo = retail_adjust(result["participant_oi"])
    for _n in ("NIFTY", "SENSEX", "BANKNIFTY"):
        _d = result["instruments"].get(_n)
        if _d and rinfo is not None:
            _d["headline_score"] = _d["score"]
            _d["retail_adj"] = adj
    result["retail_mood"] = rinfo

    market_news = pick_with_fallback(fetch_market_news(), previous.get("market_news") or {})
    if market_news.get("ok") and not market_news.get("stale"):
        market_news["as_of"] = updated
    result["market_news"] = market_news

    # Google Trends केवल workflow के चार तय स्लॉट पर चलाएँ: 09:15, 11:00, 13:00 और 19:00 IST.
    # बाकी हर 30-मिनट वाले PDMP रन में पिछली रीडिंग को दोबारा fetch न करें।
    previous_trends = previous.get("trends") or {}
    previous_crowd_terms = previous_trends.get("crowd_terms") or []
    previous_trends_all_zero = (
        not previous_crowd_terms
        or all(float(p.get("now", 0) or 0) == 0 and float(p.get("avg", 0) or 0) == 0
               for p in previous_crowd_terms)
        or (float(previous_trends.get("bull_sum_pct", 0) or 0) == 0
            and float(previous_trends.get("bear_sum_pct", 0) or 0) == 0)
    )
    previous_trends_has_scores = all(
        previous_trends.get(k) is not None
        for k in ("bull_score_pct", "bear_score_pct", "neutral_score_pct")
    )
    component_shadow_scan = os.getenv("COMPONENT_SHADOW_SCAN", "false").lower() == "true"
    trends_scan = (
        os.getenv("TRENDS_SCAN", "false").lower() == "true"
        and not component_shadow_scan
    )

    if trends_scan:
        # हर निर्धारित स्लॉट पर नया Google Trends अनुरोध करें; पुराने सफल डेटा से स्लॉट पूरा न मानें।
        fresh_trends = fetch_trends()
        if fresh_trends.get("ok"):
            trends = fresh_trends
            trends["stale"] = False
            trends["as_of"] = fresh_trends.get("source_data_time")
            trends["cached"] = False
            trends["refresh_policy_hours"] = None
        else:
            trends = {
                "ok": False, "stale": False, "cached": False,
                "error": fresh_trends.get("error", "Google Trends की नई reading उपलब्ध नहीं")
            }
    elif previous_trends.get("ok") and previous_trends_has_scores and not previous_trends_all_zero:
        if trends_within_freshness(previous_trends, now_utc):
            trends = dict(previous_trends)
            trends["cached"] = True
            trends["stale"] = False
            trends["refresh_policy_hours"] = None
        else:
            trends = {
                "ok": False, "stale": True, "cached": False,
                "error": f"आख़िरी सफल Google Trends reading {TRENDS_MAX_AGE_MINUTES} मिनट से पुरानी है; पुराना मूड छिपाया गया"
            }
    else:
        trends = {
            "ok": False, "stale": False, "cached": False,
            "error": "नई Google Trends reading उपलब्ध नहीं; अगला तय स्कैन आने पर जाँच होगी"
        }
    # चारों निर्धारित IST स्लॉट का दैनिक हिसाब; किसी एक स्लॉट की विफलता पर Crowd प्रतिशत नहीं दिखेंगे।
    slot_id = os.getenv("TRENDS_SLOT", "").strip()
    slot_labels = {"0915": "09:15", "1100": "11:00", "1300": "13:00", "1900": "19:00"}
    slot_date = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date().isoformat()
    prior_slot_state = previous_trends.get("daily_slots") or {}
    if prior_slot_state.get("date") != slot_date:
        slot_state = {"date": slot_date, "slots": {}}
    else:
        slot_state = {"date": slot_date, "slots": dict(prior_slot_state.get("slots") or {})}

    # पुराने दिन के failed/pending slot को आज का परिणाम न मानें।
    ist_tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
    def _parse_slot_time(value):
        try:
            stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return stamp.replace(tzinfo=dt.timezone.utc) if stamp.tzinfo is None else stamp
        except (TypeError, ValueError):
            return None

    for _key, _record in list(slot_state["slots"].items()):
        if not isinstance(_record, dict):
            slot_state["slots"].pop(_key, None)
            continue
        _time_text = (_record.get("source_data_time") if _record.get("status") == "success"
                      else _record.get("checked_at"))
        _stamp = _parse_slot_time(_time_text) if _time_text else None
        if _stamp is None or _stamp.astimezone(ist_tz).date().isoformat() != slot_date:
            slot_state["slots"].pop(_key, None)
            continue
        if _record.get("status") == "failed" and _key in slot_labels:
            _local_stamp = _stamp.astimezone(ist_tz)
            _expected = dt.datetime.combine(
                _local_stamp.date(), dt.time.fromisoformat(slot_labels[_key]), tzinfo=ist_tz
            )
            if abs((_local_stamp - _expected).total_seconds()) > 3 * 60 * 60:
                slot_state["slots"].pop(_key, None)
                continue
        if _record.get("status") == "success" and _key in slot_labels:
            _local_stamp = _stamp.astimezone(ist_tz)
            _expected = dt.datetime.combine(
                _local_stamp.date(), dt.time.fromisoformat(slot_labels[_key]), tzinfo=ist_tz
            )
            # आख़िरी observation स्लॉट से 6 घंटे से ज़्यादा पुराना या
            # स्लॉट के 15 मिनट से ज़्यादा आगे का हो तो success न गिनें।
            observation_lag = (_expected - _local_stamp).total_seconds() / 60
            if observation_lag < -15 or observation_lag > TRENDS_MAX_AGE_MINUTES:
                slot_state["slots"].pop(_key, None)
                continue

    if trends_scan and slot_id in slot_labels:
        if trends.get("ok") and trends.get("source_data_time") and all(
            isinstance(trends.get(k), (int, float))
            for k in ("bull_score_pct", "bear_score_pct", "neutral_score_pct")
        ):
            slot_state["slots"][slot_id] = {
                "time": slot_labels[slot_id], "status": "success",
                "source_data_time": trends.get("source_data_time"),
                "basis": trends.get("today_basis"),
                "timeframe": trends.get("source_timeframe"),
                "bull_pct": trends.get("bull_score_pct"),
                "bear_pct": trends.get("bear_score_pct"),
                "neutral_pct": trends.get("neutral_score_pct"),
                "crowd_pct": trends.get("crowd_bull_pct"),
                "today_bull_pct": trends.get("today_bull_pct"),
                "today_label": trends.get("today_label"),
                "bull_sum_pct": trends.get("bull_sum_pct"),
                "bear_sum_pct": trends.get("bear_sum_pct"),
                "crowd_terms": trends.get("crowd_terms") or [],
            }
        else:
            slot_state["slots"][slot_id] = {
                "time": slot_labels[slot_id], "status": "failed",
                "checked_at": now_utc.isoformat(),
                "error": trends.get("error", "इस स्लॉट में वैध Google Trends डेटा नहीं मिला"),
            }

    required_slots = ("0915", "1100", "1300", "1900")
    slot_records = slot_state["slots"]
    all_slots_ok = all(
        isinstance(slot_records.get(key), dict) and slot_records[key].get("status") == "success"
        for key in required_slots
    )
    # अगर इस रन में नई reading नहीं मिली, तो आज के slots में सबसे नई
    # सफल reading को 6 घंटे तक दिखाएँ; पुरानी/दूसरे दिन की reading नहीं।
    if not trends.get("ok"):
        _valid_slots = []
        for _key, _record in slot_state["slots"].items():
            if not isinstance(_record, dict) or _record.get("status") != "success":
                continue
            _stamp = _parse_slot_time(_record.get("source_data_time"))
            if _stamp is None:
                continue
            _age = (now_utc - _stamp.astimezone(dt.timezone.utc)).total_seconds() / 60
            if -5 <= _age <= TRENDS_MAX_AGE_MINUTES:
                _valid_slots.append((_stamp, _key, _record))
        if _valid_slots:
            _stamp, _key, _record = max(_valid_slots, key=lambda item: item[0])
            _crowd = _record.get("crowd_pct")
            trends = {
                "ok": True, "stale": False, "cached": True,
                "source_data_time": _stamp.isoformat(),
                "as_of": _stamp.isoformat(),
                "source_timeframe": _record.get("timeframe"),
                "today_basis": _record.get("basis"),
                "today_bull_pct": _record.get("today_bull_pct", _crowd),
                "crowd_bull_pct": _crowd,
                "bull_score_pct": _record.get("bull_pct"),
                "bear_score_pct": _record.get("bear_pct"),
                "neutral_score_pct": _record.get("neutral_pct"),
                "bull_sum_pct": _record.get("bull_sum_pct"),
                "bear_sum_pct": _record.get("bear_sum_pct"),
                "crowd_terms": _record.get("crowd_terms") or [],
                "today_date_ist": slot_date,
                "today_label": _record.get("today_label") or "पिछले 24 घंटे की Google Trends खोज-रुचि",
                "daily_label": "दैनिक औसत अधूरा — नवीनतम सफल रीडिंग",
                "refresh_policy_hours": None,
            }

    trends["daily_slots"] = slot_state
    trends["daily_complete"] = all_slots_ok
    trends["daily_slot_summary"] = [
        {"id": key, "time": slot_labels[key],
         "status": slot_records.get(key, {}).get("status", "pending")}
        for key in required_slots
    ]
    if all_slots_ok and trends_scan and slot_id in slot_labels:
        for field, output_key in (
            ("bull_pct", "bull_score_pct"),
            ("bear_pct", "bear_score_pct"),
            ("neutral_pct", "neutral_score_pct"),
        ):
            trends[output_key] = round(
                sum(float(slot_records[key][field]) for key in required_slots) / 4, 1
            )
        trends["crowd_bull_pct"] = round(
            sum(float(slot_records[key].get("crowd_pct") or 0) for key in required_slots) / 4, 1
        )
        trends["ok"] = True
        trends["stale"] = False
        trends["daily_label"] = "चारों निर्धारित स्लॉट का औसत"
        trends["as_of"] = slot_records["1900"].get("source_data_time")
    elif not all_slots_ok:
        # निर्धारित स्लॉट का दैनिक औसत अधूरा हो तो भी इसी रन की ताज़ा,
        # timestamp-validated reading को Crowd Score से न हटाएँ।
        # Manual verification runs (बिना slot_id) भी अपना ताज़ा score दिखाएँ।
        if not trends.get("ok"):
            trends["stale"] = False
        trends["daily_label"] = "दैनिक औसत अधूरा — नवीनतम सफल रीडिंग"
        failed = [slot_labels[key] for key in required_slots
                  if slot_records.get(key, {}).get("status") == "failed"]
        pending = [slot_labels[key] for key in required_slots
                   if slot_records.get(key, {}).get("status") not in ("success", "failed")]
        details = []
        if failed:
            details.append("असफल: " + ", ".join(failed))
        if pending:
            details.append("बाकी: " + ", ".join(pending))
        trends["daily_status_note"] = "दैनिक औसत अधूरा (" + "; ".join(details) + ")"

    result["trends"] = trends
    # Refresh asset-specific Search on scheduled slots and explicit manual scans.
    # Manual scans use one five-seed batch plus one CRUDEOIL batch; they do not
    # launch the six extra directional phrase requests, keeping 429 risk bounded.
    # If primary Crowd Trends failed, do not add more Google requests in that run.
    _previous_asset_instruments = previous.get("instruments") or {}
    _fresh_asset_search = None
    if component_shadow_scan:
        _fresh_asset_search = fetch_asset_trends_shadow()
    elif trends_scan and slot_id in {"0915", "1100", "1300", "1900"}:
        if trends.get("ok"):
            run_phrase_diagnostics = should_run_asset_directional_diagnostics(slot_id)
            print(
                "ASSET_TRENDS_REFRESH: scheduled five asset seeds + CRUDEOIL; "
                + ("daily six-asset phrase diagnostics enabled" if run_phrase_diagnostics
                   else "extra phrase diagnostics deferred to 19:00 IST to protect quota")
            )
            _fresh_asset_search = fetch_asset_trends_shadow(
                include_directional_diagnostics=run_phrase_diagnostics,
                include_crude=True,
            )
        elif is_google_trends_rate_limited(trends.get("error")):
            print("ASSET_TRENDS_REFRESH: Google Trends rate limit detected; all secondary requests skipped")
        else:
            print("ASSET_TRENDS_REFRESH: primary Crowd Trends unavailable; running only the independent CRUDEOIL batch")
            _fresh_asset_search = fetch_crude_trends_shadow()
    elif should_refresh_asset_search(trends_scan, os.getenv("GITHUB_EVENT_NAME", "")):
        if trends.get("ok"):
            print("ASSET_TRENDS_REFRESH: manual/controlled validation scan; refreshing five asset seeds + CRUDEOIL (phrase diagnostics skipped to limit requests)")
            _fresh_asset_search = fetch_asset_trends_shadow(include_crude=True)
        else:
            print("ASSET_TRENDS_REFRESH: manual primary Crowd Trends failed; extra asset requests skipped to protect Google Trends quota")
    attach_asset_search_snapshots(
        result["instruments"], _previous_asset_instruments, now_utc,
        fresh_results=_fresh_asset_search,
    )

    # Shadow-only component breakdown; does not change the published instrument score.
    result["component_score_method"] = build_asset_component_breakdowns(
        result["instruments"], updated, now_utc, participant_today,
        result["participant_oi"].get("changes"),
    )

    # अंतिम इंडेक्स स्कोर: केवल सत्यापित News और Google Trends; दोनों उपलब्ध हों तो 50/50.
    # NSE participant OI और CLIENT adjustment अलग diagnostic हैं, final score में शामिल नहीं।
    fresh_trends = bool(trends.get("ok") and not trends.get("stale"))
    crowd_bull = trends.get("crowd_bull_pct") if fresh_trends else None
    crowd_total_bull = trends.get("bull_score_pct") if fresh_trends else None
    crowd_bear = trends.get("bear_score_pct") if fresh_trends else None
    crowd_neutral = trends.get("neutral_score_pct") if fresh_trends else None
    crowd_valid = (
        trends.get("today_basis") in {"now_1d_anchor_relative", "now_1d_related_queries"}
        and all(
            isinstance(v, (int, float)) and math.isfinite(float(v)) and 0 <= v <= 100
            for v in (crowd_total_bull, crowd_bear, crowd_neutral)
        )
        and abs(float(crowd_total_bull) + float(crowd_bear) + float(crowd_neutral) - 100) <= 2
    )
    crowd_component = (
        three_way_crowd_component(crowd_total_bull, crowd_bear, crowd_neutral)
        if crowd_valid else None
    )
    retail_valid = isinstance(rinfo, dict) and isinstance(adj, (int, float))
    crowd_score_valid = bool(crowd_valid and crowd_component is not None)
    # Shadow calculation only; unvalidated CLIENT OI is retained as a separate diagnostic.
    # Neutral-only/weak directional Trends may be descriptive but cannot enter a numeric crowd score.
    experimental_news = experimental_news_scores(result["instruments"], now_utc=now_utc)
    for _n, _exp in experimental_news.items():
        _d = result["instruments"].get(_n)
        if not _d:
            continue
        _exp_news = _exp["news_score"]
        _exp_combined, _exp_mode_base, _ = validated_news_crowd_score(
            _exp_news, crowd_component, crowd_score_valid
        )
        _exp_mode = (
            "shadow_news24h_dedup_crowd"
            if _exp_mode_base == "news_crowd"
            else "shadow_news24h_dedup_only"
        )
        _d["experimental_news_score"] = round(_exp_news, 1)
        _d["experimental_score"] = _exp_combined
        _d["experimental_score_mode"] = _exp_mode
        _d["experimental_headline_count"] = _exp["headline_count"]
        _d["experimental_excluded_old_or_unknown"] = _exp["excluded_old_or_unknown"]
        _d["experimental_excluded_cross_index_duplicates"] = _exp["excluded_cross_index_duplicates"]
    for _n in ("NIFTY", "SENSEX", "BANKNIFTY"):
        _d = result["instruments"].get(_n)
        if not _d:
            continue
        news_component = max(-10.0, min(10.0, float(_d.get("headline_score", _d.get("score", 0))) * 2))
        _score, _mode, _normalized_weights = validated_news_crowd_score(
            news_component, crowd_component, crowd_score_valid
        )
        _d["score"] = _score
        _d["score_mode"] = _mode
    result["index_score_method"] = {
        "mode": "news_crowd" if crowd_score_valid else "news_only",
        "weights": {"news": 50, "crowd": 50},
        "normalized_weights_pct": (
            {"news": 50.0, "crowd": 50.0}
            if crowd_score_valid else {"news": 100.0}
        ),
        "crowd_included": bool(crowd_score_valid),
        "crowd_source_valid": bool(crowd_valid),
        "crowd_basis": "directional_bull_bear_ratio; (BULLISH%-BEARISH%)/(BULLISH%+BEARISH%) maps to -10..+10; NEUTRAL information interest is displayed separately",
        "crowd_bull_pct": crowd_bull if fresh_trends else None,
        "crowd_net_score": crowd_component if crowd_score_valid else None,
        "client_included": False,
        "client_diagnostic_only": True,
        "client_diagnostic_available": bool(retail_valid),
        "client_adjustment_diagnostic": adj if retail_valid else None,
        "client_excluded_reason": "NSE participant OI has not demonstrated a validated out-of-sample predictive edge; it remains diagnostic only.",
    }

    # अब signal history भी इसी अंतिम स्कोर से बनेगी।
    update_signals(result["instruments"], sig_state, sig_log, updated)
    result["signals"] = {
        "state": signal_summary(sig_state),
        "events": sig_log[-15:],
        "watch": list(SIGNAL_WATCH.keys()),
    }

    crowd_mood, _crowd_label = three_way_crowd_mood(crowd_total_bull, crowd_bear, crowd_neutral) if crowd_valid else ("NO DATA", "पर्याप्त खोज डेटा नहीं")
    crowd_pct = crowd_bull if crowd_valid and crowd_mood in {"BULLISH", "BEARISH"} and crowd_bull is not None and (crowd_bull >= CROWD_EXTREME or crowd_bull <= CROWD_LOW) else None
    nifty_ret = all_returns.get("NIFTY") or {}
    update_crowd(crowd_events, crowd_pct, today_str, nifty_ret)
    done = [e for e in crowd_events if e.get("outcome")]
    result["crowd_stats"] = {
        "tracked": len(done),
        "trap": len([e for e in done if e["outcome"] == "trap"]),
        "followed": len([e for e in done if e["outcome"] == "followed"]),
        "events": crowd_events[-10:],
    }

    # Archive after crowd_stats exists so pre-archive daily events can be backfilled.
    # This reuses existing data and makes no additional provider requests.
    crowd_mood_archive = update_crowd_mood_archive(
        load_json("crowd_mood_history.json", {}), result, updated
    )
    with open("crowd_mood_history.json", "w", encoding="utf-8") as f:
        json.dump(crowd_mood_archive, f, ensure_ascii=False, indent=2, allow_nan=False)

    result = clean(result)
    update_market_signal_history(result)
    events = clean(events)
    crowd_events = clean(crowd_events)
    div_events = clean(div_events)
    sig_state = clean(sig_state)
    sig_log = clean(sig_log)

    with open(PARTICIPANT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(clean(participant_oi_history), f, ensure_ascii=False, indent=2, allow_nan=False)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(CROWD_FILE, "w", encoding="utf-8") as f:
        json.dump(crowd_events, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(DIV_FILE, "w", encoding="utf-8") as f:
        json.dump(div_events, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(SIG_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sig_state, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(SIG_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(sig_log, f, ensure_ascii=False, indent=2, allow_nan=False)

    write_header = not os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["time_utc", "instrument", "change_pct", "score"])
        for name, d in result["instruments"].items():
            w.writerow([result["updated"], name, d["change_pct"], d["score"]])


if __name__ == "__main__":
    main()
