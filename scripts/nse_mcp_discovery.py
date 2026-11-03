#!/usr/bin/env python3
"""Read-only NSE MCP quote diagnostics. Each tool call gets a fresh MCP session."""
import json
import requests

H={"Content-Type":"application/json","Accept":"application/json, text/event-stream","User-Agent":"Trinetra-ReadOnly-Diagnostic/1.2"}
CM="https://mcp.nseindia.in/cmmkt/mcp"
BH="https://mcp.nseindia.in/bhavcopy/cm/mcp"

def payload(r):
    try: return r.json()
    except ValueError:
        for line in r.text.splitlines():
            if line.startswith("data:"):
                try: return json.loads(line[5:].strip())
                except ValueError: pass
    return {"text":r.text[:4000]}

def call(url,name,args):
    print("\n###",name,args)
    try:
        with requests.Session() as s:
            r=s.post(url,headers=H,json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"trinetra-check","version":"1.2"}}},timeout=30)
            print("init",r.status_code); r.raise_for_status()
            sid=r.headers.get("Mcp-Session-Id")
            h=dict(H)
            if sid: h["Mcp-Session-Id"]=sid
            n=s.post(url,headers=h,json={"jsonrpc":"2.0","method":"notifications/initialized"},timeout=20)
            print("notification",n.status_code)
            r=s.post(url,headers=h,json={"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":name,"arguments":args}},timeout=40)
            print("call",r.status_code); r.raise_for_status()
            print(json.dumps(payload(r),ensure_ascii=False)[:8000])
    except Exception as e:
        print("ERROR",type(e).__name__,str(e))
        if getattr(e,"response",None) is not None: print(e.response.text[:1500])

if __name__=="__main__":
    for name,args in [
      ("cm_get_data_status",{}),
      ("cm_get_index_quote",{"indexName":"NIFTY 50"}),
      ("cm_get_index_quote",{"indexName":"NIFTY BANK"}),
      ("cm_get_stock_quote",{"symbol":"RELIANCE"}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":"HDFCBANK"}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":"TMPV"}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":"HINDALCO"}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":"ADANIPORTS"}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":"COALINDIA"}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":"EICHERMOT"}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":"APOLLOHOSP"}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":"SBIN"}),
    ]: call(CM,name,args)
    call(BH,"get_bulk_quote",{"symbols":["RELIANCE","HDFCBANK","TMPV","HINDALCO","ADANIPORTS","COALINDIA","EICHERMOT","APOLLOHOSP","SBIN"]})
