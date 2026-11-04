import pytest

from radar_moradia.models import Listing
from radar_moradia.normalize import (detect_caucao, detect_contas, detect_mobiliado,
                                     detect_tipo, fees_from_text, find_phones, normalize,
                                     parse_money, whatsapp_link)


@pytest.mark.parametrize("raw,val", [
    ("R$ 1.100,00", 1100.0), ("R$ 900", 900.0), ("1.300", 1300.0), (950, 950.0),
    ("R$ 2.365,71/mês", 2365.71), ("", None), (None, None), (0, None), ("consulte", None),
])
def test_parse_money(raw, val):
    assert parse_money(raw) == val


def test_fees_reais_e_rateio():
    t = "O VALOR DE 280,00 DE CONDOMÍNIO, REFERE-SE AO RATEIO: SANASA, CPFL, IPTU E INTERNET."
    assert fees_from_text(t)["condominio"] == 280.0
    assert set(detect_contas(t)) == {"agua", "luz", "iptu", "internet"}
    assert fees_from_text("Condomínio: R$ 150,00 e IPTU R$ 35")["iptu"] == 35.0


def test_contas():
    assert detect_contas("Água e luz inclusas no valor") == ["agua", "luz"]
    assert "internet" in detect_contas("Já incluso internet wi-fi")
    assert detect_contas("Contas à parte") == []


@pytest.mark.parametrize("titulo,desc,q,esperado", [
    ("Kitnet para alugar no Centro", "", None, "kitnet"),
    ("Kitnet / Stúdio para alugar", "", None, "kitnet"),
    ("Studio mobiliado", "", None, "studio"),
    ("Casa para alugar", "Edícula nos fundos com 1 quarto", None, "edicula"),
    ("Casa de fundos 1 quarto", "", None, "casa_fundos"),
    ("Casa com 1 dormitório", "", 1, "casa_1_quarto"),
    ("Casa com 3 quartos", "", 3, "casa"),
    ("Sala para alugar, 30 m²", "", None, None),
])
def test_detect_tipo(titulo, desc, q, esperado):
    assert detect_tipo(titulo, desc, q) == esperado


def test_mobiliado():
    assert detect_mobiliado("KIT MOBILIADO para locação") is True
    assert detect_mobiliado("Imóvel não mobiliado") is False
    assert detect_mobiliado("Sem mobília") is False
    assert detect_mobiliado("Kitnet com 1 dormitório") is None


def test_telefones_e_whatsapp():
    t = "Telefone:(19)3289-4325\nCelular: WhatsApp (19) 99795-0079"
    assert find_phones(t) == ["1932894325", "19997950079"]
    assert whatsapp_link("19997950079") == "https://wa.me/5519997950079"
    assert whatsapp_link("+55 (19) 99795-0079") == "https://wa.me/5519997950079"
    assert whatsapp_link("1932894325") is None          # fixo: sem wa.me
    assert whatsapp_link("00999999999") is None          # DDD inválido
    assert find_phones("ref 4348, área 1000,00m2, 32 m2") == []


def test_caucao():
    assert "caução" in detect_caucao("Ótima kitnet. Exige caução de 1 aluguel. Ligue já").lower()
    assert detect_caucao("Ótima kitnet.") is None


def test_normalize_nao_inventa():
    it = normalize(Listing(fonte="x", id_fonte="1", url="u", titulo="Kitnet no Centro", aluguel=800))
    assert it.mobiliado is None and it.caucao is None and it.telefone is None
    assert it.condominio is None and it.total_mensal == 800
    assert it.contas_incluidas == []


def test_total_soma_taxas_conhecidas():
    it = normalize(Listing(fonte="x", id_fonte="1", url="u", titulo="Kitnet", aluguel=800,
                           descricao="Condomínio R$ 150,00. IPTU R$ 20,00"))
    assert it.total_mensal == 970


def test_total_nao_soma_iptu_incluso():
    it = normalize(Listing(fonte="x", id_fonte="1", url="u", titulo="Kitnet", aluguel=800,
                           iptu=30, descricao="IPTU incluso no aluguel"))
    assert it.total_mensal == 800


@pytest.mark.parametrize("titulo,val", [
    ("Kitnet com 1 dormitório para alugar, 14 m² por R$ 1.300,00/mês - Barão Geraldo", 1300.0),
    ("Casa com 1 dormitório para alugar, 40 m² por R$ 1.520,00 - Vila Marieta", 1520.0),
    ("Apartamento, 44 m² - venda por R$ 345.000,00 ou aluguel por R$ 2.365,71/", 2365.71),
    ("Terreno, 2690 m² - venda por R$ 795.000,00 ou alug", None),
    ("Kitnet / Stúdio", None),
])
def test_price_in_title(titulo, val):
    from radar_moradia.normalize import price_in_title
    assert price_in_title(titulo) == val
