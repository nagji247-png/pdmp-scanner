"""Parse TradingView continuous-futures Front month metadata safely.

This module deliberately does not fetch market data or select a contract by OI.
Callers must match the returned contract code against an official MCX FUTCOM row.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re
from datetime import date


_MONTH_CODES = {
    "F": 1,   # January
    "G": 2,   # February
    "H": 3,   # March
    "J": 4,   # April
    "K": 5,   # May
    "M": 6,   # June
    "N": 7,   # July
    "Q": 8,   # August
    "U": 9,   # September
    "V": 10,  # October
    "X": 11,  # November
    "Z": 12,  # December
}


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(data.strip())


def parse_front_month(page_text: str, symbol: str) -> str | None:
    """Return e.g. GOLDZ2026 only when it follows the Front month label."""
    if not isinstance(page_text, str) or not page_text.strip():
        return None
    symbol = str(symbol or "").strip().upper()
    if symbol not in {"GOLD", "SILVER"}:
        return None

    parser = _VisibleText()
    parser.feed(page_text)
    visible = " ".join(parser.parts) if "<" in page_text else page_text
    visible = re.sub(r"\s+", " ", visible)

    match = re.search(
        r"\bFront\s+month\s*:?[ \t\u00a0]*"
        rf"({re.escape(symbol)}[FGHJKMNQUVXZ]\d{{4}})\b",
        visible,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).upper()


def contract_code_month(contract_code: str, symbol: str) -> tuple[int, int] | None:
    """Decode a full-size MCX GOLD/SILVER contract code into (year, month)."""
    symbol = str(symbol or "").strip().upper()
    code = str(contract_code or "").strip().upper()
    if symbol not in {"GOLD", "SILVER"}:
        return None
    match = re.fullmatch(
        rf"{re.escape(symbol)}([FGHJKMNQUVXZ])(\d{{4}})", code
    )
    if not match:
        return None
    month = _MONTH_CODES.get(match.group(1))
    year = int(match.group(2))
    if month is None or not 2000 <= year <= 2099:
        return None
    return year, month


def contract_code_matches_expiry(contract_code: str, symbol: str, expiry: date) -> bool:
    """Match the TradingView contract's month/year to an MCX expiry date."""
    decoded = contract_code_month(contract_code, symbol)
    return bool(decoded and isinstance(expiry, date)
                and decoded == (expiry.year, expiry.month))
