"""Persistência em SQLite + cálculo de status (novo/atualizado/repetido/indisponível)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import (STATUS_ATUALIZADO, STATUS_INDISPONIVEL, STATUS_NOVO,
                     STATUS_REPETIDO, Listing)

# Campos cuja mudança caracteriza "atualizado"
CAMPOS_RELEVANTES = ("aluguel", "condominio", "iptu", "outras_taxas", "titulo", "mobiliado",
                     "contas_incluidas", "caucao", "telefone", "bairro", "endereco")

SCHEMA = """
CREATE TABLE IF NOT EXISTS anuncios (
    uid TEXT PRIMARY KEY,
    fonte TEXT NOT NULL,
    id_fonte TEXT NOT NULL,
    status TEXT NOT NULL,
    primeira_vez TEXT NOT NULL,
    ultima_verificacao TEXT NOT NULL,
    dados TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historico (
    uid TEXT NOT NULL,
    quando TEXT NOT NULL,
    evento TEXT NOT NULL,
    detalhe TEXT
);
CREATE TABLE IF NOT EXISTS execucoes (
    quando TEXT PRIMARY KEY,
    resumo TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    def get(self, uid: str) -> Listing | None:
        row = self.db.execute("SELECT dados FROM anuncios WHERE uid=?", (uid,)).fetchone()
        return Listing.from_dict(json.loads(row[0])) if row else None

    def all(self) -> list[Listing]:
        return [Listing.from_dict(json.loads(r[0]))
                for r in self.db.execute("SELECT dados FROM anuncios")]

    def upsert(self, item: Listing, agora: str) -> Listing:
        """Grava e define item.status comparando com o registro anterior."""
        old = self.get(item.uid)
        if old is None:
            item.status = STATUS_NOVO
            item.primeira_vez = agora
            self._hist(item.uid, agora, "novo", None)
        else:
            item.primeira_vez = old.primeira_vez
            mudancas = [c for c in CAMPOS_RELEVANTES if getattr(old, c) != getattr(item, c)]
            # Detalhes ausentes nesta coleta não apagam dados já conhecidos
            for c in CAMPOS_RELEVANTES + ("descricao", "data_publicacao", "whatsapp_link", "anunciante"):
                if getattr(item, c) in (None, "", []) and getattr(old, c) not in (None, "", []):
                    setattr(item, c, getattr(old, c))
                    if c in mudancas:
                        mudancas.remove(c)
            if old.status == STATUS_INDISPONIVEL:
                mudancas.append("reapareceu")
            if mudancas:
                item.status = STATUS_ATUALIZADO
                det = {c: [getattr(old, c), getattr(item, c)] for c in mudancas if c != "reapareceu"}
                self._hist(item.uid, agora, "atualizado", json.dumps(det, ensure_ascii=False, default=str))
            else:
                item.status = STATUS_REPETIDO
        item.ultima_verificacao = agora
        item.ausencias = 0
        self.db.execute(
            "INSERT OR REPLACE INTO anuncios VALUES (?,?,?,?,?,?,?)",
            (item.uid, item.fonte, item.id_fonte, item.status, item.primeira_vez, agora,
             json.dumps(item.to_dict(), ensure_ascii=False)),
        )
        return item

    def mark_unavailable(self, fonte: str, vistos: Iterable[str], agora: str,
                         min_ausencias: int = 2) -> list[Listing]:
        """Conta ausências em coletas COMPLETAS; marca indisponível após `min_ausencias`
        seguidas (a paginação das fontes pode oscilar entre execuções)."""
        vistos = set(vistos)
        out = []
        for item in self.all():
            if item.fonte != fonte or item.uid in vistos or item.status == STATUS_INDISPONIVEL:
                continue
            item.ausencias += 1
            if item.ausencias >= min_ausencias:
                item.status = STATUS_INDISPONIVEL
                self._hist(item.uid, agora, "indisponivel", None)
                out.append(item)
            self.db.execute("UPDATE anuncios SET status=?, dados=? WHERE uid=?",
                            (item.status, json.dumps(item.to_dict(), ensure_ascii=False), item.uid))
        return out

    def log_run(self, agora: str, resumo: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO execucoes VALUES (?,?)",
                        (agora, json.dumps(resumo, ensure_ascii=False)))

    def _hist(self, uid, quando, evento, detalhe):
        self.db.execute("INSERT INTO historico VALUES (?,?,?,?)", (uid, quando, evento, detalhe))
