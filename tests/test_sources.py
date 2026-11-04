import json

from radar_moradia.http import PoliteClient
from radar_moradia.sources.chavesnamao import ChavesNaMaoMCP, parse_result
from radar_moradia.sources.vrsync_feed import VRSyncFeed, parse_feed
from tests.conftest import FakeResponse, FakeSession

UA = "RadarMoradia/1.0 (+https://example)"


def test_parse_result_real(fixture_json):
    r = fixture_json("mcp_kit_barao.json")["result"]["results"][0]
    it = parse_result(r)
    assert it.id_fonte == "39390422"
    assert it.aluguel == 1300.0
    assert it.bairro == "Barão Geraldo" and it.municipio == "Campinas"
    assert it.quartos == 1 and it.area_m2 == 14.0
    assert it.tipo == "kitnet"
    assert it.url.startswith("https://www.chavesnamao.com.br/imovel/")
    # O MCP não publica estes dados: devem continuar desconhecidos
    assert it.telefone is None and it.caucao is None and it.mobiliado is None


def test_parse_result_comercial(fixture_json):
    rs = fixture_json("mcp_todos_paulinia.json")["result"]["results"]
    tipos = {parse_result(r).tipo for r in rs}
    assert "comercial_ou_outro" in tipos
    zero = [parse_result(r) for r in rs if r.get("priceBRL") == 0]
    assert zero and all(z.aluguel is None for z in zero)  # preço 0 = não publicado


def _mcp_server(pages_by_query, robots_status=200, robots_text="User-agent: *\nAllow: /api/mcp\n"):
    """Simula o servidor MCP. pages_by_query: dict cidade -> lista de payloads por página."""
    def post(url, body, headers):
        m = body.get("method")
        if m == "initialize":
            return FakeResponse(200, json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {
                "protocolVersion": "2025-06-18"}}), {"Content-Type": "application/json"})
        if m == "notifications/initialized":
            return FakeResponse(202, "")
        args = body["params"]["arguments"]
        key = args["filters"].get("neighborhood") or args["filters"]["city"]
        pages = pages_by_query[key]
        payload = pages[args.get("page", 1) - 1]
        return FakeResponse(200, json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}]}}),
            {"Content-Type": "application/json", "x-ratelimit-remaining": "50"})
    routes = {"https://www.chavesnamao.com.br/robots.txt": FakeResponse(robots_status, robots_text)}
    return FakeSession(routes, post)


def test_chavesnamao_fetch_paginado(fixture_json):
    real = fixture_json("mcp_kit_barao.json")["result"]
    p1 = fixture_json("mcp_todos_paulinia.json")["result"]
    p1 = dict(p1, pagination={"page": 1, "pageSize": 15, "totalResults": 16, "totalPages": 2})
    p2 = dict(real, pagination={"page": 2, "pageSize": 15, "totalResults": 16, "totalPages": 2})
    s = _mcp_server({"Paulínia": [p1, p2]})
    src = ChavesNaMaoMCP(PoliteClient(UA, min_interval=0, session=s),
                         {"consultas": [{"filters": {"transaction": "aluguel", "city": "Paulínia"}}]})
    res = src.fetch()
    assert res.ok and res.paginas == 2 and res.cobertura_completa
    assert "39390422" in res.ids_vistos and len(res.listings) == 16


def test_chavesnamao_bloqueado_por_robots():
    s = _mcp_server({}, robots_text="User-agent: *\nDisallow: /api/\n")
    src = ChavesNaMaoMCP(PoliteClient(UA, min_interval=0, session=s),
                         {"consultas": [{"filters": {"city": "Paulínia"}}]})
    res = src.fetch()
    assert res.bloqueada and not res.ok and res.listings == []
    assert not any(c[0] == "POST" for c in s.calls)  # nem tentou


def test_chavesnamao_erro_ferramenta():
    def post(url, body, headers):
        if body.get("method") == "initialize":
            return FakeResponse(200, '{"jsonrpc":"2.0","id":1,"result":{}}', {"Content-Type": "application/json"})
        if body.get("method") == "notifications/initialized":
            return FakeResponse(202, "")
        return FakeResponse(200, json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {
            "isError": True, "content": [{"type": "text", "text": "invalid filters"}]}}),
            {"Content-Type": "application/json"})
    s = FakeSession({"https://www.chavesnamao.com.br/robots.txt": FakeResponse(404)}, post)
    res = ChavesNaMaoMCP(PoliteClient(UA, min_interval=0, session=s),
                         {"consultas": [{"filters": {"city": "X"}}]}).fetch()
    assert not res.ok and not res.cobertura_completa and "invalid filters" in res.erros[0]


def test_sse_response():
    from radar_moradia.mcp_client import MCPClient
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":1}}\n\n'
    assert MCPClient._parse_body(body, "text/event-stream")["result"] == {"ok": 1}


VRSYNC = """<?xml version="1.0" encoding="UTF-8"?>
<ListingDataFeed xmlns="http://www.vivareal.com/schemas/1.0/VRSync">
 <Listings>
  <Listing>
   <ListingID>K-77</ListingID>
   <Title>Kitnet mobiliada no Centro</Title>
   <TransactionType>For Rent</TransactionType>
   <DetailViewUrl>https://imob.example/imovel/K-77</DetailViewUrl>
   <ListDate>2026-10-01</ListDate>
   <Details>
     <PropertyType>Residential / Kitnet</PropertyType>
     <Description>Kitnet mobiliada, agua e luz inclusas. Caucao de 1 aluguel.</Description>
     <RentalPrice currency="BRL">850</RentalPrice>
     <PropertyAdministrationFee currency="BRL">50</PropertyAdministrationFee>
     <YearlyTax currency="BRL">240</YearlyTax>
     <LivingArea unit="square metres">25</LivingArea>
     <Bedrooms>1</Bedrooms>
   </Details>
   <Location><City>Paulínia</City><Neighborhood>Centro</Neighborhood><Address>Rua X</Address></Location>
   <ContactInfo><Name>Imob Exemplo</Name><Telephone>(19) 98888-7777</Telephone></ContactInfo>
  </Listing>
  <Listing>
   <ListingID>V-1</ListingID><Title>Casa à venda</Title><TransactionType>For Sale</TransactionType>
   <DetailViewUrl>https://imob.example/imovel/V-1</DetailViewUrl>
  </Listing>
 </Listings>
</ListingDataFeed>""".encode("utf-8")


def test_vrsync_parse():
    items = parse_feed(VRSYNC, "imob")
    assert len(items) == 1
    it = items[0]
    assert (it.id_fonte, it.aluguel, it.condominio, it.iptu) == ("K-77", 850, 50, 20)
    assert it.bairro == "Centro" and it.municipio == "Paulínia" and it.telefone == "19988887777"
    assert it.data_publicacao == "2026-10-01" and it.tipo == "kitnet"


def test_vrsync_fetch_e_xml_quebrado():
    s = FakeSession({"https://imob.example/robots.txt": FakeResponse(404),
                     "https://imob.example/feed.xml": FakeResponse(200, "", content=VRSYNC),
                     "https://imob.example/ruim.xml": FakeResponse(200, "", content=b"nada")})
    c = PoliteClient(UA, min_interval=0, session=s)
    ok = VRSyncFeed(c, {"nome": "imob", "urls": ["https://imob.example/feed.xml"]}).fetch()
    assert ok.ok and len(ok.listings) == 1
    bad = VRSyncFeed(c, {"nome": "imob", "urls": ["https://imob.example/ruim.xml"]}).fetch()
    assert not bad.ok and bad.erros
