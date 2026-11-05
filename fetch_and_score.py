import json, csv, os, re, time, math, datetime as dt, html
from urllib.parse import quote_plus
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
    "nifty today", "sensex today", "share market", "option chain",
    "निफ्टी आज", "सेंसेक्स आज", "शेयर बाजार", "शेयर बाजार आज",
]
TERM_CHUNK = 4

# भीड़ का मूड तभी दिखेगा जब दोनों तरफ़ के शब्दों में कम से कम इतनी खोज हो।
# यह मान "निफ़्टी" की खोज के प्रतिशत में है। शुरुआती मान है, डैशबोर्ड पर असली अनुपात दिखता है ताकि बदला जा सके।
MIN_SIDE_PCT = 0.01
TRENDS_RETRIES = 1  # तय समय पर केवल एक प्रयास; 429 पर उसी स्लॉट में दोबारा अनुरोध नहीं
TRENDS_MAX_AGE_MINUTES = 360  # 30 मिनट से पुरानी Google Trends reading Crowd score में शामिल नहीं होगी

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
            # US indices: accept a same-session close overnight, but never a
            # quote older than 18 hours (weekends/holidays naturally expire).
            max_age = 18 * 60 * 60
            if age_seconds > max_age:
                raise ValueError("US index quote is older than the allowed 18-hour session window")
            time_label = stamp.strftime("%I:%M %p ET").lstrip("0")
        else:
            after_close = now_exchange.time() >= dt.time(15, 30) and stamp.time() >= dt.time(15, 15)
            max_age = 6 * 60 * 60 if after_close else 15 * 60
            if age_seconds > max_age:
                raise ValueError("Google Finance quote is outside the allowed freshness window")
            time_label = stamp.strftime("%I:%M %p") + " " + ("IST" if offset_text == "+5:30" else "local")
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
        change_pct = float(pct_match.group(1).replace("%", "").replace(" ", "")) if pct_match else None
        return {"price": price, "stamp": stamp.strftime("%d-%b-%Y %H:%M:%S"),
                "date": stamp.date().isoformat(), "time": time_label,
                "source": "Google Finance direct " + label + " quote",
                "change_pct": change_pct}
    except Exception as exc:
        print(f"Google Finance {label} quote unavailable: {str(exc)[:160]}")
        return None


def google_finance_sensex_quote():
    return google_finance_quote("SENSEX", "INDEXBOM", "SENSEX")


def nse_cash_quote(name, sym):
    """Prefer official exchange quotes; use Google Finance only as a timestamp-validated backup."""
    if name == "SENSEX":
        return bse_sensex_quote() or google_finance_sensex_quote()
    if name in ("NIFTY", "BANKNIFTY"):
        index_name = "NIFTY 50" if name == "NIFTY" else "NIFTY BANK"
        # Discover the exact cm_get_index_quote input schema from NSE tools/list
        # on the live server, then call it with only schema-derived arguments.
        tool_name = "cm_get_index_quote"
        arguments = nse_index_quote_arguments(tool_name, index_name)
        data = nse_mcp_call(tool_name, arguments) if arguments is not None else None
        def find_index_quote(node, inherited_stamp=None, matched=False):
            if isinstance(node, dict):
                labels = " ".join(str(node.get(k) or "") for k in
                                  ("indexName", "name", "index", "symbol", "index_name")).upper()
                target = index_name.upper()
                is_match = matched or (target in labels if labels else False)
                stamp = next((node.get(k) for k in
                              ("nseTimestamp", "latestTimestamp", "updatedAt",
                               "timestamp", "time", "lastUpdateTime")
                              if node.get(k)), inherited_stamp)
                price = next((node.get(k) for k in
                              ("last", "lastValue", "lastPrice", "lastTradedPrice",
                               "indexValue", "currentIndexValue", "ltp", "currentValue")
                              if node.get(k) is not None), None)
                if price is not None and stamp and (is_match or not labels):
                    return {"price": float(price), "stamp": stamp}
                for key, value in node.items():
                    key_match = target in str(key).upper()
                    found = find_index_quote(value, stamp, is_match or key_match)
                    if found:
                        return found
            elif isinstance(node, list):
                for value in node:
                    found = find_index_quote(value, inherited_stamp, matched)
                    if found:
                        return found
            return None
        quote = find_index_quote(data)
        if quote:
            return {**quote, "source": "NSE"}
        return google_finance_quote("NIFTY_50" if name == "NIFTY" else "NIFTY_BANK",
                                   "INDEXNSE", index_name)
    if sym.endswith(".NS"):
        symbol = sym[:-3].upper()
        def find_quote(node, inherited_stamp=None):
            if isinstance(node, dict):
                stamp = next((node.get(k) for k in
                              ("latestTimestamp", "timestamp", "nseTimestamp", "updatedAt")
                              if node.get(k)), inherited_stamp)
                price = next((node.get(k) for k in
                              ("lastTradedPrice", "lastPrice", "ltp", "last")
                              if node.get(k) is not None), None)
                pct = next((node.get(k) for k in
                            ("perChange", "changePercent", "pChange", "change_pct")
                            if node.get(k) is not None), None)
                if price is not None and stamp:
                    return {"price": float(price), "stamp": stamp,
                            "change_pct": float(pct) if pct is not None else None}
                for value in node.values():
                    found = find_quote(value, stamp)
                    if found:
                        return found
            elif isinstance(node, list):
                for value in node:
                    found = find_quote(value, inherited_stamp)
                    if found:
                        return found
            return None

        # First use one cached bulk NSE response for the entire watchlist.
        universe = nse_stock_universe()
        quote = find_quote(universe.get(symbol)) if isinstance(universe, dict) else None
        if quote:
            return {**quote, "source": "NSE"}

        # If the bulk endpoint did not include this symbol, try the individual quote.
        data = nse_mcp_call("cm_get_stock_quote", {"symbol": symbol})
        quote = find_quote(data)
        if quote:
            return {**quote, "source": "NSE"}
        return google_finance_quote(symbol, "NSE", symbol)
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
def parse_upstox_mcx_quote(page_html, min_price, max_price, label):
    """Extract an MCX quote, its exchange-page timestamp and daily change from Upstox."""
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
    if age_minutes < -2 or age_minutes > 45:
        raise ValueError(f"{label} source quote is outside the 45-minute freshness window")
    pct_match = re.search(
        r"(?:\+|−|-)?\s*₹[\d,]+(?:\.\d+)?\s*\(\s*([+\-−]?\d+(?:\.\d+)?)%\s*\)",
        text
    )
    if not pct_match:
        raise ValueError(f"{label} daily change percentage missing")
    change_pct = float(pct_match.group(1).replace("−", "-"))
    prev_match = re.search(r"Prev\.?\s*Close\s*₹\s*([\d,]+(?:\.\d+)?)", text, re.I)
    previous_close = float(prev_match.group(1).replace(",", "")) if prev_match else None
    if previous_close is None or previous_close <= 0:
        raise ValueError(f"{label} previous close missing")
    return {
        "price": round(prices[0], 2), "previous_close": round(previous_close, 2),
        "change_pct": round(change_pct, 2), "date": stamp.date().isoformat(),
        "time": stamp.strftime("%H:%M"), "source_time": stamp.strftime("%Y-%m-%d %H:%M IST")
    }


def mcx_reference_is_fresh(data, max_age_minutes=45):
    """Reject cached MCX quotes unless their source-page timestamp is recent."""
    try:
        stamp = dt.datetime.strptime(str(data.get("source_time") or ""), "%Y-%m-%d %H:%M IST")
        ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
        stamp = stamp.replace(tzinfo=ist)
        now = dt.datetime.now(dt.timezone.utc).astimezone(ist)
        age = (now - stamp).total_seconds() / 60
        return -2 <= age <= max_age_minutes
    except (TypeError, ValueError):
        return False

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
            "source_time": quote["source_time"],
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
            return round(value * (1 + GST_RATE), 2), str(mcx.get("date", "")), "MCX quote + 3% GST Estimate"
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
            "source_time": quote["source_time"],
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
            return round(value * (1 + GST_RATE), 2), str(data.get("date", "")), "MCX quote × 3% GST"
        if not mcx_reference_is_fresh(data):
            return None, "", "MCX GOLD quote पुराना है — नया भाव उपलब्ध नहीं"
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
            "source_time": stamp.strftime("%Y-%m-%d %H:%M IST"),
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
    """Return only a recent, source-timestamped MCX CRUDEOIL quote."""
    data = load_json(CRUDE_MCX_FILE, {})
    try:
        value = float(data.get("mcx_price_per_bbl"))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("invalid MCX crude quote")
        if not mcx_reference_is_fresh(data):
            raise ValueError("MCX CRUDEOIL source quote is older than 45 minutes")
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
    # Save the previous completed session close separately. After the market
    # closes, today's close may be included for display, but it must never
    # become the comparison base (otherwise index change incorrectly becomes 0%).
    previous_session = [float(value) for stamp, value in closes.items()
                        if stamp.date() < today_market_date and math.isfinite(float(value))]
    previous_close = previous_session[-1] if previous_session else None
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
    PRICE_CACHE[sym + "_PREV_CLOSE"] = (previous_close if indian_closed and previous_close is not None
                                         else last_close)
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
        # स्रोत से कोई candle न लौटे (जैसे Yahoo 429/खाली response) तब भी
        # लक्ष्य विंडो बीतने के बाद pending अनिश्चितकाल तक नहीं रहना चाहिए।
        horizon.update({
            "status": "unavailable",
            "reason": "लक्ष्य समय के 10 मिनट के भीतर पूरी candle नहीं मिली या स्रोत ने डेटा नहीं दिया",
        })


def update_contrarian(events, name, score, today_str, returns, sym):
    """±6 समाचार स्कोर इवेंट; अगले सत्र के साथ अलग 30m/60m परिणाम भी दर्ज करें."""
    key = f"{today_str}|{name}"
    existing = next((e for e in events if e.get("key") == key), None)
    if abs(score) >= CONTRARIAN_LIMIT and not SKIP_EVENTS and existing is None:
        event = {"key": key, "date": today_str, "instrument": name,
                 "score": score, "outcome": None, "next_change": None,
                 "baseline_price": None, "baseline_time": None, "baseline_attempted": False,
                 "intraday_source": "Yahoo Finance completed 5-minute candles",
                 "after_30m": {"status": "unavailable", "reason": "ताज़ा शुरुआती candle नहीं मिली"},
                 "after_60m": {"status": "unavailable", "reason": "ताज़ा शुरुआती candle नहीं मिली"}}
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

    # Intraday horizons are prospective only. Old records without a baseline stay legacy.
    needs_bars = any(
        e.get("baseline_time") and any(
            isinstance(e.get(field), dict) and e[field].get("status") == "pending"
            for field in ("after_30m", "after_60m")
        ) for e in relevant
    )
    new_baseline_needed = bool(existing and existing.get("baseline_attempted") is False)
    bars = _completed_5m_bars(sym) if (needs_bars or new_baseline_needed) else []
    if new_baseline_needed:
        # Baseline केवल उसी scan में लें जिसमें extreme event पहली बार दर्ज हुआ।
        # अगली सुबह की candle को पिछली शाम के संकेत का शुरुआती भाव नहीं मानना है।
        existing["baseline_attempted"] = True
        latest = bars[-1] if bars else None
        age = ((dt.datetime.now(dt.timezone.utc) - latest["time"]).total_seconds() / 60
               if latest else None)
        if latest and -1 <= age <= 15:
            existing["baseline_price"] = round(latest["price"], 4)
            existing["baseline_time"] = latest["time"].isoformat(timespec="seconds").replace("+00:00", "Z")
            existing["after_30m"] = {"status": "pending"}
            existing["after_60m"] = {"status": "pending"}
        else:
            reason = "इवेंट दर्ज होते समय ताज़ा पूरी 5-मिनट candle नहीं मिली"
            existing["after_30m"] = {"status": "unavailable", "reason": reason}
            existing["after_60m"] = {"status": "unavailable", "reason": reason}
    if bars:
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
    global_quote = None
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
            prev_close = PRICE_CACHE.get(sym + "_PREV_CLOSE")
            if prev_close and prev_close > 0:
                PRICE_CACHE["BTC-USD_CHANGE_PCT"] = round((live_quote["price"] / prev_close - 1) * 100, 2)
        if nse_quote and nse_quote.get("change_pct") is not None:
            change = round(nse_quote["change_pct"], 2)
        elif global_quote:
            if global_quote.get("change_pct") is not None:
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
    elif sym == "INR=X":
        # USD/INR must have a fresh intraday quote; a daily Yahoo close is not
        # presented as today's live exchange rate when the quote feed is absent.
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


def fetch_usdinr_reference():
    """Daily USD/INR reference rate only; never label it as an intraday quote."""
    try:
        response = requests.get(
            "https://api.frankfurter.dev/v2/rate/usd/inr",
            headers={"User-Agent": "PDMP-Scanner/1.0", "Accept": "application/json"},
            timeout=12
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("base") != "USD" or payload.get("quote") != "INR":
            raise ValueError("Unexpected Frankfurter currency pair")
        rate = float(payload.get("rate"))
        rate_date = dt.date.fromisoformat(str(payload.get("date")))
        age_days = (dt.datetime.now(dt.timezone.utc).date() - rate_date).days
        if not math.isfinite(rate) or rate <= 0 or age_days < 0 or age_days > 3:
            raise ValueError("Frankfurter daily reference rate is invalid or too old")
        print(f"USDINR_REFERENCE: rate={rate:.4f} date={rate_date.isoformat()} source=Frankfurter daily reference (not live)")
        return {
            "reference_price": round(rate, 4),
            "reference_date": rate_date.isoformat(),
            "reference_source": "Frankfurter · दैनिक संदर्भ दर (लाइव नहीं)"
        }
    except Exception as exc:
        print(f"USDINR daily reference unavailable: {str(exc)[:160]}")
        return {"reference_price": None, "reference_date": None, "reference_source": None}


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
                 "गिरावट", "गिरेगा", "गिरेगी", "नीचे", "मंदी", "बेयरिश", "बिकवाली", "टूटेगा", "करेक्शन", "गिरावट"]
# सामान्य/दिशाहीन खोजों को स्पष्ट neutral bucket में रखें; अज्ञात queries को mood में न गिनें।
TQ_NEUTRAL_WORDS = ["today", "live", "price", "news", "chart", "index", "market", "stock",
                    "share", "sensex", "nifty", "bank", "option", "chain", "prediction", "expiry",
                    "what", "meaning", "history", "hours", "volume", "oi", "fii", "dii",
                    "आज", "भाव", "समाचार", "चार्ट", "शेयर", "बाजार", "बाज़ार", "निफ्टी", "सेंसेक्स",
                    "बैंक", "ऑप्शन", "चेन", "भविष्यवाणी"]
TQ_MIN_WEIGHT = 0.01  # कोई भी वास्तविक non-zero reading स्वीकार; शून्य/अनुपलब्ध डेटा अस्वीकार


def tq_dir(q):
    """खोज-वाक्यांश की दिशा: bull/bear/neutral; अस्पष्ट query को None रखें।"""
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
    return None


def tq_weight(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 100.0  # 'Breakout' जैसे मान


def tq_aggregate(queries):
    """असली खोजें (related queries) -> भीड़ का मूड, स्कोर और सूचियाँ।"""
    bull_w = bear_w = 0.0
    crowd_terms, spikes = [], []
    for item in queries.values():
        d = tq_dir(item["term"])
        if d == "bull":
            bull_w += item["weight"]
        elif d == "bear":
            bear_w += item["weight"]
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
        bull_score = round(max(0.0, bull_w - bear_w) / total * 100, 1)
        bear_score = round(max(0.0, bear_w - bull_w) / total * 100, 1)
        neutral_score = round(max(0.0, 100.0 - bull_score - bear_score), 1)
        # Direction label compares bullish vs bearish search interest directly.
        # Residual neutral score measures strength/uncertainty; it is not a vote.
        sentiment = ("BULLISH" if bull_w > bear_w
                     else "BEARISH" if bear_w > bull_w else "NEUTRAL")
    rising_all = [it for it in queries.values() if it.get("rising")]
    return {
        "crowd_bull_pct": pct, "crowd_label": label,
        "bull_sum_pct": round(bull_w, 1), "bear_sum_pct": round(bear_w, 1),
        "min_side_pct": TQ_MIN_WEIGHT,
        "crowd_terms": crowd_terms[:20],
        "spikes": spikes[:10],
        "hidden_spikes": max(0, len(rising_all) - len(spikes)),
        "bull_score_pct": bull_score, "bear_score_pct": bear_score,
        "neutral_score_pct": neutral_score, "sentiment_label": sentiment,
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
                    "30 मिनट से अधिक अलग है"
                )
            for term in chunk:
                recent_ratio, average_ratio = _ratio(df, term, recent_points=recent_points)
                queries[term.lower()] = {
                    "term": term, "weight": round(max(0.0, recent_ratio) * 100, 2),
                    "avg_weight": round(max(0.0, average_ratio) * 100, 2),
                    "rising": False, "direction": direction
                }

    bull_total = sum(x["weight"] for x in queries.values() if x["direction"] == "bull")
    bear_total = sum(x["weight"] for x in queries.values() if x["direction"] == "bear")
    neutral_total = sum(x["weight"] for x in queries.values() if x["direction"] == "neutral")
    if bull_total < TQ_MIN_WEIGHT or bear_total < TQ_MIN_WEIGHT:
        raise ValueError(
            f"Google Trends में तेजी और मंदी दोनों समूहों का वास्तविक non-zero डेटा चाहिए "
            f"(bull={bull_total:.3f}, bear={bear_total:.3f}, minimum={TQ_MIN_WEIGHT})"
        )

    total = bull_total + bear_total + neutral_total
    if total <= 0:
        raise ValueError("Google Trends के तीनों समूहों का कुल डेटा शून्य है")
    bull_pct = bull_total / total * 100
    bear_pct = bear_total / total * 100
    neutral_pct = neutral_total / total * 100
    bull_score = round(bull_pct, 1)
    bear_score = round(bear_pct, 1)
    neutral_score = round(neutral_pct, 1)
    crowd_direction_pct = bull_total / (bull_total + bear_total) * 100
    label = ("ज़्यादातर बुलिश सोच" if crowd_direction_pct >= CROWD_EXTREME
             else "ज़्यादातर बियरिश सोच" if crowd_direction_pct <= CROWD_LOW else "सोच बँटी हुई")
    sentiment = ("BULLISH" if bull_total > bear_total
                 else "BEARISH" if bear_total > bull_total else "NEUTRAL")

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
        "min_side_pct": TQ_MIN_WEIGHT, "crowd_terms": crowd_terms[:20],
        "spikes": [], "hidden_spikes": 0,
        "bull_score_pct": bull_score, "bear_score_pct": bear_score,
        "neutral_score_pct": neutral_score, "sentiment_label": sentiment,
        "today_bull_pct": round(crowd_direction_pct, 1) if timeframe == "now 1-d" else None,
        "today_label": "पिछले 24 घंटे में तेजी बनाम मंदी खोज-रुचि" if timeframe == "now 1-d" else "डेटा उपलब्ध नहीं",
        "today_basis": "now_1d_anchor_relative" if timeframe == "now 1-d" else timeframe + "_anchor_relative",
        "source_timeframe": timeframe,
        "source_data_time": source_data_time,
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

        bull = bear = neutral = 0.0
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
            # अनजान/general queries को mood प्रतिशत में न मिलाएँ; केवल पहचानी दिशा गिनें।
            if direction is None:
                continue
            rows += 1
            if direction == "bull":
                bull += weight
            elif direction == "bear":
                bear += weight
            else:
                neutral += weight
            key = term.casefold()
            entry = {"term": term, "weight": weight, "direction": direction}
            if key not in all_terms or weight > all_terms[key]["weight"]:
                all_terms[key] = entry

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
    if bull_pct < TQ_MIN_WEIGHT or bear_pct < TQ_MIN_WEIGHT:
        raise ValueError(
            f"Google Trends में दोनों दिशाओं की पर्याप्त खोज नहीं "
            f"(bull={bull_pct:.1f}%, bear={bear_pct:.1f}%, minimum={TQ_MIN_WEIGHT}%)"
        )
    if bull_pct >= CROWD_EXTREME:
        label, sentiment = "EXTREMELY BULLISH", "BULLISH"
    elif bear_pct >= CROWD_EXTREME:
        label, sentiment = "EXTREMELY BEARISH", "BEARISH"
    else:
        label, sentiment = "NEUTRAL", "NEUTRAL"

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
        "crowd_bull_pct": round(bull_pct), "crowd_label": label,
        "bull_sum_pct": bull_pct, "bear_sum_pct": bear_pct,
        "min_side_pct": None, "crowd_terms": terms[:20],
        "spikes": [], "hidden_spikes": 0,
        "bull_score_pct": bull_pct, "bear_score_pct": bear_pct,
        "neutral_score_pct": neutral_pct, "sentiment_label": sentiment,
        "today_bull_pct": bull_pct, "today_label": "पिछले 24 घंटे की related searches",
        "today_basis": "now_1d_related_queries" if timeframe == "now 1-d" else "related_queries_other",
        "source_timeframe": timeframe + " related queries",
        "source_data_time": source_data_time,
        "fallback_used": True, "queries_total": len(all_terms),
        "related_seed_count": len(per_seed)
    }


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
    """रिटेल (CLIENT) की इंडेक्स ऑप्शन स्थिति से स्कोर का समायोजन (-2 से +2)।
    CE का Long हिस्सा PE के Long हिस्से से जितना ज़्यादा, उतना बुलिश। (CE% − PE%) ÷ 10, सीमा ±2।
    यह कल का (EOD) डेटा है। न मिले तो 0।"""
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


def main():
    global SKIP_EVENTS
    refresh_mcx_silver_reference()
    refresh_mcx_gold_reference()
    refresh_mcx_crude_reference()
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

    # Add a clearly separate daily reference rate when the intraday FX quote is unavailable.
    # The live price field remains null unless a validated intraday quote exists.
    if "USDINR" in result["instruments"]:
        result["instruments"]["USDINR"].update(fetch_usdinr_reference())

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
    adj, rinfo = retail_adjust(result["participant_oi"])
    for _n in ("NIFTY", "SENSEX", "BANKNIFTY"):
        _d = result["instruments"].get(_n)
        if _d and rinfo is not None:
            _d["headline_score"] = _d["score"]
            _d["retail_adj"] = adj
            _d["score"] = round(_d["score"] + adj, 1)
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
    trends_scan = os.getenv("TRENDS_SCAN", "false").lower() == "true"

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

    # अंतिम इंडेक्स स्कोर: खबरें 40%, Google Trends crowd 40%, NSE CLIENT OI 20%.
    # हर घटक -10..+10 पर सामान्यीकृत है। कोई आवश्यक स्रोत न मिले तो crowd composite
    # का दावा नहीं करें; पुराना news+CLIENT score सुरक्षित रखें।
    fresh_trends = bool(trends.get("ok") and not trends.get("stale"))
    crowd_bull = trends.get("bull_score_pct") if fresh_trends else None
    crowd_bear = trends.get("bear_score_pct") if fresh_trends else None
    crowd_neutral = trends.get("neutral_score_pct") if fresh_trends else None
    crowd_valid = all(
        isinstance(v, (int, float)) and 0 <= v <= 100
        for v in (crowd_bull, crowd_bear, crowd_neutral)
    ) and abs((crowd_bull or 0) + (crowd_bear or 0) + (crowd_neutral or 0) - 100) <= 2
    retail_valid = isinstance(rinfo, dict) and isinstance(adj, (int, float))
    for _n in ("NIFTY", "SENSEX", "BANKNIFTY"):
        _d = result["instruments"].get(_n)
        if not _d:
            continue
        if crowd_valid and retail_valid:
            news_component = max(-10.0, min(10.0, float(_d.get("headline_score", _d.get("score", 0))) * 2))
            crowd_component = max(-10.0, min(10.0, float(crowd_bull - crowd_bear) / 100 * 10))
            retail_component = max(-10.0, min(10.0, float(adj) * 5))
            combined = news_component * 0.40 + crowd_component * 0.40 + retail_component * 0.20
            _d["score"] = round(max(-10.0, min(10.0, combined)), 1)
            _d["score_mode"] = "news_crowd_client"
        else:
            _d["score_mode"] = "news_client_only"
    result["index_score_method"] = {
        "mode": "news_crowd_client" if crowd_valid and retail_valid else "news_client_only",
        "weights": {"news": 40, "crowd": 40, "client": 20},
        "crowd_included": bool(crowd_valid),
        "client_included": bool(retail_valid),
    }

    # अब signal history भी इसी अंतिम स्कोर से बनेगी।
    update_signals(result["instruments"], sig_state, sig_log, updated)
    result["signals"] = {
        "state": signal_summary(sig_state),
        "events": sig_log[-15:],
        "watch": list(SIGNAL_WATCH.keys()),
    }

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