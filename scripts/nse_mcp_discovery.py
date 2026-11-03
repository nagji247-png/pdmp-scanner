#!/usr/bin/env python3
"""Read-only discovery of the public NSE MCP tool catalogue. No market data is requested."""
import json
import os
import sys
import requests

ENDPOINTS = {
    "CM Market Live": "https://mcp.nseindia.in/cmmkt/mcp",
    "CM Bhavcopy": "https://mcp.nseindia.in/bhavcopy/cm/mcp",
}
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "User-Agent": "Trinetra-Informational-MCP-Discovery/1.0",
}

def parse_payload(response):
    body = response.text.strip()
    if not body:
        return None
    try:
        return response.json()
    except ValueError:
        # Streamable HTTP may return an SSE event containing JSON data.
        for line in body.splitlines():
            if line.startswith("data:"):
                value = line[5:].strip()
                try:
                    return json.loads(value)
                except ValueError:
                    pass
    return {"unparsed_response": body[:4000]}

def rpc(session, endpoint, method, request_id, params=None, session_id=None):
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    headers = dict(HEADERS)
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    response = session.post(endpoint, headers=headers, json=payload, timeout=25)
    print(f"HTTP {response.status_code}; content-type={response.headers.get('content-type')}")
    response.raise_for_status()
    return parse_payload(response), response.headers.get("Mcp-Session-Id")

def inspect(label, endpoint):
    print(f"\n===== {label} =====")
    with requests.Session() as session:
        try:
            init, session_id = rpc(
                session, endpoint, "initialize", 1,
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "trinetra-discovery", "version": "1.0"},
                },
            )
            print("INITIALIZE:")
            print(json.dumps(init, ensure_ascii=False, indent=2)[:6000])
            if isinstance(init, dict) and "error" in init:
                print("Initialize returned an MCP error; skipping tools/list.")
                return
            notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
            h = dict(HEADERS)
            if session_id:
                h["Mcp-Session-Id"] = session_id
            note = session.post(endpoint, headers=h, json=notification, timeout=25)
            print(f"initialized notification HTTP {note.status_code}")
            tools_result, _ = rpc(session, endpoint, "tools/list", 2, {}, session_id)
            print("TOOLS/LIST:")
            print(json.dumps(tools_result, ensure_ascii=False, indent=2)[:18000])
            if isinstance(tools_result, dict) and tools_result.get("result", {}).get("tools") is not None:
                tools = tools_result["result"]["tools"]
                print("TOOL_NAMES:", ", ".join(t.get("name", "?") for t in tools))
        except Exception as exc:
            print(f"DISCOVERY_ERROR: {type(exc).__name__}: {exc}")
            if getattr(exc, "response", None) is not None:
                print("RESPONSE_BODY:", exc.response.text[:3000])

if __name__ == "__main__":
    for label, endpoint in ENDPOINTS.items():
        inspect(label, endpoint)
