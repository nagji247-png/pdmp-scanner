"""Conservative parser for NSE Integrated Filing - Financials XBRL instances.

Only the four standard non-dimensional contexts are mapped. Unknown tags and
missing facts remain absent; no values are inferred from narrative text.
Monetary INR facts are converted from absolute rupees to ₹ crore.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

CONTEXTS = {"OneD": "quarter", "FourD": "ytd", "OneI": "balance_sheet", "PY_I": "prior_balance_sheet"}

MONEY_TAGS = {
    "RevenueFromOperations": "revenue",
    "OtherIncome": "other_income",
    "Income": "total_income",
    "Expenses": "total_expenses",
    "ProfitBeforeTax": "profit_before_tax",
    "ProfitLossForPeriod": "net_profit",
    "EquityAndLiabilities": "total_assets",
    "Equity": "total_equity",
    "CurrentFinancialLiabilities": "current_financial_liabilities",
    "NoncurrentFinancialLiabilities": "noncurrent_financial_liabilities",
    "CurrentAssets": "current_assets",
    "NoncurrentAssets": "noncurrent_assets",
    "Inventories": "inventories",
    "TradeReceivablesCurrent": "trade_receivables",
    "TradePayablesCurrent": "trade_payables",
    "PropertyPlantAndEquipment": "property_plant_equipment",
    "CashAndCashEquivalents": "cash_and_cash_equivalents",
    "PaidUpValueOfEquityShareCapital": "paid_up_equity",
}
PER_SHARE_TAGS = {
    "BasicEarningsLossPerShareFromContinuingOperations": "basic_eps",
    "DilutedEarningsLossPerShareFromContinuingOperations": "diluted_eps",
    "FaceValueOfEquityShareCapital": "face_value",
}


def _local(tag):
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _number(value):
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_integrated_financial_xbrl(source):
    """Parse one NSE IFIndAs XBRL XML string/bytes into conservative fields."""
    try:
        root = ET.fromstring(source.encode("utf-8") if isinstance(source, str) else source)
    except (ET.ParseError, TypeError, ValueError, AttributeError):
        return None

    units = {}
    for node in root.iter():
        if _local(node.tag) != "unit":
            continue
        unit_id = node.attrib.get("id")
        measures = [(child.text or "").strip().split(":")[-1].upper()
                    for child in node.iter() if _local(child.tag) == "measure"]
        if unit_id:
            units[unit_id] = measures

    contexts = {}
    for node in root.iter():
        if _local(node.tag) != "context":
            continue
        cid = node.attrib.get("id")
        if cid not in CONTEXTS:
            continue
        period = next((child for child in node if _local(child.tag) == "period"), None)
        if period is None:
            continue
        dates = {_local(child.tag): (child.text or "").strip() for child in period}
        contexts[cid] = dates

    if not contexts:
        return None

    facts = {}
    for node in list(root):
        context_id = node.attrib.get("contextRef")
        if context_id not in contexts or node.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
            continue
        tag = _local(node.tag)
        value = _number(node.text)
        if value is None:
            continue
        unit_ref = node.attrib.get("unitRef")
        measures = units.get(unit_ref, []) if unit_ref else []
        # These fields are displayed in INR. Never relabel USD or unknown
        # currencies as rupees; retain only facts with a verified INR unit.
        if tag in MONEY_TAGS and "INR" not in measures:
            continue
        if tag in PER_SHARE_TAGS and "INR" not in measures:
            continue
        facts.setdefault(tag, {})[context_id] = value

    if not facts:
        return None

    result = {"periods": {}, "source": "NSE India · Integrated Filing - Financials XBRL",
              "unit": "₹ Crore for monetary values; ₹ per share for EPS"}
    for cid, dates in contexts.items():
        result["periods"][CONTEXTS[cid]] = dates

    for tag, field in MONEY_TAGS.items():
        if tag in facts:
            for cid, value in facts[tag].items():
                result.setdefault(CONTEXTS[cid], {})[field + "_cr"] = round(value / 10000000.0, 6)
    for tag, field in PER_SHARE_TAGS.items():
        if tag in facts:
            for cid, value in facts[tag].items():
                result.setdefault(CONTEXTS[cid], {})[field] = value

    # No debt/equity ratio is inferred: financial liabilities are not identical to borrowings.

    result["raw_facts"] = {
        tag: {CONTEXTS[cid]: value for cid, value in values.items()}
        for tag, values in facts.items()
    }
    result["taxonomy"] = next(((node.attrib.get("href") or node.attrib.get("{http://www.w3.org/1999/xlink}href"))
                               for node in root.iter() if _local(node.tag) == "schemaRef"), None)
    return result
