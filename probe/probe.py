"""Sondagem 3: descoberta do servidor MCP oficial do Chaves na Mão."""
import json, pathlib, time
import requests

UA = "RadarMoradia/1.0 (+https://github.com/therealrikbusiness-max/Radar.moradia)"
out = pathlib.Path("probe_out"); out.mkdir(exist_ok=True)
B = "https://www.chavesnamao.com.br"
s = requests.Session(); s.headers["User-Agent"] = UA
def save(name, r):
    (out / name).write_text(f"STATUS {r.status_code}\nHEADERS {dict(r.headers)}\n\n{r.text[:400000]}")
    print(name, r.status_code, len(r.text), flush=True)
for p in ["/.well-known/mcp/server-card.json", "/.well-known/agent-skills/index.json"]:
    save(p.strip("/").replace("/", "_"), s.get(B + p, timeout=30)); time.sleep(3)
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
     "MCP-Protocol-Version": "2025-06-18"}
init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {},
    "clientInfo": {"name": "radar-moradia", "version": "1.0"}}}
r = s.post(B + "/api/mcp/", json=init, headers=H, timeout=30); save("mcp_initialize", r)
sid = r.headers.get("Mcp-Session-Id")
if sid: H["Mcp-Session-Id"] = sid
time.sleep(2)
s.post(B + "/api/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=H, timeout=30)
time.sleep(2)
save("mcp_tools_list", s.post(B + "/api/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=H, timeout=30))
