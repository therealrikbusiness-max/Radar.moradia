"""Fonte: Chaves na Mão — via servidor MCP OFICIAL e público do portal.

Por que MCP e não HTML:
- Os Termos de Uso do portal proíbem raspagem/coleta automatizada das páginas.
- O próprio portal publica um servidor MCP (/api/mcp/, liberado no robots.txt e
  anunciado em /llms.txt e /.well-known/mcp/server-card.json) e orienta agentes a
  "priorizar o MCP Server em vez de percorrer sequencialmente as páginas".
Portanto este módulo usa SOMENTE a ferramenta `search_realty_listings` e nunca
abre as páginas HTML dos anúncios.
"""
from __future__ import annotations

import re
from typing import Optional

from ..http import SourceBlocked, SourceError
from ..mcp_client import MCPClient
from ..models import Listing
from .base import Source, SourceResult

ENDPOINT = "https://www.chavesnamao.com.br/api/mcp/"
TOOL = "search_realty_listings"
IMG_PREFIX = "https://www.chavesnamao.com.br/imn/0640x0400/N/75/imoveis/"

# Mapeia o "propertyType" retornado para nossos tipos (refinado depois pela normalização)
_TIPO_MAP = {
    "kitnet / studio": "kitnet", "kitnet / stúdio": "kitnet", "kitnet": "kitnet",
    "studio": "studio", "loft": "studio", "flat": "studio",
    "casa": "casa", "casa / sobrado": "casa", "sobrado": "casa",
}


def _tipo(pt: Optional[str]) -> Optional[str]:
    if not pt:
        return None
    p = pt.strip().lower()
    if p in _TIPO_MAP:
        return _TIPO_MAP[p]
    if re.search(r"sala|galp|barrac|ponto|loja|comercial|terreno|pr[eé]dio|ch[aá]cara|garagem|fazenda|s[ií]tio", p):
        return "comercial_ou_outro"
    if "apart" in p or "cobertura" in p:
        return "apartamento"
    if "condom" in p:
        return "casa_condominio"
    return p


def parse_result(r: dict) -> Optional[Listing]:
    """Converte um item de `results` em Listing. Retorna None se faltar id/url."""
    rid, url = r.get("id"), r.get("url")
    if not rid or not url:
        return None
    loc = r.get("location") or {}
    price = r.get("priceBRL")
    return Listing(
        fonte="chavesnamao",
        id_fonte=str(rid),
        url=url,
        titulo=(r.get("title") or "").strip(),
        bairro=loc.get("neighborhood"),
        municipio=loc.get("city"),
        aluguel=float(price) if isinstance(price, (int, float)) and price > 0 else None,
        quartos=r.get("bedrooms"),
        area_m2=float(r["areaM2"]) if r.get("areaM2") else None,
        tipo=_tipo(r.get("propertyType")),
    )


class ChavesNaMaoMCP(Source):
    nome = "chavesnamao"
    descricao = "Chaves na Mão (servidor MCP oficial)"

    def fetch(self) -> SourceResult:
        res = SourceResult(fonte=self.nome)
        max_pages = int(self.cfg.get("max_paginas_por_consulta", 5))
        consultas = self.cfg.get("consultas", [])
        mcp = MCPClient(self.client, self.cfg.get("endpoint", ENDPOINT))
        try:
            mcp.initialize()
        except SourceBlocked as e:
            res.ok, res.bloqueada = False, True
            res.erros.append(str(e))
            return res
        except (SourceError, ValueError) as e:
            res.ok = False
            res.erros.append(f"initialize: {e}")
            return res

        vistos: dict[str, Listing] = {}
        completas = 0
        for q in consultas:
            filtros = dict(q["filters"])
            page, total_pages = 1, 1
            try:
                while page <= min(total_pages, max_pages):
                    args = {"filters": filtros, "page": page}
                    if q.get("proximity"):
                        args["proximity"] = q["proximity"]
                    out = mcp.call_tool(TOOL, args)
                    res.paginas += 1
                    if not isinstance(out, dict) or "results" not in out:
                        raise SourceError(f"formato inesperado: {str(out)[:200]}")
                    total_pages = int((out.get("pagination") or {}).get("totalPages") or 0)
                    for r in out["results"]:
                        item = parse_result(r)
                        if item and item.id_fonte not in vistos:
                            vistos[item.id_fonte] = item
                    remaining = mcp.last_headers.get("x-ratelimit-remaining")
                    if remaining is not None and remaining.isdigit() and int(remaining) < 5:
                        self.log.warning("Limite de taxa quase esgotado (%s); parando.", remaining)
                        res.erros.append("limite de taxa do MCP quase esgotado; coleta parcial")
                        raise StopIteration
                    page += 1
                if total_pages <= max_pages:
                    completas += 1
                else:
                    self.log.info("Consulta %s truncada em %s/%s páginas", filtros, max_pages, total_pages)
            except StopIteration:
                break
            except SourceBlocked as e:
                res.ok, res.bloqueada = False, True
                res.erros.append(str(e))
                break
            except (SourceError, ValueError) as e:
                res.ok = False
                res.erros.append(f"consulta {filtros}: {e}")
        res.listings = list(vistos.values())
        res.ids_vistos = set(vistos)
        res.cobertura_completa = res.ok and completas == len(consultas) and not res.erros
        self.log.info("%s anúncios únicos em %s páginas", len(res.listings), res.paginas)
        return res
