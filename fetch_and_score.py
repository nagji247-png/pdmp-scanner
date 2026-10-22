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
BULL_TERMS = [
    "nifty target", "sensex rally", "nifty rise", "sensex up",
    "nifty high", "sensex record", "nifty buy", "sensex bull",
    "nifty bullish", "sensex jump", "nifty surge", "sensex gain",
    "nifty टारगेट", "sensex रैली", "nifty तेज़ी", "sensex उछाल",
    "nifty ऊपर", "sensex बुलिश", "nifty खरीद",
]
BEAR_TERMS = [
    "nifty fall", "sensex crash", "nifty down", "sensex drop",
    "nifty low", "sensex sell", "nifty bear", "sensex bearish",
    "nifty slump", "sensex decline", "nifty sell-off",
    "sensex गिरावट", "nifty गिरेगा", "sensex नीचे",
    "nifty मंदी", "sensex बेयरिश", "nifty बिकवाली",
]
TERM_CHUNK = 4

# भीड़ का मूड तभी दिखेगा जब दोनों तरफ़ के शब्दों में कम से कम इतनी खोज हो।
# यह मान "निफ़्टी" की खोज के प्रतिशत में है। शुरुआती मान है, डैशबोर्ड पर असली अनुपात दिखता है ताकि बदला जा सके।
MIN_SIDE_PCT = 1.0
TRENDS_RETRIES = 2  # केवल गैर-429 त्रुटियों पर दोबारा प्रयास

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
# NSE की आधिकारिक छुट्टियाँ "YYYY-MM-DD" में यहाँ भरें (Google/आधिकारिक सूची से)
NSE_HOLIDAYS = set()
DATA_FILE = "data.json"
EVENTS_FILE = "contrarian.json"
CROWD_FILE = "crowd_events.json"
DIV_FILE = "divergence_events.json"
SIG_STATE_FILE = "signal_state.json"
SIG_LOG_FILE = "signal_log.json"
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
    if abs(score) >= CONTRARIAN_LIMIT and not SKIP_EVENTS and not any(e["key"] == key for e in events):
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


def update_divergence(events, name, score, change, today_str, returns):
    """⚡ संकेत दर्ज करें: स्कोर और कीमत की दिशा अलग हो।
    नतीजा उसी दिन के सत्र से भरता है जिस दिन संकेत बना।
    'sentiment' = खबर की दिशा में चाल, 'price' = कीमत की दिशा में चाल।
    यह इतिहास का मिलान है, भविष्य की गारंटी नहीं।"""
    diverging = (abs(score) >= DIV_SCORE_MIN and abs(change) >= DIV_CHANGE_MIN
                 and (score > 0) != (change > 0) and not SKIP_EVENTS)
    key = f"{today_str}|{name}|div"
    if diverging and not any(e["key"] == key for e in events):
        events.append({
            "key": key, "date": today_str, "instrument": name,
            "score": score, "price_change": change,
            "sentiment_up": score > 0, "outcome": None, "next_change": None,
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


def process(name, sym, query, kind, events, today_str, instruments, div_events, all_returns):
    returns = {}
    change = 0.0
    try:
        returns = daily_returns(sym)
        if returns:
            change = returns[max(returns)]
    except Exception as e:
        print(f"price error {name}: {e}")
    all_returns[name] = returns

    try:
        heads = fetch_news(query)
    except Exception as e:
        print(f"news error {name}: {e}")
        heads = []

    heads = dedupe_heads(heads)
    score = weighted_score(heads)

    instruments[name] = {
        "type": kind,
        "change_pct": change,
        "score": score,
        "headlines": heads[:8],
        "pos_n": sum(1 for h in heads if h["score"] > 0),
        "neg_n": sum(1 for h in heads if h["score"] < 0),
    }
    update_contrarian(events, name, score, today_str, returns)
    update_divergence(div_events, name, score, change, today_str, returns)


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


def _trends_request(py, terms):
    """एक Google Trends अनुरोध: ANCHOR + ज़्यादा से ज़्यादा 4 शब्द।"""
    py.build_payload([ANCHOR] + terms, timeframe="now 7-d", geo="IN")
    df = py.interest_over_time()
    if df is None or df.empty:
        raise ValueError("Google से खाली डेटा मिला")
    return df[[ANCHOR] + terms].fillna(0)


def _ratio(df, term):
    """शब्द की खोज 'nifty' की खोज के अनुपात में (अभी और औसत)। एक ही अनुरोध के अंदर।"""
    a_recent = float(df[ANCHOR].tail(24).mean())
    a_avg = float(df[ANCHOR].mean())
    if a_recent <= 0 or a_avg <= 0:
        return 0.0, 0.0
    t_recent = float(df[term].tail(24).mean())
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


def _trends_once():
    """एक बार Google Trends से डेटा लेता है। 429 या कोई भी एरर ऊपर फेंकता है।
    फ़ियर के नंबर अंकों (points) में हैं; भीड़ के नंबर 'nifty' की खोज के प्रतिशत में हैं।"""
    from pytrends.request import TrendReq

    py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))

    # 1) फ़ियर मेट्रिक (एक अनुरोध)
    df_f = _trends_request(py, FEAR_TERMS)
    fear_df = df_f[FEAR_TERMS]
    if float(fear_df.values.max()) == 0:
        raise ValueError("सभी खोजों का डेटा शून्य है")
    base = float(fear_df.mean(axis=1).mean())
    recent = float(fear_df.tail(24).mean(axis=1).mean())
    fear_pts = round(recent - base, 1)
    per_term = []
    for t in FEAR_TERMS:
        b = float(fear_df[t].mean())
        r = float(fear_df[t].tail(24).mean())
        per_term.append({"term": t, "pts": round(r - b, 1), "now": round(r, 1), "avg": round(b, 1)})

    # 2) भीड़ का मूड: बुलिश और बियरिश शब्द, 4-4 के समूहों में, हर समूह के साथ ANCHOR
    bull_pct_sum = 0.0
    bear_pct_sum = 0.0
    bull_today_sum = 0.0
    bear_today_sum = 0.0
    bull_yesterday_sum = 0.0
    bear_yesterday_sum = 0.0
    crowd_terms = []
    ist_now = dt.datetime.now(dt.timezone.utc).astimezone(
        dt.timezone(dt.timedelta(hours=5, minutes=30)))
    today_ist = ist_now.strftime("%Y-%m-%d")
    yesterday_ist = (ist_now.date() - dt.timedelta(days=1)).isoformat()
    for side, terms in (("bull", BULL_TERMS), ("bear", BEAR_TERMS)):
        for chunk in _chunks(terms, TERM_CHUNK):
            time.sleep(8)
            df = _trends_request(py, chunk)
            for t in chunk:
                r_now, r_avg = _ratio(df, t)
                today_pct = _period_ratio(df, t, today_ist)
                yesterday_pct = _period_ratio(df, t, yesterday_ist)
                if side == "bull":
                    bull_pct_sum += r_now * 100
                    if today_pct is not None:
                        bull_today_sum += today_pct
                    if yesterday_pct is not None:
                        bull_yesterday_sum += yesterday_pct
                else:
                    bear_pct_sum += r_now * 100
                    if today_pct is not None:
                        bear_today_sum += today_pct
                    if yesterday_pct is not None:
                        bear_yesterday_sum += yesterday_pct
                crowd_terms.append({
                    "term": t, "dir": side,
                    "now": round(r_now * 100, 2), "avg": round(r_avg * 100, 2),
                    "today_pct": today_pct, "yesterday_pct": yesterday_pct,
                })

    # सभी शब्दों में now और average शून्य हों तो इसे सफल रीडिंग न मानें।
    # Google Trends कभी-कभी खाली/अधूरा जवाब देता है; उसे वैध डेटा बनाकर नहीं दिखाना चाहिए।
    if not crowd_terms or (
        all(float(p.get("now", 0) or 0) == 0 and float(p.get("avg", 0) or 0) == 0 for p in crowd_terms)
        or (bull_pct_sum == 0 and bear_pct_sum == 0)
    ):
        raise ValueError("Google Trends ने सभी crowd terms के लिए शून्य/खाली डेटा दिया")

    crowd_bull_pct, crowd_label = crowd_decision(bull_pct_sum, bear_pct_sum)

    # 3) Rising/related_queries अनुरोध जानबूझकर छोड़ा गया है:
    # यह एक अतिरिक्त Google Trends कॉल करता था और 429 की संभावना बढ़ाता था।
    # Crowd/Fear डेटा के बिना rising खोजों का खाली होना कोई सकारात्मक संकेत नहीं है।
    spikes = []

    today_total = bull_today_sum + bear_today_sum
    yesterday_total = bull_yesterday_sum + bear_yesterday_sum
    today_bull_pct = round(bull_today_sum / today_total * 100, 1) if today_total > 0 else None
    yesterday_bull_pct = round(bull_yesterday_sum / yesterday_total * 100, 1) if yesterday_total > 0 else None
    today_label = crowd_decision(bull_today_sum, bear_today_sum)[1] if today_total > 0 else "आज का डेटा उपलब्ध नहीं"
    yesterday_label = crowd_decision(bull_yesterday_sum, bear_yesterday_sum)[1] if yesterday_total > 0 else "कल का डेटा उपलब्ध नहीं"

    return {"ok": True, "unit": "points", "fear_vs_avg": fear_pts,
            "per_term": per_term, "spikes": spikes[:10],
            "crowd_bull_pct": crowd_bull_pct, "crowd_label": crowd_label,
            "today_bull_pct": today_bull_pct, "today_label": today_label,
            "yesterday_bull_pct": yesterday_bull_pct, "yesterday_label": yesterday_label,
            "today_date_ist": today_ist, "yesterday_date_ist": yesterday_ist,
            "bull_sum_pct": round(bull_pct_sum, 2), "bear_sum_pct": round(bear_pct_sum, 2),
            "min_side_pct": MIN_SIDE_PCT,
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
            # Google 429 = rate limit. उसी रन में पूरा Trends sequence दोहराने से
            # कई और अनुरोध होते हैं; तुरंत retry न करें, stale fallback/NO TRADE लागू होगा।
            if "429" in last_err or "too many requests" in last_err.lower():
                break
            if attempt < TRENDS_RETRIES - 1:
                time.sleep(60)
    return {"ok": False, "error": f"Google Trends फेल: {last_err}"}


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


def market_closed_today():
    """भारतीय बाज़ार आज बंद है? (सप्ताहांत, सूची में दी गई छुट्टी, या शाम 4 बजे के बाद
    भी आज का NIFTY बार न होना)। सुबह की छुट्टी सूची के बिना नहीं पकड़ी जा सकती।"""
    ist = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
    today = ist.date().isoformat()
    if today in NSE_HOLIDAYS or ist.weekday() >= 5:
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


def main():
    global SKIP_EVENTS
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    updated = now_utc.isoformat(timespec="minutes").replace("+00:00", "Z")
    events = load_json(EVENTS_FILE, [])
    crowd_events = load_json(CROWD_FILE, [])
    div_events = load_json(DIV_FILE, [])
    sig_state = load_json(SIG_STATE_FILE, {})
    sig_log = load_json(SIG_LOG_FILE, [])
    previous = load_json(DATA_FILE, {})

    result = {"updated": updated, "instruments": {}, "market_closed": SKIP_EVENTS}
    all_returns = {}
    SKIP_EVENTS = market_closed_today()

    for name, (sym, query) in INDEXES.items():
        process(name, sym, query, "index", events, today_str, result["instruments"],
                div_events, all_returns)

    for name, (sym, query) in STOCKS.items():
        process(name, sym, query, "stock", events, today_str, result["instruments"],
                div_events, all_returns)

    # संकेत-बदलाव: CRUDEOIL और DJI के लिए
    update_signals(result["instruments"], sig_state, sig_log, updated)

    result["signals"] = {
        "state": signal_summary(sig_state),
        "events": sig_log[-15:],
        "watch": list(SIGNAL_WATCH.keys()),
    }

    result["contrarian"] = {
        "events": events[-30:],
        "tracked": len([e for e in events if e["outcome"]]),
        "reversed": len([e for e in events if e["outcome"] == "reversed"]),
        "continued": len([e for e in events if e["outcome"] == "continued"]),
    }

    div_done = [e for e in div_events if e.get("outcome")]
    result["divergence"] = {
        "tracked": len(div_done),
        "sentiment": len([e for e in div_done if e["outcome"] == "sentiment"]),
        "price": len([e for e in div_done if e["outcome"] == "price"]),
        "events": div_events[-12:],
    }

    result["range"] = nifty_range()
    result["levels"] = build_levels(result["range"])

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

    # Google Trends is rate-limited on frequent GitHub Actions runs.
    # Reuse a successful snapshot for up to 6 hours; preserve its real as_of timestamp.
    # Once older than 6 hours, attempt a refresh and keep stale=true if refresh fails.
    previous_trends = previous.get("trends") or {}
    trends_age_hours = None
    try:
        trends_as_of = dt.datetime.fromisoformat(
            str(previous_trends.get("as_of", "")).replace("Z", "+00:00")
        )
        if trends_as_of.tzinfo is None:
            trends_as_of = trends_as_of.replace(tzinfo=dt.timezone.utc)
        trends_age_hours = (now_utc - trends_as_of.astimezone(dt.timezone.utc)).total_seconds() / 3600
    except Exception:
        pass

    previous_crowd_terms = previous_trends.get("crowd_terms") or []
    previous_trends_all_zero = (
        not previous_crowd_terms
        or all(float(p.get("now", 0) or 0) == 0 and float(p.get("avg", 0) or 0) == 0
               for p in previous_crowd_terms)
        or (float(previous_trends.get("bull_sum_pct", 0) or 0) == 0
            and float(previous_trends.get("bear_sum_pct", 0) or 0) == 0)
    )

    if (previous_trends.get("ok") and not previous_trends_all_zero
            and trends_age_hours is not None and 0 <= trends_age_hours < 6):
        trends = dict(previous_trends)
        trends["stale"] = False
        trends["cached"] = True
        trends["refresh_policy_hours"] = 6
        trends.pop("error", None)
        print(f"Using cached Google Trends snapshot ({trends_age_hours:.1f}h old; refresh window 6h)")
    else:
        # अमान्य zero-cache को fallback के रूप में भी वापस न दिखाएँ।
        fallback_trends = {} if previous_trends_all_zero else previous_trends
        trends = pick_with_fallback(fetch_trends(), fallback_trends)
        if trends.get("ok") and not trends.get("stale"):
            trends["as_of"] = updated
            trends["cached"] = False
            trends["refresh_policy_hours"] = 6
    result["trends"] = trends

    fresh_trends = trends.get("ok") and not trends.get("stale")
    crowd_pct = trends.get("crowd_bull_pct") if fresh_trends else None
    nifty_ret = all_returns.get("NIFTY") or {}
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
    div_events = clean(div_events)
    sig_state = clean(sig_state)
    sig_log = clean(sig_log)

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
