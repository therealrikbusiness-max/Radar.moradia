"""Detecção de duplicatas entre fontes/anunciantes (mesmo imóvel anunciado várias vezes)."""
from __future__ import annotations

import re

from .models import Listing
from .normalize import norm


def _fingerprint_text(item: Listing) -> set[str]:
    t = norm(f"{item.titulo} {item.descricao}")
    t = re.sub(r"https?://\S+|\d", " ", t)
    return {w for w in t.split() if len(w) > 3}


def same_property(a: Listing, b: Listing) -> bool:
    """Heurística conservadora: mesmo bairro, preço igual (±2%) e
    (mesmo telefone, mesmo endereço ou texto muito parecido)."""
    if a.uid == b.uid:
        return False
    if not a.aluguel or not b.aluguel:
        return False
    if abs(a.aluguel - b.aluguel) > 0.02 * max(a.aluguel, b.aluguel):
        return False
    if norm(a.bairro) != norm(b.bairro) or norm(a.municipio) != norm(b.municipio):
        return False
    if a.telefone and a.telefone == b.telefone:
        return True
    if a.endereco and b.endereco and norm(a.endereco) == norm(b.endereco):
        if a.area_m2 == b.area_m2:
            return True
    wa, wb = _fingerprint_text(a), _fingerprint_text(b)
    if len(wa) >= 8 and len(wb) >= 8:
        jac = len(wa & wb) / len(wa | wb)
        return jac >= 0.6
    return False


def mark_duplicates(items: list[Listing]) -> list[Listing]:
    """Define duplicata_de no item 'pior' (mantém o mais antigo/mais completo)."""
    ordered = sorted(items, key=lambda x: (x.primeira_vez or "9999", -len(x.descricao or "")))
    canon: list[Listing] = []
    for it in ordered:
        it.duplicata_de = None
        for c in canon:
            if same_property(it, c):
                it.duplicata_de = c.uid
                break
        if it.duplicata_de is None:
            canon.append(it)
    return items
