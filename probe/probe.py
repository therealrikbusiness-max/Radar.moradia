"""Verificação cruzada: dados do MCP x dados da página pública do anúncio,
capturados na sondagem 1 (JSON-LD de id-30482980: R$ 1450, Kitnet/Stúdio,
Barão Geraldo, Campinas, 1 quarto)."""
import json, pathlib, sys
sys.path.insert(0, ".")
from radar_moradia.http import PoliteClient
from radar_moradia.mcp_client import MCPClient
from radar_moradia.sources.chavesnamao import parse_result

out = pathlib.Path("probe_out"); out.mkdir(exist_ok=True)
http = PoliteClient("RadarMoradia/1.0 (+https://github.com/therealrikbusiness-max/Radar.moradia)", min_interval=3)
mcp = MCPClient(http, "https://www.chavesnamao.com.br/api/mcp/"); mcp.initialize()
esperado = {"id_fonte": "30482980", "aluguel": 1450.0, "bairro": "Barão Geraldo", "municipio": "Campinas", "quartos": 1}
achado, log = None, []
for page in range(1, 21):
    r = mcp.call_tool("search_realty_listings", {"filters": {"transaction": "aluguel", "propertyType": "kitnet",
        "city": "Campinas", "state": "SP", "neighborhood": "Barão Geraldo", "minPrice": 1400, "maxPrice": 1500}, "page": page})
    log.append({"page": page, "pagination": r.get("pagination"), "ids": [x["id"] for x in r["results"]]})
    for x in r["results"]:
        if str(x["id"]) == esperado["id_fonte"]:
            achado = x
    if achado or page >= (r.get("pagination") or {}).get("totalPages", 0):
        break
res = {"esperado": esperado, "mcp_bruto": achado, "log": log}
if achado:
    it = parse_result(achado)
    res["comparacao"] = {k: [v, getattr(it, k), v == getattr(it, k)] for k, v in esperado.items()}
(out / "verificacao.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False, indent=1))
