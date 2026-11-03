import json, csv, os, re, time, math, datetime as dt, html
from urllib.parse import quote_plus
import feedparser, yfinance as yf
import requests

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
    # प्रचलित English + Hindi/roman Hindi खोजें; कम-volume शब्दों को भी रखा है,
    # ताकि एक-दो शब्द शून्य होने पर पूरा Trends स्कैन विफल न हो।
    "nifty rally", "nifty rise", "nifty bullish", "sensex rise",
    "nifty target", "nifty up", "share market teji", "nifty badhega",
]
BEAR_TERMS = [
    # बुलिश सूची के समान आकार की bearish खोजें; दोनों पक्षों का संतुलित कवरेज।
    "nifty fall", "nifty crash", "nifty bearish", "sensex fall",
    "nifty down", "nifty low", "share market girawat", "nifty girega",
]
TERM_CHUNK = 4

# भीड़ का मूड तभी दिखेगा जब दोनों तरफ़ के शब्दों में कम से कम इतनी खोज हो।
# यह मान "निफ़्टी" की खोज के प्रतिशत में है। शुरुआती मान है, डैशबोर्ड पर असली अनुपात दिखता है ताकि बदला जा सके।
MIN_SIDE_PCT = 0.01
TRENDS_RETRIES = 1  # तय समय पर केवल एक प्रयास; 429 पर उसी स्लॉट में दोबारा अनुरोध नहीं
TRENDS_MAX_AGE_MINUTES = 30  # 30 मिनट से पुरानी Google Trends reading Crowd score में शामिल नहीं होगी

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



# ---- NSE official MCP quotes (primary for NSE cash market) ----
NSE_MCP_URL = "https://mcp.nseindia.in/cmmkt/mcp"
NSE_MCP_HEADERS = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "User-Agent": "Mozilla/5.0 Trinetra"}
NSE_QUOTE_CACHE = {"stocks": None, "loaded_at": 0}

def nse_mcp_call(tool_name, arguments):
    """Each retry uses a fresh MCP session; NSE sometimes returns transient HTTP 404."""
    for attempt in range(3):
        try:
            with requests.Session() as session:
                init = session.post(NSE_MCP_URL, headers=NSE_MCP_HEADERS, json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                               "clientInfo": {"name": "trinetra", "version": "1.0"}}
                }, timeout=25)
                init.raise_for_status()
                headers = dict(NSE_MCP_HEADERS)
                sid = init.headers.get("Mcp-Session-Id")
                if sid:
                    headers["Mcp-Session-Id"] = sid
                response = session.post(NSE_MCP_URL, headers=headers, json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments}
                }, timeout=35)
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                    for line in response.text.splitlines():
                        if line.startswith("data:"):
                            try:
                                payload = json.loads(line[5:].strip())
                                break
                            except ValueError:
                                continue
                if isinstance(payload, dict) and not payload.get("error"):
                    contents = (payload.get("result") or {}).get("content") or []
                    for item in contents:
                        if item.get("type") == "text":
                            try:
                                return json.loads(item.get("text", ""))
                            except (ValueError, TypeError):
                                continue
        except Exception as exc:
            print(f"NSE MCP {tool_name} attempt {attempt + 1}/3 failed: {str(exc)[:180]}")
        if attempt < 2:
            time.sleep(1.0 + attempt)
    return None

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
    return NSE_QUOTE_CACHE["stocks"] or {}

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
        if stamp.date() != now_ist.date():
            raise ValueError(f"BSE quote is not today's session: {stamp_text}")
        # After the cash market closes, the final exchange quote remains the
        # valid closing snapshot for today. Accept it only when its source
        # timestamp is from the final 15 minutes of today's session.
        after_close = now_ist.time() >= dt.time(15, 30) and stamp.time() >= dt.time(15, 15)
        max_age_seconds = 6 * 60 * 60 if after_close else 30 * 60
        if (now_ist - stamp).total_seconds() > max_age_seconds or stamp > now_ist + dt.timedelta(minutes=2):
            raise ValueError(f"BSE quote timestamp outside allowed session window: {stamp_text}")
        return {"price": price, "stamp": stamp.strftime("%d-%b-%Y %H:%M:%S"),
                "source": "BSE",
                "change_pct": float(str(raw_pct).replace("%", "").replace(",", "")) if raw_pct is not None else None}
    except Exception as exc:
        print(f"BSE SENSEX quote unavailable: {exc}")
        return None


def google_finance_sensex_quote():
    """Read Google's direct SENSEX quote and its explicit timestamp; never use a candle."""
    try:
        page = requests.get(
            "https://www.google.com/finance/quote/SENSEX:INDEXBOM",
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                     "Accept-Language": "en-IN,en;q=0.9",
                     "Cache-Control": "no-cache"},
            timeout=15
        )
        page.raise_for_status()
        text = html.unescape(re.sub(r"<[^>]+>", " ", page.text))
        text = re.sub(r"\s+", " ", text)
        match = re.search(
            r"([A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2}:\d{2}\s*[AP]M\s*GMT\+5:30)",
            text
        )
        if not match:
            raise ValueError("Google Finance quote timestamp missing")
        ist_tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
        now_ist = dt.datetime.now(dt.timezone.utc).astimezone(ist_tz)
        stamp = dt.datetime.strptime(match.group(1), "%b %d, %I:%M:%S %p GMT+5:30")
        stamp = stamp.replace(year=now_ist.year, tzinfo=ist_tz)
        if stamp.date() != now_ist.date() or stamp > now_ist + dt.timedelta(minutes=2):
            raise ValueError("Google Finance quote is not from today's session")
        after_close = now_ist.time() >= dt.time(15, 30) and stamp.time() >= dt.time(15, 15)
        max_age = 6 * 60 * 60 if after_close else 15 * 60
        if (now_ist - stamp).total_seconds() > max_age:
            raise ValueError("Google Finance quote is outside the allowed freshness window")
        price_match = re.search(
            r"(?:BSE SENSEX|S&P BSE SENSEX).{0,500}?([0-9]{1,3}(?:,[0-9]{3})+\.\d{2})",
            text
        )
        if not price_match:
            prefix = text[:match.start()]
            candidates = re.findall(r"(?<![0-9])([0-9]{1,3}(?:,[0-9]{3})+\.\d{2})(?![0-9])", prefix)
            if not candidates:
                raise ValueError("Google Finance SENSEX price missing")
            raw_price = candidates[-1]
        else:
            raw_price = price_match.group(1)
        price = float(raw_price.replace(",", ""))
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Google Finance returned an invalid SENSEX price")
        return {"price": price, "stamp": stamp.strftime("%d-%b-%Y %H:%M:%S"),
                "source": "Google Finance direct SENSEX quote"}
    except Exception as exc:
        print(f"Google Finance direct SENSEX quote unavailable: {str(exc)[:160]}")
        return None


def nse_cash_quote(name, sym):
    """Return actual NSE/BSE quote and exchange timestamp; never replace it with scan time."""
    if name == "SENSEX":
        # BSE exchange quote first; Google's direct quote page is the no-key backup.
        # Neither source reads an OHLC/intraday candle.
        return bse_sensex_quote() or google_finance_sensex_quote()
    if name == "NIFTY":
        data = nse_mcp_call("cm_get_index_quote", {"indexName": "NIFTY 50"})
        idx = (data or {}).get("index", {})
        if idx.get("last") and data.get("nseTimestamp"):
            return {"price": float(idx["last"]), "stamp": data["nseTimestamp"],
                    "source": "NSE"}
    elif name == "BANKNIFTY":
        data = nse_mcp_call("cm_get_index_quote", {"indexName": "NIFTY BANK"})
        idx = (data or {}).get("index", {})
        if idx.get("last") and data.get("nseTimestamp"):
            return {"price": float(idx["last"]), "stamp": data["nseTimestamp"],
                    "source": "NSE"}
    elif sym.endswith(".NS"):
        symbol = sym[:-3].upper()
        data = nse_mcp_call("cm_get_stock_quote", {"symbol": symbol})
        def find_quote(node):
            if isinstance(node, dict):
                price = next((node.get(k) for k in
                              ("lastTradedPrice", "lastPrice", "ltp", "last")
                              if node.get(k) is not None), None)
                stamp = next((node.get(k) for k in
                              ("latestTimestamp", "timestamp", "nseTimestamp")
                              if node.get(k)), None)
                pct = next((node.get(k) for k in
                            ("perChange", "changePercent", "pChange", "change_pct")
                            if node.get(k) is not None), None)
                if price is not None and stamp:
                    return {"price": float(price), "stamp": stamp,
                            "change_pct": float(pct) if pct is not None else None}
                for value in node.values():
                    found = find_quote(value)
                    if found:
                        return found
            elif isinstance(node, list):
                for value in node:
                    found = find_quote(value)
                    if found:
                        return found
            return None
        quote = find_quote(data)
        if quote:
            return {**quote, "source": "NSE"}
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

def refresh_mcx_silver_reference():
    """Try to read public MCX SILVER quote from Upstox; never substitute SI=F."""
    path = MCX_SILVER_FILE
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
        response = requests.get(MCX_PUBLIC_URL, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
        # The public page's main quote is normally rendered as ₹1,96,100.00.
        # Use a conservative value range to avoid picking unrelated prices.
        matches = re.findall(r"(?:₹|&#8377;|&#x20b9;|INR\s*)\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]{5,6}(?:\.[0-9]{1,2})?)", html, re.I)
        candidates = []
        for item in matches:
            try:
                value = float(item.replace(",", ""))
                if 50000 <= value <= 500000:
                    candidates.append(value)
            except ValueError:
                pass
        if not candidates:
            raise ValueError("public page quote not found or outside validation range")
        # First matching price in the page is usually the headline quote.
        current = round(candidates[0], 2)
        data = load_json(path, {})
        old = data.get("mcx_price_per_kg")
        try:
            old_num = float(old)
        except (TypeError, ValueError):
            old_num = None
        if old_num and old_num > 0 and old_num != current:
            data["previous_mcx_price_per_kg"] = old_num
        data.update({
            "mcx_price_per_kg": current,
            "date": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date().isoformat(),
            "source": "Upstox public MCX Silver quote (automatically fetched; verify if page format changes)",
            "source_url": MCX_PUBLIC_URL,
            "source_time": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST"),
            "note": "Public-page quote, not exchange-certified live feed. Dashboard display applies 3% GST estimate."
        })
        with open(path, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        print(f"MCX silver public quote refreshed: ₹{current:,.2f}/kg")
        return True
    except Exception as exc:
        print(f"MCX silver auto-refresh failed; retaining last reference and its original timestamp: {exc}")
        return False

def silver_display_price(international_inr_per_kg=None):
    """केवल सत्यापित mcx_silver.json MCX भाव पर 3% GST जोड़ें; अंतरराष्ट्रीय भाव को MCX न बताएं."""
    try:
        mcx = load_json(MCX_SILVER_FILE, {})
        raw = mcx.get("mcx_price_per_kg")
        value = float(raw) if raw is not None else None
        if value is not None and math.isfinite(value) and value > 0:
            return round(value * (1 + GST_RATE), 2), str(mcx.get("date", "")), "MCX quote + 3% GST Estimate"
    except Exception as e:
        print(f"MCX silver manual file error: {e}")
    return None, "", "MCX भाव उपलब्ध नहीं — अनुमान नहीं दिखाया गया"

GOLD_MCX_FILE = "mcx_gold.json"
GOLD_PUBLIC_URL = "https://upstox.com/commodity-market-trading/mcx-gold-price/"

def refresh_mcx_gold_reference():
    """Fetch a public MCX gold quote; only update when a plausible ₹/10g quote is found."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
        response = requests.get(GOLD_PUBLIC_URL, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
        matches = re.findall(r"(?:₹|&#8377;|&#x20b9;|INR\s*)\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]{5,6}(?:\.[0-9]{1,2})?)", html, re.I)
        candidates = []
        for item in matches:
            try:
                value = float(item.replace(",", ""))
                if 50000 <= value <= 500000:
                    candidates.append(value)
            except ValueError:
                pass
        if not candidates:
            raise ValueError("public page quote not found or outside ₹50,000–₹5,00,000 per 10g validation range")
        current = round(candidates[0], 2)
        data = load_json(GOLD_MCX_FILE, {})
        old = data.get("mcx_price_per_10g")
        try:
            old_num = float(old)
        except (TypeError, ValueError):
            old_num = None
        if old_num and old_num > 0 and old_num != current:
            data["previous_mcx_price_per_10g"] = old_num
        now_ist = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
        data.update({
            "mcx_price_per_10g": current,
            "date": now_ist.date().isoformat(),
            "source": "Upstox public MCX Gold page quote; not an exchange-certified live feed",
            "source_url": GOLD_PUBLIC_URL,
            "source_time": now_ist.strftime("%Y-%m-%d %H:%M IST"),
            "note": "Reference quote per 10g; dashboard display adds 3% GST estimate. Jewellery making charges are not included."
        })
        with open(GOLD_MCX_FILE, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        print(f"MCX gold public quote refreshed: ₹{current:,.2f}/10g")
        return True
    except Exception as exc:
        print(f"MCX gold auto-refresh failed; retaining last reference and its original timestamp: {exc}")
        return False

def gold_display_price():
    """MCX reference per 10g plus 3% GST; no jewellery making charges."""
    try:
        data = load_json(GOLD_MCX_FILE, {})
        value = float(data.get("mcx_price_per_10g"))
        if math.isfinite(value) and value > 0:
            return round(value * (1 + GST_RATE), 2), str(data.get("date", "")), "MCX quote × 3% GST"
    except Exception as exc:
        print(f"MCX gold reference unavailable: {exc}")
    return None, "", "MCX Gold भाव उपलब्ध नहीं — अनुमान नहीं दिखाया गया"

CRUDE_MCX_FILE = "mcx_crudeoil.json"
CRUDE_PUBLIC_URL = "https://upstox.com/commodity-market-trading/mcx-crudeoil-price/"

def refresh_mcx_crude_reference():
    """Fetch MCX CRUDEOIL in INR/barrel; never substitute Brent USD quotes."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
        response = requests.get(CRUDE_PUBLIC_URL, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
        matches = re.findall(r"(?:₹|&#8377;|&#x20b9;|INR\s*)\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]{4,5}(?:\.[0-9]{1,2})?)", html, re.I)
        candidates = []
        for item in matches:
            try:
                value = float(item.replace(",", ""))
                if 3000 <= value <= 30000:
                    candidates.append(value)
            except ValueError:
                pass
        if not candidates:
            raise ValueError("MCX CRUDEOIL quote not found or outside ₹3,000–₹30,000/BBL validation range")
        current = round(candidates[0], 2)
        stamp_match = re.search(r"Last updated on\s*(\d{1,2}\s+[A-Za-z]{3},?\s+\d{4})\s*\|\s*(\d{1,2}:\d{2})\s*IST", html, re.I)
        if not stamp_match:
            raise ValueError("MCX quote timestamp missing; refusing to label it live")
        stamp = dt.datetime.strptime(stamp_match.group(1).replace(",", ""), "%d %b %Y")
        hh, mm = map(int, stamp_match.group(2).split(":"))
        stamp = stamp.replace(hour=hh, minute=mm)
        date = stamp.date().isoformat()
        time_label = stamp.strftime("%I:%M %p IST").lstrip("0")
        pct_match = re.search(r"(?:\+|−|-)?\s*₹[\d,]+(?:\.\d+)?\s*\(\s*([+\-]?\d+(?:\.\d+)?)%\s*\)", html, re.I)
        change_pct = round(float(pct_match.group(1)), 2) if pct_match else None
        data = load_json(CRUDE_MCX_FILE, {})
        old_price = data.get("mcx_price_per_bbl")
        if old_price is not None and float(old_price) != current:
            data["previous_mcx_price_per_bbl"] = float(old_price)
        data.update({
            "mcx_price_per_bbl": current, "change_pct": change_pct,
            "date": date, "time": time_label,
            "source": "Upstox MCX CRUDEOIL quote (₹/BBL)",
            "source_url": CRUDE_PUBLIC_URL,
            "note": "Public MCX contract quote; not an exchange-certified direct feed."
        })
        with open(CRUDE_MCX_FILE, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        print(f"MCX crude quote refreshed: ₹{current:,.2f}/BBL ({date} {time_label})")
        return True
    except Exception as exc:
        print(f"MCX crude refresh failed; keeping original quote timestamp if available: {exc}")
        return False

def crude_display_quote():
    """Return the stored MCX quote with its actual source date/time."""
    data = load_json(CRUDE_MCX_FILE, {})
    try:
        value = float(data.get("mcx_price_per_bbl"))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("invalid MCX crude quote")
        return (round(value, 2), str(data.get("date") or ""),
                str(data.get("time") or ""), str(data.get("source") or "MCX CRUDEOIL"),
                data.get("change_pct"))
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
    keep = [(d.date() < today_market_date) or (indian_closed and d.date() == ist_now.date()) for d in closes.index]
    closes = closes[keep]
    last_close = float(closes.iloc[-1]) if len(closes) else None
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
    PRICE_CACHE[sym + "_PREV_CLOSE"] = last_close
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
        PRICE_CACHE["GC=F_TIME"] = compact_ist_time(gold_stamp) if gold_stamp[:10] == str(gold_meta.get("date") or "") else None
        gold = load_json(GOLD_MCX_FILE, {})
        try:
            previous_gold = float(gold.get("previous_mcx_price_per_10g"))
            current_gold = float(gold.get("mcx_price_per_10g"))
            PRICE_CACHE["GC=F_CHANGE_PCT"] = round((current_gold / previous_gold - 1) * 100, 2) if previous_gold > 0 and current_gold > 0 else None
        except (TypeError, ValueError):
            PRICE_CACHE["GC=F_CHANGE_PCT"] = None
    if sym == "SI=F":
        silver_price, silver_date, silver_source = silver_display_price(last_close)
        PRICE_CACHE[sym] = silver_price
        PRICE_CACHE["SI=F_SOURCE"] = silver_source
        PRICE_CACHE["SI=F_DATE"] = silver_date
        silver_meta = load_json(MCX_SILVER_FILE, {})
        silver_stamp = str(silver_meta.get("source_time") or "")
        PRICE_CACHE["SI=F_TIME"] = compact_ist_time(silver_stamp) if silver_stamp[:10] == str(silver_meta.get("date") or "") else None
        # Yahoo SI=F का प्रतिशत बदलाव MCX के ₹/kg भाव का बदलाव नहीं है।
        # MCX का पिछला भाव फाइल में न हो तो गलत प्रतिशत न दिखाएँ।
        mcx = load_json(MCX_SILVER_FILE, {})
        previous_mcx = mcx.get("previous_mcx_price_per_kg")
        current_mcx = mcx.get("mcx_price_per_kg")
        try:
            previous_mcx = float(previous_mcx)
            current_mcx = float(current_mcx)
            PRICE_CACHE["SI=F_CHANGE_PCT"] = round((current_mcx / previous_mcx - 1) * 100, 2) if previous_mcx > 0 and current_mcx > 0 else None
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
            if result:
                return result
            raise ValueError("Coinbase latest trade is older than 3 minutes or has an invalid timestamp")
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

def fetch_participant_oi(base_date=None):
    """NSE official participant-wise OI: daily EOD, not a live feed.
    base_date lets the caller fetch the latest archived snapshot on/before a target date."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,text/plain,*/*",
               "Referer": "https://www.nseindia.com/"}
    last_error = "NSE participant OI CSV unavailable"
    if base_date is None:
        base_date = dt.datetime.now(dt.timezone.utc).date()
    elif isinstance(base_date, str):
        base_date = dt.date.fromisoformat(base_date)
    for offset in range(0, 8):
        day = base_date - dt.timedelta(days=offset)
        if day.weekday() >= 5:
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
    change = 0.0
    try:
        returns = daily_returns(sym)
        if returns:
            change = returns[max(returns)]
    except Exception as e:
        print(f"price error {name}: {e}")
    all_returns[name] = returns

    # NSE official quote is primary for Indian cash indices/stocks; Yahoo is backup.
    nse_quote = nse_cash_quote(name, sym)
    # SENSEX price must come only from the direct BSE index quote, never an OHLC candle.
    yahoo_quote = intraday_quote(sym) if not nse_quote and name != "SENSEX" else None
    live_quote = nse_quote or yahoo_quote
    if live_quote:
        PRICE_CACHE[sym] = live_quote["price"]
        if sym == "BTC-USD":
            PRICE_CACHE["BTC-USD_DATE"] = live_quote["date"] + " " + live_quote["time"]
            PRICE_CACHE["BTC-USD_SOURCE"] = live_quote["source"]
            prev_close = PRICE_CACHE.get(sym + "_PREV_CLOSE")
            if prev_close and prev_close > 0:
                PRICE_CACHE["BTC-USD_CHANGE_PCT"] = round((live_quote["price"] / prev_close - 1) * 100, 2)
        if nse_quote and nse_quote.get("change_pct") is not None:
            change = round(nse_quote["change_pct"], 2)
        elif name == "SENSEX":
            # After 15:45 IST daily_returns includes today's completed close.
            # Do not divide the closing quote by today's close (which would
            # incorrectly display 0.00%); use today's recorded daily return.
            now_ist = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
            if now_ist.weekday() < 5 and now_ist.time() >= dt.time(15, 45) and returns:
                change = returns[max(returns)]
            else:
                prev_close = PRICE_CACHE.get(sym + "_PREV_CLOSE")
                if prev_close and prev_close > 0:
                    change = round((live_quote["price"] / prev_close - 1) * 100, 2)
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
        "price_source": live_quote["source"] if live_quote else PRICE_CACHE.get("BZ=F_SOURCE") if sym == "BZ=F" else PRICE_CACHE.get("SI=F_SOURCE") if sym == "SI=F" else PRICE_CACHE.get("GC=F_SOURCE") if sym == "GC=F" else PRICE_CACHE.get("BTC-USD_SOURCE") if sym == "BTC-USD" else None,
        "score": score,
        "headline_score": score,
        "headlines": heads[:8],
        "pos_n": sum(1 for h in heads if h["score"] > 0),
        "neg_n": sum(1 for h in heads if h["score"] < 0),
        **derive_card_indicator(name, sym, score, change),
    }
    update_contrarian(events, name, score, today_str, returns)
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