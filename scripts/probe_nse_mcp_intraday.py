#!/usr/bin/env python3
"""Read-only probe of NSE MCP equity quote coverage; never writes production data."""
import datetime as dt
import json
import sys
from pathlib import Path

# The script lives under scripts/; expose the repository root for importing the scanner.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_and_score as scanner

TOOL = "cm_get_equity_stocks"
REPORT = {
    "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "tool": TOOL,
    "status": "not_run",
    "schema": None,
    "request_arguments": None,
    "row_count": 0,
    "unique_symbols": 0,
    "cm_eq_rows": 0,
    "timestamped_rows": 0,
    "latest_exchange_timestamp": None,
    "parser_accepted_rows": 0,
    "pagination_fields": [],
    "page_probe_count": 0,
    "pages": [],
    "errors": [],
}


def sample_value(name, spec):
    if "default" in spec:
        return spec["default"]
    enum = spec.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    kind = spec.get("type")
    if name.lower() in {"limit", "pagesize", "page_size", "count"}:
        maximum = spec.get("maximum")
        return min(int(maximum), 500) if isinstance(maximum, (int, float)) else 500
    if name.lower() in {"symbolfilter", "symbol_filter", "search", "query"}:
        return ""
    if kind == "integer":
        minimum = spec.get("minimum", 0)
        return max(0, int(minimum))
    if kind == "number":
        return max(0, float(spec.get("minimum", 0)))
    if kind == "boolean":
        return False
    if kind == "string":
        return ""
    return None


def get_rows(payload):
    if isinstance(payload, dict):
        for key in ("stocks", "data", "rows", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []
    return payload if isinstance(payload, list) else []


def main():
    schema = scanner.nse_mcp_list_tool_schema(TOOL)
    if not isinstance(schema, dict):
        raise RuntimeError("NSE MCP tools/list did not return a usable schema")
    REPORT["schema"] = schema
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    args = {}
    for key in required:
        spec = properties.get(key, {})
        value = sample_value(key, spec if isinstance(spec, dict) else {})
        if value is None:
            raise RuntimeError("Cannot safely construct required NSE MCP argument: " + key)
        args[key] = value
    # Use only fields explicitly advertised by the live schema.
    for key, spec in properties.items():
        low = key.lower()
        if low in {"limit", "symbolfilter", "symbol_filter"} and key not in args:
            value = sample_value(key, spec if isinstance(spec, dict) else {})
            if value is not None:
                args[key] = value
    REPORT["request_arguments"] = args

    pagination = []
    for key in properties:
        low = key.lower()
        if low in {"offset", "start", "startindex", "start_index", "page", "pagenumber", "page_number", "pageno", "page_no"}:
            pagination.append(key)
    REPORT["pagination_fields"] = pagination

    payload = scanner._nse_mcp_call_http(TOOL, args)
    rows = get_rows(payload)
    REPORT["page_probe_count"] = 1
    REPORT["pages"].append({"arguments": args, "rows": len(rows)})
    all_rows = list(rows)

    # Probe one additional page only when the live schema explicitly advertises
    # a pagination field. No guessed/undocumented argument names are sent.
    if rows and pagination:
        key = pagination[0]
        spec = properties.get(key) or {}
        low = key.lower()
        if low in {"page", "pagenumber", "page_number", "pageno", "page_no"}:
            next_value = 2
        else:
            limit = next((int(v) for k, v in args.items() if k.lower() in {"limit", "pagesize", "page_size"} and isinstance(v, (int, float))), len(rows))
            next_value = limit
        page_args = dict(args)
        page_args[key] = next_value
        next_payload = scanner._nse_mcp_call_http(TOOL, page_args)
        next_rows = get_rows(next_payload)
        REPORT["page_probe_count"] = 2
        REPORT["pages"].append({"arguments": page_args, "rows": len(next_rows)})
        known = {str(x.get("symbol") or "").upper() for x in all_rows if isinstance(x, dict)}
        all_rows.extend(x for x in next_rows if isinstance(x, dict) and str(x.get("symbol") or "").upper() not in known)

    symbols = {str(x.get("symbol") or "").upper() for x in all_rows if isinstance(x, dict) and x.get("symbol")}
    cm_eq = [x for x in all_rows if isinstance(x, dict)
             and str(x.get("type") or "").upper() == "CM"
             and str(x.get("series") or "").upper() == "EQ"]
    stamped = [x for x in cm_eq if x.get("latestTimestamp")]
    REPORT["row_count"] = len(all_rows)
    REPORT["unique_symbols"] = len(symbols)
    REPORT["cm_eq_rows"] = len(cm_eq)
    REPORT["timestamped_rows"] = len(stamped)
    REPORT["latest_exchange_timestamp"] = max(
        (str(x.get("latestTimestamp")) for x in stamped), default=None
    )
    if symbols:
        parsed = scanner.parse_nse_mcp_equity_stocks(all_rows, symbols)
        REPORT["parser_accepted_rows"] = parsed["coverage"]["matched"]
        REPORT["parser_source_timestamp"] = parsed.get("source_timestamp")
    REPORT["status"] = "ok" if rows else "empty_response"
    REPORT["total_metadata"] = {
        key: payload.get(key) for key in ("total", "totalCount", "count", "hasMore", "nextPage", "page", "limit")
        if isinstance(payload, dict) and key in payload
    }
    REPORT["interpretation"] = (
        "Pagination is advertised by the live schema; one extra page was probed."
        if pagination else
        "No explicit pagination field was advertised by the live schema; full-universe coverage is not established."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        REPORT["status"] = "error"
        REPORT["errors"].append(str(exc)[:600])
    Path("nse-mcp-intraday-source-probe.json").write_text(
        json.dumps(REPORT, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(REPORT, ensure_ascii=False, indent=2, default=str))
