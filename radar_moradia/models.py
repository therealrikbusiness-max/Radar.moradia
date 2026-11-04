"""Modelo de dados de um anúncio normalizado."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

STATUS_NOVO = "novo"
STATUS_ATUALIZADO = "atualizado"
STATUS_REPETIDO = "repetido"
STATUS_INDISPONIVEL = "indisponivel"


@dataclass
class Listing:
    """Anúncio. Campos None = informação NÃO publicada (nunca inventada)."""

    fonte: str
    id_fonte: str                     # id do anúncio na fonte
    url: str
    titulo: str
    descricao: str = ""
    bairro: Optional[str] = None
    municipio: Optional[str] = None
    endereco: Optional[str] = None
    aluguel: Optional[float] = None
    condominio: Optional[float] = None
    iptu: Optional[float] = None       # mensal
    outras_taxas: Optional[float] = None
    mobiliado: Optional[bool] = None
    contas_incluidas: list[str] = field(default_factory=list)
    caucao: Optional[str] = None       # texto publicado sobre caução/garantia
    quartos: Optional[int] = None
    area_m2: Optional[float] = None
    tipo: Optional[str] = None         # kitnet, studio, edicula, ...
    data_publicacao: Optional[str] = None
    telefone: Optional[str] = None
    whatsapp_link: Optional[str] = None
    anunciante: Optional[str] = None
    # Preenchidos pelo pipeline
    uid: str = ""
    total_mensal: Optional[float] = None
    regiao: Optional[str] = None
    pontuacao: int = 0
    motivos: list[str] = field(default_factory=list)
    categoria: str = ""                # prioridade | elegivel | excepcional | descartado
    status: str = STATUS_NOVO
    primeira_vez: Optional[str] = None
    ultima_verificacao: Optional[str] = None
    duplicata_de: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Listing":
        names = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in names})
