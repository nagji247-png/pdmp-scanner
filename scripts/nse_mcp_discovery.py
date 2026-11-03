#!/usr/bin/env python3
"""Read-only NSE MCP diagnostics: fetch one complete CM equity snapshot."""
import json, requests
H={"Content-Type":"application/json","Accept":"application/json, text/event-stream","User-Agent":"Trinetra-ReadOnly-Diagnostic/1.3"}
CM="https://mcp.nseindia.in/cmmkt/mcp"
def main():
  with requests.Session() as s:
    r=s.post(CM,headers=H,json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"trinetra-check","version":"1.3"}}},timeout=30)
    print("INITIALIZE",r.status_code); r.raise_for_status()
    sid=r.headers.get("Mcp-Session-Id"); h=dict(H)
    if sid: h["Mcp-Session-Id"]=sid
    n=s.post(CM,headers=h,json={"jsonrpc":"2.0","method":"notifications/initialized"},timeout=20)
    print("INITIALIZED_NOTIFICATION",n.status_code)
    for i,(name,args) in enumerate([
      ("cm_get_data_status",{}),
      ("cm_get_equity_stocks",{"limit":500,"symbolFilter":""}),
      ("cm_get_index_quote",{"indexName":"NIFTY 50"}),
      ("cm_get_index_quote",{"indexName":"NIFTY BANK"}),
    ],2):
      print("\nTOOL",name,args)
      try:
        q=s.post(CM,headers=h,json={"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":name,"arguments":args}},timeout=45)
        print("HTTP",q.status_code)
        if q.status_code != 200: print(q.text[:1200]); continue
        try: data=q.json()
        except ValueError:
          data={"raw":q.text[:5000]}
        print(json.dumps(data,ensure_ascii=False)[:16000])
      except Exception as e: print("ERROR",repr(e))
if __name__=="__main__": main()
