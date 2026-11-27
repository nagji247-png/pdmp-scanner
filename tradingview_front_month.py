"""Parse TradingView continuous-futures Front month metadata safely.

This module reads only TradingView's explicit Front month label. It never
infers the contract from the nearest-contract list or from open interest.
The matching quote must still come from an official MCX FUTCOM row.
"""
from __future__ import annotations

from html.parser import HTMLParser
from datetime import date
import re


_MONTH_CODES = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}
_TRADINGVIEW_URLS = {
    "GOLD": "https://in.tradingview.com/symbols/MCX-GOLD1%21/",
    "SILVER": "https://in.tradingview.com/symbols/MCX-SILVER1%21/",
}


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(data.strip())


def parse_front_month(page_text: str, symbol: str) -> str | None:
    """Return a code only when it immediately follows the explicit Front month label."""
    if not isinstance(page_text, str) or not page_text.strip():
        return None
    symbol = str(symbol or "").strip().upper()
    if symbol not in _TRADINGVIEW_URLS:
        return None
    parser = _VisibleText()
    parser.feed(page_text)
    visible = " ".join(parser.parts) if "<" in page_text else page_text
    visible = re.sub(r"\s+", " ", visible)
    match = re.search(
        r"\bFront\s+month\s*:?[ \t\u00a0]*"
        rf"({re.escape(symbol)}[FGHJKMNQUVXZ]\d{{4}})\b",
        visible, flags=re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def fetch_front_month_code(symbol: str, http_get, timeout: int = 12) -> str | None:
    """Fetch one public TradingView page and read its explicit Front month code."""
    symbol = str(symbol or "").strip().upper()
    url = _TRADINGVIEW_URLS.get(symbol)
    if not url or not callable(http_get):
        return None
    try:
        response = http_get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TRINETRA/1.0)"},
            timeout=timeout,
        )
        response.raise_for_status()
        return parse_front_month(response.text, symbol)
    except Exception:
        # A failed or blocked metadata request must never trigger an OI fallback.
        return None


def contract_code_month(contract_code: str, symbol: str) -> tuple[int, int] | None:
    """Decode a full-size MCX GOLD/SILVER code into (year, month)."""
    symbol = str(symbol or "").strip().upper()
    code = str(contract_code or "").strip().upper()
    if symbol not in _TRADINGVIEW_URLS:
        return None
    match = re.fullmatch(rf"{re.escape(symbol)}([FGHJKMNQUVXZ])(\d{{4}})", code)
    if not match:
        return None
    year = int(match.group(2))
    if not 2000 <= year <= 2099:
        return None
    return year, _MONTH_CODES[match.group(1)]


def contract_code_matches_expiry(contract_code: str, symbol: str, expiry: date) -> bool:
    decoded = contract_code_month(contract_code, symbol)
    return bool(decoded and isinstance(expiry, date)
                and decoded == (expiry.year, expiry.month))


def select_front_month_quote(quotes: list[dict], symbol: str,
                             front_month_code: str | None) -> dict | None:
    """Select exactly one matching official MCX quote; no OI/nearest-expiry fallback."""
    symbol = str(symbol or "").strip().upper()
    if symbol not in _TRADINGVIEW_URLS or not front_month_code:
        return None
    matches = []
    for quote in quotes or []:
        if not isinstance(quote, dict) or not quote.get("expiry"):
            continue
        row_symbol = str(quote.get("symbol") or "").strip().upper()
        if row_symbol and row_symbol != symbol:
            continue
        try:
            expiry = date.fromisoformat(str(quote["expiry"]))
        except (TypeError, ValueError):
            continue
        if contract_code_matches_expiry(front_month_code, symbol, expiry):
            matches.append(quote)
    return matches[0] if len(matches) == 1 else None
