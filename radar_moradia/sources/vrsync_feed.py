"""Fonte genérica: feed XML no padrão VRSync (VivaReal/OLX/Zap), usado por
sistemas de imobiliárias (Jetimob, Kenlo, Imobibrasil, Vista...) para exportar
anúncios. Só deve ser configurada com URLs de feed PÚBLICAS ou fornecidas/autorizadas
pela imobiliária. O feed é baixado via PoliteClient (respeita robots.txt)."""
from __future__ import annotations

import re
from typing import Optional

from lxml import etree

from ..http import SourceBlocked, SourceError
from ..models import Listing
from ..normalize import parse_money
from .base import Source, SourceResult


def _local(tag) -> str:
    return tag.split("}", 1)[-1] if isinstance(tag, str) else ""


def _find(el, *path) -> Optional[etree._Element]:
    cur = el
    for name in path:
        nxt = None
        for ch in cur:
            if _local(ch.tag).lower() == name.lower():
                nxt = ch
                break
        if nxt is None:
            return None
        cur = nxt
    return cur


def _text(el, *path) -> Optional[str]:
    node = _find(el, *path)
    if node is None or node.text is None:
        return None
    t = node.text.strip()
    return t or None


def parse_feed(xml_bytes: bytes, fonte: str) -> list[Listing]:
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.fromstring(xml_bytes, parser=parser)
    if root is None:
        raise SourceError("XML inválido")
    out = []
    for lst in root.iter():
        if _local(lst.tag) != "Listing":
            continue
        tt = (_text(lst, "TransactionType") or "").lower()
        if tt and "rent" not in tt and "lease" not in tt and "alug" not in tt:
            continue  # só locação
        lid = _text(lst, "ListingID")
        url = _text(lst, "DetailViewUrl") or _text(lst, "Url")
        if not lid or not url:
            continue
        iptu_ano = parse_money(_text(lst, "Details", "YearlyTax"))
        iptu_mes = parse_money(_text(lst, "Details", "MonthlyTax"))
        tel = _text(lst, "ContactInfo", "Telephone")
        out.append(Listing(
            fonte=fonte,
            id_fonte=lid,
            url=url,
            titulo=_text(lst, "Title") or "",
            descricao=_text(lst, "Details", "Description") or "",
            bairro=_text(lst, "Location", "Neighborhood"),
            municipio=_text(lst, "Location", "City"),
            endereco=" ".join(x for x in (_text(lst, "Location", "Address"),
                                          _text(lst, "Location", "StreetNumber")) if x) or None,
            aluguel=parse_money(_text(lst, "Details", "RentalPrice")),
            condominio=parse_money(_text(lst, "Details", "PropertyAdministrationFee")),
            iptu=iptu_mes if iptu_mes else (round(iptu_ano / 12, 2) if iptu_ano else None),
            quartos=int(_text(lst, "Details", "Bedrooms")) if (_text(lst, "Details", "Bedrooms") or "").isdigit() else None,
            area_m2=parse_money(_text(lst, "Details", "LivingArea")),
            tipo=(_text(lst, "Details", "PropertyType") or "").split("/")[-1].strip().lower() or None,
            data_publicacao=_text(lst, "ListDate") or _text(lst, "PublishDate"),
            telefone=re.sub(r"\D", "", tel) if tel else None,
            anunciante=_text(lst, "ContactInfo", "Name"),
        ))
    return out


class VRSyncFeed(Source):
    nome = "vrsync"
    descricao = "Feed XML VRSync de imobiliária (configurável)"

    def fetch(self) -> SourceResult:
        nome = self.cfg.get("nome", self.nome)
        res = SourceResult(fonte=nome)
        urls = self.cfg.get("urls", [])
        if not urls:
            res.ok = False
            res.erros.append("nenhuma URL de feed configurada")
            return res
        for url in urls:
            try:
                r = self.client.get(url)
                res.paginas += 1
                items = parse_feed(r.content, nome)
                res.listings.extend(items)
            except SourceBlocked as e:
                res.ok, res.bloqueada = False, True
                res.erros.append(str(e))
            except (SourceError, etree.XMLSyntaxError, ValueError) as e:
                res.ok = False
                res.erros.append(f"{url}: {e}")
        res.ids_vistos = {i.id_fonte for i in res.listings}
        res.cobertura_completa = res.ok
        return res
