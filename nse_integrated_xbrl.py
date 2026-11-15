"""Conservative parser for NSE Integrated Filing - Financials XBRL instances.

Reporting periods are classified from context dates, and dimensional segment
contexts are excluded from company-wide totals. Unknown tags and missing facts
remain absent; no values are inferred from narrative text.
Monetary INR facts are converted from absolute rupees to ₹ crore.
"""
from __future__ import annotations

import datetime as dt
import math
import xml.etree.ElementTree as ET

# Legacy labels are only a fallback for malformed/undated contexts. Real
# instances are classified from their reporting dates, not contextRef names.
LEGACY_CONTEXTS = {"OneD": "quarter", "FourD": "ytd", "OneI": "balance_sheet", "PY_I": "prior_balance_sheet"}

MONEY_TAGS = {
    "RevenueFromOperations": "revenue",
    "OtherIncome": "other_income",
    "Income": "total_income",
    "Expenses": "total_expenses",
    "ProfitBeforeTax": "profit_before_tax",
    "ProfitLossForPeriod": "net_profit",
    # Assets is the actual balance-sheet asset fact. EquityAndLiabilities is
    # deliberately not treated as Assets, even though totals should reconcile.
    "Assets": "total_assets",
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

    context_records = {}
    for node in root.iter():
        if _local(node.tag) != "context":
            continue
        cid = node.attrib.get("id")
        if not cid:
            continue
        # Company-wide totals must not accidentally use segment/dimensional facts.
        if any(_local(part.tag) in ("segment", "scenario") and
               any(_local(desc.tag) in ("explicitMember", "typedMember") for desc in part.iter())
               for part in node.iter()):
            continue
        period = next((child for child in node if _local(child.tag) == "period"), None)
        if period is None:
            continue
        dates = {_local(child.tag): (child.text or "").strip() for child in period}
        context_records[cid] = dates

    if not context_records:
        return None

    def as_date(value):
        try:
            return dt.date.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    # XBRL context IDs are arbitrary. Classify from actual reporting periods.
    classified = {}
    instant_dates = []
    duration_records = []
    for cid, dates in context_records.items():
        instant = as_date(dates.get("instant"))
        start = as_date(dates.get("startDate"))
        end = as_date(dates.get("endDate"))
        if instant:
            instant_dates.append((instant, cid))
        elif start and end and end >= start:
            duration_records.append((start, end, cid))

    if instant_dates:
        unique_instants = sorted({item[0] for item in instant_dates}, reverse=True)
        latest_instant = unique_instants[0]
        prior_instant = unique_instants[1] if len(unique_instants) > 1 else None
        for instant, cid in instant_dates:
            if instant == latest_instant:
                classified[cid] = "balance_sheet"
            elif prior_instant and instant == prior_instant:
                classified[cid] = "prior_balance_sheet"

    duration_groups = {"quarter": [], "ytd": []}
    for start, end, cid in duration_records:
        days = (end - start).days + 1
        if 60 <= days <= 120:
            duration_groups["quarter"].append((end, cid))
        elif 150 <= days <= 300:
            duration_groups["ytd"].append((end, cid))

    for category, records in duration_groups.items():
        if records:
            latest_end = max(item[0] for item in records)
            for end, cid in records:
                if end == latest_end:
                    classified[cid] = category

    # Conservative compatibility fallback for known legacy IDs only.
    for cid in context_records:
        if cid not in classified and cid in LEGACY_CONTEXTS:
            classified[cid] = LEGACY_CONTEXTS[cid]

    contexts = {cid: context_records[cid] for cid in classified}
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
        result["periods"][classified[cid]] = dates

    for tag, field in MONEY_TAGS.items():
        if tag in facts:
            for cid, value in facts[tag].items():
                result.setdefault(classified[cid], {})[field + "_cr"] = round(value / 10000000.0, 6)
    for tag, field in PER_SHARE_TAGS.items():
        if tag in facts:
            for cid, value in facts[tag].items():
                result.setdefault(classified[cid], {})[field] = value

    # No debt/equity ratio is inferred: financial liabilities are not identical to borrowings.

    result["raw_facts"] = {
        tag: {classified[cid]: value for cid, value in values.items()}
        for tag, values in facts.items()
    }
    result["taxonomy"] = next(((node.attrib.get("href") or node.attrib.get("{http://www.w3.org/1999/xlink}href"))
                               for node in root.iter() if _local(node.tag) == "schemaRef"), None)
    return result
