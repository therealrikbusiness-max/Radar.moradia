"""Orquestração: coleta -> normalização -> filtros/classificação -> duplicatas -> banco -> relatório."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from . import report
from .dedup import mark_duplicates
from .http import PoliteClient
from .models import STATUS_INDISPONIVEL
from .normalize import make_uid, normalize
from .scoring import score
from .sources import REGISTRY
from .sources.base import SourceResult
from .storage import Store

log = logging.getLogger("radar")


def load_config(path: str | Path = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def build_sources(cfg: dict, client: PoliteClient, only: Optional[list[str]] = None):
    out = []
    for key, scfg in (cfg.get("fontes") or {}).items():
        if only and key not in only:
            continue
        if not scfg.get("ativa", False):
            log.info("Fonte %s desativada na configuração", key)
            continue
        cls = REGISTRY.get(scfg.get("modulo", key))
        if cls is None:
            log.error("Fonte %s: módulo desconhecido %s", key, scfg.get("modulo"))
            continue
        src = cls(client, scfg, cfg)
        src.nome = key
        out.append(src)
    return out


def run(cfg: dict, db_path: str = "data/radar.db", outdir: str = "reports",
        client: Optional[PoliteClient] = None, only: Optional[list[str]] = None) -> dict:
    agora = now_iso()
    h = cfg["http"]
    client = client or PoliteClient(h["user_agent"], h["timeout"], h["intervalo_min_segundos"], h["tentativas"])
    store = Store(db_path)
    fontes_info = []
    try:
        for src in build_sources(cfg, client, only):
            log.info("Coletando fonte %s", src.nome)
            try:
                result: SourceResult = src.fetch()
            except Exception as e:  # uma fonte nunca derruba a execução
                log.exception("Fonte %s falhou inesperadamente", src.nome)
                result = SourceResult(fonte=src.nome, ok=False, erros=[f"erro inesperado: {e!r}"])
            uids = set()
            for item in result.listings:
                item.fonte = src.nome
                item.uid = make_uid(src.nome, item.id_fonte)
                uids.add(item.uid)
                normalize(item)
                score(item, cfg)
                store.upsert(item, agora)
            if result.cobertura_completa:
                gone = store.mark_unavailable(src.nome, uids, agora,
                                              int(cfg.get("ausencias_para_indisponivel", 2)))
                if gone:
                    log.info("%s anúncios de %s marcados como indisponíveis", len(gone), src.nome)
            elif result.listings or not result.ok:
                log.info("Coleta de %s incompleta: não marca indisponíveis", src.nome)
            fontes_info.append({"fonte": src.nome, "ok": result.ok, "bloqueada": result.bloqueada,
                                "coletados": len(result.listings), "paginas": result.paginas,
                                "cobertura_completa": result.cobertura_completa,
                                "erros": result.erros})
            for e in result.erros:
                log.warning("[%s] %s", src.nome, e)

        todos = store.all()
        # Reclassifica tudo (configuração pode ter mudado) e detecta duplicatas
        for it in todos:
            normalize(it)
            score(it, cfg)
        ativos = [i for i in todos if i.status != STATUS_INDISPONIVEL]
        mark_duplicates(ativos)
        md, js = report.build(todos, fontes_info, agora, cfg)
        report.write(md, js, outdir)
        resumo = {"fontes": fontes_info, "total_banco": len(todos),
                  "prioridade": len(js["prioridade"]), "elegiveis": len(js["elegiveis"]),
                  "excepcionais": len(js["excepcionais_acima_do_teto"]),
                  "requisicoes": client.requests_made}
        store.log_run(agora, resumo)
        log.info("Resumo: %s", resumo)
        return resumo
    finally:
        store.close()
