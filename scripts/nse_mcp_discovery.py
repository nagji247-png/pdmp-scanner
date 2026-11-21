#!/usr/bin/env python3
"""Read-only NSE MCP protocol probe: initialize then one tool call, no notification."""
import json, requests
URL="https://mcp.nseindia.in/cmmkt/mcp"
H={"Content-Type":"application/json","Accept":"application/json, text/event-stream","User-Agent":"Mozilla/5.0 Trinetra diagnostic"}
def decode(r):
    try: return r.json()
    except ValueError:
        for line in r.text.splitlines():
            if line.startswith("data:"):
                try: return json.loads(line[5:].strip())
                except ValueError: pass
    return {"raw":r.text[:5000]}
def probe(name,args):
    print("\nTOOL",name,args)
    with requests.Session() as s:
        init=s.post(URL,headers=H,json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"trinetra-probe","version":"1.4"}}},timeout=30)
        print("INIT",init.status_code,"SESSION",init.headers.get("Mcp-Session-Id"))
        init.raise_for_status()
        h=dict(H)
        if init.headers.get("Mcp-Session-Id"): h["Mcp-Session-Id"]=init.headers["Mcp-Session-Id"]
        r=s.post(URL,headers=h,json={"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":name,"arguments":args}},timeout=40)
        print("TOOL_HTTP",r.status_code)
        print(json.dumps(decode(r),ensure_ascii=False)[:12000])
if __name__=="__main__":
  for n,a in [("cm_get_data_status",{}),("cm_get_index_quote",{"indexName":"NIFTY 50"}),("cm_get_equity_stocks",{"limit":500,"symbolFilter":""})]:
    try: probe(n,a)
    except Exception as e:
      print("ERROR",repr(e))
      if getattr(e,"response",None) is not None: print(e.response.text[:1000])
