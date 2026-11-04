"""Interface comum das fontes."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..http import PoliteClient
from ..models import Listing


@dataclass
class SourceResult:
    fonte: str
    listings: list[Listing] = field(default_factory=list)
    ok: bool = True
    bloqueada: bool = False
    erros: list[str] = field(default_factory=list)
    paginas: int = 0
    # ids vistos na listagem (permite marcar "indisponível" com segurança)
    ids_vistos: set[str] = field(default_factory=set)
    cobertura_completa: bool = False


class Source(ABC):
    nome: str = "base"
    descricao: str = ""

    def __init__(self, client: PoliteClient, cfg: dict, global_cfg: Optional[dict] = None):
        self.client = client
        self.cfg = cfg or {}
        self.global_cfg = global_cfg or {}
        self.log = logging.getLogger(f"radar.fonte.{self.nome}")

    @abstractmethod
    def fetch(self) -> SourceResult:
        """Coleta anúncios. Não deve lançar exceção: erros vão em SourceResult."""
