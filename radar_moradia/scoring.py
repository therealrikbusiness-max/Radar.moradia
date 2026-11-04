"""Filtros (preço, região, tipo) e classificação das oportunidades."""
from __future__ import annotations

import re
from typing import Optional

from .models import Listing
from .normalize import norm

CAT_PRIORIDADE = "prioridade"     # total <= prioridade_max
CAT_ELEGIVEL = "elegivel"         # prioridade_max < total <= teto
CAT_EXCEPCIONAL = "excepcional"   # acima do teto, mas muito bom (seção separada)
CAT_VERIFICAR = "verificar"       # preço do título dentro do teto, mas diverge do preço do anúncio
CAT_DESCARTADO = "descartado"


def match_regiao(item: Listing, cfg: dict) -> tuple[Optional[str], int]:
    """Retorna (nome da região, peso). (None, -1) = fora da área."""
    mun = norm(item.municipio)
    municipios = [norm(m) for m in cfg["municipios"]]
    if not any(m in mun for m in municipios):
        return None, -1
    texto_bairro = norm(f"{item.bairro or ''} {item.endereco or ''}")
    for reg in cfg["regioes"]:
        if norm(reg["municipio"]) not in mun:
            continue
        for ap in reg["apelidos"]:
            if re.search(rf"\b{re.escape(norm(ap))}\b", texto_bairro):
                return reg["nome"], int(reg["peso"])
    if "paulinia" in mun:
        return (item.bairro or "Paulínia (bairro não informado)"), int(
            cfg.get("peso_bairro_nao_listado_paulinia", 5))
    # Campinas fora de Barão Geraldo e arredores: descarta
    return None, -1


def score(item: Listing, cfg: dict) -> Listing:
    """Aplica filtros e calcula pontuação 0–100 com motivos legíveis."""
    orc = cfg["orcamento"]
    motivos: list[str] = []
    pts = 0

    regiao, peso = match_regiao(item, cfg)
    item.regiao = regiao
    if peso < 0:
        item.categoria = CAT_DESCARTADO
        item.motivos = [f"fora da área ({item.bairro or '?'} / {item.municipio or '?'})"]
        item.pontuacao = 0
        return item
    pts += peso
    motivos.append(f"região: {regiao} (+{peso})")

    if item.tipo not in cfg["tipos_aceitos"]:
        item.categoria = CAT_DESCARTADO
        item.motivos = [f"tipo não procurado ({item.tipo or 'desconhecido'})"]
        item.pontuacao = 0
        return item
    pts += 15
    motivos.append(f"tipo: {item.tipo} (+15)")

    total = item.total_mensal
    if total is None:
        item.categoria = CAT_DESCARTADO
        item.motivos = ["preço não publicado"]
        return item

    # Preço: até 30 pontos (quanto mais barato, melhor)
    if total <= orc["prioridade_max"]:
        p = 30
    elif total <= orc["teto"]:
        p = 18
    else:
        p = max(0, 10 - int((total - orc["teto"]) / 50))
    pts += p
    motivos.append(f"total R$ {total:,.0f} (+{p})".replace(",", "."))

    if item.mobiliado:
        pts += 10
        motivos.append("mobiliado (+10)")
    contas = set(item.contas_incluidas)
    bonus_contas = 0
    for c, v in (("agua", 3), ("luz", 4), ("internet", 3)):
        if c in contas:
            bonus_contas += v
    if bonus_contas:
        pts += bonus_contas
        motivos.append(f"contas incluídas: {', '.join(sorted(contas))} (+{bonus_contas})")

    t = norm(f"{item.titulo} {item.descricao}")
    if re.search(r"geladeira|frigobar|frigo bar|refrigerador", t):
        pts += 3; motivos.append("geladeira/frigobar citado (+3)")
    if re.search(r"fogao|cooktop", t):
        pts += 2; motivos.append("fogão/cooktop citado (+2)")
    if re.search(r"(sem|nao exige|dispensa) (fiador|caucao)|sem burocracia|caucao facilitad|caucao parcelad", t):
        pts += 5; motivos.append("garantia facilitada citada (+5)")
    if re.search(r"individual|independente|entrada independente|privativ", t):
        pts += 5; motivos.append("individual/independente (+5)")
    if re.search(r"compartilhad|divid(ir|e) (o )?banheiro|banheiro coletivo|republica|vaga em quarto|quarto em casa", t):
        pts -= 25; motivos.append("possível moradia compartilhada (-25)")

    item.pontuacao = max(0, min(100, pts))
    item.motivos = motivos

    if total <= orc["prioridade_max"]:
        item.categoria = CAT_PRIORIDADE
    elif total <= orc["teto"]:
        item.categoria = CAT_ELEGIVEL
    elif total <= orc["excepcional_max"] and item.pontuacao >= orc["excepcional_pontuacao_min"]:
        item.categoria = CAT_EXCEPCIONAL
    else:
        item.categoria = CAT_DESCARTADO
        item.motivos.append("acima do teto")
        if item.preco_titulo is not None:
            alt = item.preco_titulo + (total - item.aluguel if item.aluguel else 0)
            if alt <= orc["teto"]:
                item.categoria = CAT_VERIFICAR
                item.motivos.append(f"título cita R$ {item.preco_titulo:,.0f}".replace(",", "."))
    return item
