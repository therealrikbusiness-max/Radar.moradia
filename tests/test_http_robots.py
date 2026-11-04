import pytest

from radar_moradia.http import PoliteClient, RobotsRules, SourceBlocked
from tests.conftest import FakeResponse, FakeSession

UA = "RadarMoradia/1.0 (+https://example)"


def test_robots_chavesnamao_real(fixture_text):
    r = RobotsRules.parse(fixture_text("robots_chavesnamao.txt"))
    B = "https://www.chavesnamao.com.br"
    assert r.allowed(UA, B + "/api/mcp")
    assert r.allowed(UA, B + "/api/mcp/")
    assert not r.allowed(UA, B + "/api/outra")
    assert r.allowed(UA, B + "/kitnet-para-alugar/sp-paulinia/")
    assert r.allowed(UA, B + "/kitnet-para-alugar/sp-paulinia/?pg=2")
    assert not r.allowed(UA, B + "/kitnet-para-alugar/sp-paulinia/?pg=3")
    assert not r.allowed(UA, B + "/minhaconta/")
    # Grupos específicos de outros bots não se aplicam ao nosso UA
    assert not r.allowed("HTTrack/3.0", B + "/")


def test_robots_quintoandar_real(fixture_text):
    r = RobotsRules.parse(fixture_text("robots_quintoandar.txt"))
    B = "https://www.quintoandar.com.br"
    assert r.allowed(UA, B + "/alugar/imovel/paulinia-sp-brasil")
    assert not r.allowed(UA, B + "/busca")
    assert not r.allowed(UA, B + "/imovel/123/agendar")


def test_robots_simples():
    r = RobotsRules.parse("User-agent: *\nDisallow: /\nAllow: /public$\n")
    assert not r.allowed(UA, "https://x/qualquer")
    assert r.allowed(UA, "https://x/public")
    assert not r.allowed(UA, "https://x/public/2")


def _client(routes):
    return PoliteClient(UA, min_interval=0, retries=2, session=FakeSession(routes))


def test_robots_403_bloqueia_fonte():
    c = _client({"https://a.com/robots.txt": FakeResponse(403)})
    with pytest.raises(SourceBlocked):
        c.get("https://a.com/pagina")


def test_robots_404_permite():
    c = _client({"https://a.com/robots.txt": FakeResponse(404),
                 "https://a.com/p": FakeResponse(200, "ok")})
    assert c.get("https://a.com/p").text == "ok"


def test_http_403_nao_e_contornado():
    s = FakeSession({"https://a.com/robots.txt": FakeResponse(404),
                     "https://a.com/p": FakeResponse(403, "denied")})
    c = PoliteClient(UA, min_interval=0, session=s)
    with pytest.raises(SourceBlocked):
        c.get("https://a.com/p")
    assert sum(1 for x in s.calls if x[1] == "https://a.com/p") == 1  # sem novas tentativas


def test_captcha_detectado():
    c = _client({"https://a.com/robots.txt": FakeResponse(404),
                 "https://a.com/p": FakeResponse(200, "<div class='g-recaptcha'>captcha</div>")})
    with pytest.raises(SourceBlocked):
        c.get("https://a.com/p")
