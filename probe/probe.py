"""Sondagem 4: chamadas reais à ferramenta search_realty_listings (MCP oficial)."""
import json, pathlib, sys, logging
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO)
from radar_moradia.http import PoliteClient
from radar_moradia.mcp_client import MCPClient

out = pathlib.Path("probe_out"); out.mkdir(exist_ok=True)
http = PoliteClient("RadarMoradia/1.0 (+https://github.com/therealrikbusiness-max/Radar.moradia)", min_interval=3)
mcp = MCPClient(http, "https://www.chavesnamao.com.br/api/mcp/")
print(mcp.initialize())
queries = {
  "kit_paulinia": {"filters": {"transaction": "aluguel", "propertyType": "kitnet", "city": "Paulínia", "state": "SP", "maxPrice": 1400}},
  "casa_paulinia": {"filters": {"transaction": "aluguel", "propertyType": "casa", "city": "Paulínia", "state": "SP", "maxPrice": 1400}},
  "todos_paulinia": {"filters": {"transaction": "aluguel", "city": "Paulínia", "state": "SP", "maxPrice": 1400}},
  "kit_barao": {"filters": {"transaction": "aluguel", "propertyType": "kitnet", "city": "Campinas", "state": "SP", "neighborhood": "Barão Geraldo", "maxPrice": 1400}},
  "kit_barao_p2": {"filters": {"transaction": "aluguel", "propertyType": "kitnet", "city": "Campinas", "state": "SP", "neighborhood": "Barão Geraldo", "maxPrice": 1400}, "page": 2},
  "casa_barao": {"filters": {"transaction": "aluguel", "propertyType": "casa", "city": "Campinas", "state": "SP", "neighborhood": "Barão Geraldo", "maxPrice": 1400}},
}
for k, args in queries.items():
    try:
        res = mcp.call_tool("search_realty_listings", args)
    except Exception as e:
        res = {"_erro": repr(e)}
    (out / f"mcp_{k}.json").write_text(json.dumps({"args": args, "headers": mcp.last_headers, "result": res}, ensure_ascii=False, indent=1))
    print(k, str(res)[:300], flush=True)
