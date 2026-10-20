import json, csv, os, re, time, math, datetime as dt
from urllib.parse import quote_plus
import feedparser, yfinance as yf
import requests

# ---- इंडेक्स और कमोडिटी ----
# (yfinance सिंबल, न्यूज़ खोज शब्द)
INDEXES = {
    "NIFTY": ("^NSEI", "Nifty 50 stock market"),
    "SENSEX": ("^BSESN", "Sensex stock market"),
    "BANKNIFTY": ("^NSEBANK", "Bank Nifty"),
    "GOLD": ("GC=F", "gold price"),
    "SILVER": ("SI=F", "silver price"),
    "CRUDEOIL": ("CL=F", "crude oil price"),
    "BITCOIN": ("BTC-USD", "bitcoin price"),
    "NASDAQ": ("^IXIC", "Nasdaq stock market"),
    "DJI": ("^DJI", "Dow Jones stock market"),
}

# ---- स्टॉक वॉचलिस्ट ----
# अपने स्टॉक यहाँ जोड़ें या हटाएँ। NSE स्टॉक के लिए सिंबल के आगे ".NS" लगता है।
STOCKS = {
    "RELIANCE": ("RELIANCE.NS", "Reliance Industries share"),
    "HDFCBANK": ("HDFCBANK.NS", "HDFC Bank share"),
    "TATAMOTORS": ("TATAMOTORS.NS", "Tata Motors share"),
    "HINDALCO": ("HINDALCO.NS", "Hindalco share"),
    "ADANIPORTS": ("ADANIPORTS.NS", "Adani Ports share"),
    "COALINDIA": ("COALINDIA.NS", "Coal India share"),
    "EICHERMOT": ("EICHERMOT.NS", "Eicher Motors share"),
    "APOLLOHOSP": ("APOLLOHOSP.NS", "Apollo Hospitals share"),
    "SBIN": ("SBIN.NS", "SBI share"),
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

# शब्द-सूची: वज़न 1 या 2। जितनी बढ़ाएँगे, स्कोर उतना बेहतर होगा।
POS = {"rally": 2, "surge": 2, "record high": 2, "bullish": 2, "gain": 1,
       "jump": 1, "rise": 1, "climb": 1, "rebound": 1, "higher": 1, "profit": 1,
       "beats": 1, "upgrade": 2, "buy": 1}
NEG = {"crash": 2, "slump": 2, "bearish": 2, "plunge": 2, "fall": 1,
       "drag": 1, "loss": 1, "drop": 1, "decline": 1, "weigh": 1,
       "lower": 1, "losses": 1, "sell-off": 2, "selloff": 2, "downgrade": 2,
       "misses": 1, "sell": 1}

# Google Trends: डर-संबंधी खोजें (बियरिश सोच) और बुलिश खोजें (एक ही अनुरोध में, ताकि पैमाना एक हो)
FEAR_TERMS = ["nifty crash", "stock market crash", "sensex fall"]
BULL_TERMS = ["nifty rally", "nifty buy"]
TRENDS_RETRIES = 2

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

CONTRARIAN_LIMIT = 6.0
DATA_FILE = "data.json"
EVENTS_FILE = "contrarian.json"
CROWD_FILE = "crowd_events.json"
HISTORY_FILE = "history.csv"


def clean(obj):
    """NaN या infinity को 0 से बदलता है, ताकि JSON फ़ाइल सही बने।"""
    if isinstance(obj, float):
        return 0.0 if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def headline_score(text):
    t = text.lower()
    return sum(v for k, v in POS.items() if k in t) - sum(v for k, v in NEG.items() if k in t)


def fetch_news(query):
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(url)
    items = []
    now = time.time()
    for e in feed.entries[:15]:
        age_h = None
        if getattr(e, "published_parsed", None):
            age_h = round((now - time.mktime(e.published_parsed)) / 3600, 1)
        title = e.title
        source = ""
        if " - " in title:
            title, source = title.rsplit(" - ", 1)
        items.append({"title": title, "source": source,
                      "link": getattr(e, "link", "") or "",
                      "score": headline_score(title), "age_h": age_h})
    items.sort(key=lambda x: (x["age_h"] is None, x["age_h"] or 0))
    return items


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def daily_returns(sym):
    """तारीख -> उस दिन का % बदलाव।
    आज का अधूरा बार छोड़ा जाता है, ताकि सुबह के रन में गलत बदलाव न आए।"""
    closes = yf.Ticker(sym).history(period="1mo", interval="1d")["Close"]
    today_utc = dt.datetime.now(dt.timezone.utc).date()
    keep = [d.date() < today_utc for d in closes.index]
    closes = closes[keep]
    out = {}
    for i in range(1, len(closes)):
        prev, cur = float(closes.iloc[i - 1]), float(closes.iloc[i])
        if math.isnan(prev) or math.isnan(cur) or prev == 0:
            continue
        d = closes.index[i].strftime("%Y-%m-%d")
        out[d] = round((cur / prev - 1) * 100, 2)
    return out


def update_contrarian(events, name, score, today_str, returns):
    """±6 से ज़्यादा स्कोर दर्ज करें और पुराने इवेंट का नतीजा भरें"""
    key = f"{today_str}|{name}"
    if abs(score) >= CONTRARIAN_LIMIT and not any(e["key"] == key for e in events):
        events.append({"key": key, "date": today_str, "instrument": name,
                       "score": score, "outcome": None, "next_change": None})

    for e in events:
        if e["outcome"] is not None or e["instrument"] != name:
            continue
        later = sorted(d for d in returns if d > e["date"])
        if later:
            nxt = returns[later[0]]
            e["next_change"] = nxt
            same_sign = (nxt >= 0) == (e["score"] >= 0)
            e["outcome"] = "continued" if same_sign else "reversed"


def process(name, sym, query, kind, events, today_str, instruments):
    returns = {}
    change = 0.0
    try:
        returns = daily_returns(sym)
        if returns:
            change = returns[max(returns)]
    except Exception as e:
        print(f"price error {name}: {e}")

    try:
        heads = fetch_news(query)
    except Exception as e:
        print(f"news error {name}: {e}")
        heads = []

    score = round(sum(h["score"] for h in heads) / len(heads) * 5, 1) if heads else 0.0

    instruments[name] = {
        "type": kind,
        "change_pct": change,
        "score": score,
        "headlines": heads[:8],
        # पूरी खबरों का बुलिश/बियरिश बँटवारा (सिर्फ़ 8 नहीं)
        "pos_n": sum(1 for h in heads if h["score"] > 0),
        "neg_n": sum(1 for h in heads if h["score"] < 0),
    }
    update_contrarian(events, name, score, today_str, returns)


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
    """बाज़ार पर असर डालने वाली ताज़ा खबरें, कई विषयों से।
    कोई खबर बाज़ार से न जुड़ी हो तो छोड़ दी जाती है। दोहराव भी हटाया जाता है।"""
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
    या हमारी वॉचलिस्ट के किसी स्टॉक से।
    लौटता है: (संबंधित है या नहीं, स्टॉक का नाम या None)।"""
    q = query.lower()
    for stock, aliases in STOCK_ALIASES.items():
        if any(a in q for a in aliases):
            return True, stock
    if "nifty" in q or "sensex" in q:
        return True, None
    return False, None


def crowd_label(pct):
    if pct >= CROWD_EXTREME:
        return "ज़्यादातर बुलिश सोच"
    if pct <= CROWD_LOW:
        return "ज़्यादातर बियरिश सोच"
    return "सोच बँटी हुई"


def _trends_once():
    """एक बार Google Trends से डेटा लेता है। 429 या कोई भी एरर ऊपर फेंकता है।
    सारे नतीजे अंकों (points) में हैं, प्रतिशत में नहीं।
    एक ही अनुरोध में बियरिश और बुलिश खोजें हैं, इसलिए उनका पैमाना एक ही रहता है।"""
    from pytrends.request import TrendReq

    py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
    keywords = FEAR_TERMS + BULL_TERMS
    py.build_payload(keywords, timeframe="now 7-d", geo="IN")
    df = py.interest_over_time()
    if df is None or df.empty:
        raise ValueError("Google से खाली डेटा मिला")
    df = df[keywords].fillna(0)

    if float(df.values.max()) == 0:
        raise ValueError("सभी खोजों का डेटा शून्य है")

    base = float(df[FEAR_TERMS].mean(axis=1).mean())
    recent = float(df[FEAR_TERMS].tail(24).mean(axis=1).mean())
    fear_pts = round(recent - base, 1)

    per_term = []
    for t in FEAR_TERMS:
        b = float(df[t].mean())
        r = float(df[t].tail(24).mean())
        per_term.append({"term": t, "pts": round(r - b, 1), "now": round(r, 1), "avg": round(b, 1)})

    # भीड़ की सोच: पिछले 24 घंटे में बुलिश खोजें बनाम बियरिश खोजें
    bull_recent = float(df[BULL_TERMS].tail(24).mean(axis=1).mean())
    total = bull_recent + recent
    crowd_bull_pct = round(bull_recent / total * 100) if total > 0 else 50
    crowd_terms = [{"term": t, "now": round(float(df[t].tail(24).mean()), 1),
                    "avg": round(float(df[t].mean()), 1)} for t in BULL_TERMS]

    # उभरती खोजें: सिर्फ़ Nifty, Sensex या वॉचलिस्ट से जुड़ी
    spikes = []
    try:
        time.sleep(5)
        py.build_payload(["nifty", "sensex"], timeframe="now 7-d", geo="IN")
        rq = py.related_queries()
        seen = set()
        for kw in ("nifty", "sensex"):
            r = rq.get(kw, {}).get("rising")
            if r is None or r.empty:
                continue
            for _, row in r.head(15).iterrows():
                q = str(row["query"])
                if q in seen:
                    continue
                ok, stock = match_relevant(q)
                if not ok:
                    continue
                seen.add(q)
                spikes.append({"query": q, "value": str(row["value"]), "stock": stock})
    except Exception as e:
        print(f"rising queries skipped: {e}")

    return {"ok": True, "unit": "points", "fear_vs_avg": fear_pts,
            "per_term": per_term, "spikes": spikes[:10],
            "crowd_bull_pct": crowd_bull_pct, "crowd_label": crowd_label(crowd_bull_pct),
            "crowd_terms": crowd_terms}


def fetch_trends():
    """Google 429 देने पर थोड़ी देर रुककर दोबारा कोशिश करता है।
    सब फेल हो तो {"ok": False, "error": ...} लौटता है।"""
    try:
        import pytrends  # noqa: F401
    except Exception as e:
        return {"ok": False, "error": f"pytrends नहीं मिला: {e}"}

    last_err = ""
    for attempt in range(TRENDS_RETRIES):
        try:
            return _trends_once()
        except Exception as e:
            last_err = str(e)
            print(f"trends attempt {attempt + 1} failed: {last_err}")
            if attempt < TRENDS_RETRIES - 1:
                time.sleep(20)
    return {"ok": False, "error": f"Google Trends फेल: {last_err}"}


def update_crowd(events, crowd_pct, today_str, nifty_ret):
    """भीड़ एकतरफ़ा हो तो उस दिन दर्ज करें। अगले सत्र की Nifty चाल से नतीजा भरें।
    'trap' = भीड़ की दिशा उल्टी गई। 'followed' = भीड़ की दिशा सही निकली।
    यह इतिहास का मिलान है, भविष्य की गारंटी नहीं।"""
    if crowd_pct is not None and (crowd_pct >= CROWD_EXTREME or crowd_pct <= CROWD_LOW):
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


def main():
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    updated = now_utc.isoformat(timespec="minutes").replace("+00:00", "Z")
    events = load_json(EVENTS_FILE, [])
    crowd_events = load_json(CROWD_FILE, [])
    previous = load_json(DATA_FILE, {})

    result = {"updated": updated, "instruments": {}}

    for name, (sym, query) in INDEXES.items():
        process(name, sym, query, "index", events, today_str, result["instruments"])

    for name, (sym, query) in STOCKS.items():
        process(name, sym, query, "stock", events, today_str, result["instruments"])

    result["contrarian"] = {
        "events": events[-30:],
        "tracked": len([e for e in events if e["outcome"]]),
        "reversed": len([e for e in events if e["outcome"] == "reversed"]),
        "continued": len([e for e in events if e["outcome"] == "continued"]),
    }

    result["range"] = nifty_range()
    result["levels"] = build_levels(result["range"])

    # शीर्षक का बुलिश/बियरिश बँटवारा (NIFTY और SENSEX की सभी खबरें)
    idx_pos = sum(result["instruments"][k].get("pos_n", 0) for k in ("NIFTY", "SENSEX"))
    idx_neg = sum(result["instruments"][k].get("neg_n", 0) for k in ("NIFTY", "SENSEX"))
    result["headline_split"] = {"pos": idx_pos, "neg": idx_neg}

    fii = pick_with_fallback(fetch_fii_dii(), previous.get("fii_dii") or {})
    if fii.get("ok") and not fii.get("stale"):
        fii["as_of_run"] = updated
    result["fii_dii"] = fii

    market_news = pick_with_fallback(fetch_market_news(), previous.get("market_news") or {})
    if market_news.get("ok") and not market_news.get("stale"):
        market_news["as_of"] = updated
    result["market_news"] = market_news

    trends = pick_with_fallback(fetch_trends(), previous.get("trends") or {})
    if trends.get("ok") and not trends.get("stale"):
        trends["as_of"] = updated
    result["trends"] = trends

    # भीड़ का इतिहास: सिर्फ़ ताज़ा ट्रेंड्स डेटा से दर्ज होता है, पुराने से नहीं
    fresh_trends = trends.get("ok") and not trends.get("stale")
    crowd_pct = trends.get("crowd_bull_pct") if fresh_trends else None
    nifty_ret = {}
    try:
        nifty_ret = daily_returns("^NSEI")
    except Exception as e:
        print(f"crowd nifty returns error: {e}")
    update_crowd(crowd_events, crowd_pct, today_str, nifty_ret)
    done = [e for e in crowd_events if e.get("outcome")]
    result["crowd_stats"] = {
        "tracked": len(done),
        "trap": len([e for e in done if e["outcome"] == "trap"]),
        "followed": len([e for e in done if e["outcome"] == "followed"]),
        "events": crowd_events[-10:],
    }

    result = clean(result)
    events = clean(events)
    crowd_events = clean(crowd_events)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(CROWD_FILE, "w", encoding="utf-8") as f:
        json.dump(crowd_events, f, ensure_ascii=False, indent=2, allow_nan=False)

    write_header = not os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["time_utc", "instrument", "change_pct", "score"])
        for name, d in result["instruments"].items():
            w.writerow([result["updated"], name, d["change_pct"], d["score"]])


if __name__ == "__main__":
    main()
