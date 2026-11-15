"""Small, dependency-free parsers for official NSE XBRL filing documents.

The SHP taxonomy member names and fact names follow the public NSE XBRL
filings format. The scale guard supports both legacy percentage values and
the post-2025-10-31 fraction representation. Unknown facts stay missing.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

CATEGORY_MEMBERS = {
    "promoter": "ShareholdingOfPromoterAndPromoterGroupMember",
    "public": "PublicShareholdingMember",
    "fii": "InstitutionsForeignMember",
    "dii": "InstitutionsDomesticMember",
    "noninst": "NonInstitutionsMember",
}
PERCENT_FACT = "ShareholdingAsAPercentageOfTotalNumberOfShares"
SHARES_FACT = "NumberOfShares"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _number(value):
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if result != result or abs(result) == float("inf"):
        return None
    return result


def parse_shareholding_xbrl(source) -> dict | None:
    """Return promoter/public/FII/DII percentages from one NSE SHP XML.

    source may be XML bytes/text or a pathlib.Path. Only direct category
    roll-ups are used; contexts with multiple dimensions are ignored to avoid
    adding subcategories to their parent totals.
    """
    try:
        if isinstance(source, Path):
            root = ET.parse(source).getroot()
        elif isinstance(source, bytes):
            root = ET.fromstring(source)
        elif isinstance(source, str):
            root = ET.fromstring(source.encode("utf-8"))
        else:
            return None
    except (ET.ParseError, OSError, ValueError, TypeError):
        return None

    contexts = {}
    for node in root.iter():
        if _local_name(node.tag) != "context":
            continue
        context_id = node.attrib.get("id")
        if not context_id:
            continue
        members = []
        for child in node.iter():
            if _local_name(child.tag) == "explicitMember" and child.text:
                members.append(child.text.strip().rsplit(":", 1)[-1])
        contexts[context_id] = members

    facts = {}
    share_counts = {}
    for node in root.iter():
        name = _local_name(node.tag)
        if name not in (PERCENT_FACT, SHARES_FACT):
            continue
        context_id = node.attrib.get("contextRef")
        members = contexts.get(context_id, [])
        if len(members) > 2:
            continue
        category = next((key for key, member in CATEGORY_MEMBERS.items()
                         if member in members), None)
        if not category:
            continue
        value = _number(node.text)
        if value is None:
            continue
        target = facts if name == PERCENT_FACT else share_counts
        if category not in target:
            target[category] = value

    if not facts:
        return None

    # Legacy NSE XBRL encoded percent values at 100x; V1.1 uses fractions.
    promoter, public = facts.get("promoter"), facts.get("public")
    anchor = (promoter + public) if promoter is not None and public is not None else (promoter if promoter is not None else public)
    scale = 1.0
    if anchor is not None:
        if anchor > 1000:
            scale = 0.01
        elif 0 < anchor < 2:
            scale = 100.0

    result = {f"{key}_pct": round(value * scale, 4)
              for key, value in facts.items()}
    if "promoter" in share_counts:
        result["promoter_shares"] = int(share_counts["promoter"])
    if "public" in share_counts:
        result["public_shares"] = int(share_counts["public"])
    if "promoter" in share_counts and "public" in share_counts:
        result["total_shares"] = int(share_counts["promoter"] + share_counts["public"])
    result["taxonomy"] = next(
        (value for key, value in root.attrib.items() if "schemaRef" in key),
        None,
    )
    result["source"] = "NSE India Corporate Filings · Shareholding Pattern XBRL"
    return result


def filing_xml_url(filing: dict) -> str | None:
    """Return an absolute NSE archive URL only for a real filing XBRL link."""
    if not isinstance(filing, dict):
        return None
    url = filing.get("xbrl")
    if not isinstance(url, str) or not url.strip() or url.strip() in ("-", "null"):
        return None
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://nsearchives.nseindia.com" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return None


def parse_financial_results_comparison(payload: dict) -> dict | None:
    """Parse NSE's filed quarterly results comparison payload.

    Values for income and profit are reported in rupees lakhs by NSE and are
    converted to crore. EPS and ratios retain their reported units. This is a
    filing-summary feed, not a substitute for the complete XBRL statements.
    """
    if not isinstance(payload, dict):
        return None
    rows = payload.get("resCmpData")
    if not isinstance(rows, list):
        return None
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        end_date = row.get("re_to_dt")
        if not end_date:
            continue

        def amount(key):
            value = _number(row.get(key))
            return round(value / 100.0, 4) if value is not None else None

        parsed.append({
            "period_end": end_date,
            "period_start": row.get("re_from_dt"),
            "revenue_cr": amount("re_total_inc") if amount("re_total_inc") is not None else amount("re_net_sale"),
            "net_profit_cr": amount("re_net_profit") if amount("re_net_profit") is not None else amount("re_proloss_ord_act"),
            "eps": _number(row.get("re_basic_eps_for_cont_dic_opr")) if _number(row.get("re_basic_eps_for_cont_dic_opr")) is not None else _number(row.get("re_basic_eps")),
            "debt_equity": _number(row.get("re_debt_eqt_rat")),
            "face_value": _number(row.get("re_face_val")),
            "audited_status": row.get("re_res_type"),
            "source": "NSE India Corporate Filings · Financial Results comparison",
            "amount_unit": "₹ Crore (converted from NSE ₹ Lakhs)",
        })
    if not parsed:
        return None
    parsed.sort(key=lambda item: _parse_filing_date(item.get("period_end")), reverse=True)
    return {
        "latest": parsed[0],
        "quarters": parsed[:8],
        "source": "NSE India Corporate Filings · Financial Results comparison",
        "note": "Quarterly filing summary; not full balance sheet/cash flow XBRL.",
    }


def _parse_filing_date(value):
    raw = str(value or "")
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return __import__("datetime").datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return __import__("datetime").date.min
