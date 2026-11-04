"""CLI: python -m radar_moradia [--config config.yaml] [--fonte chavesnamao]"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from .pipeline import load_config, run


def setup_logging(logdir: str) -> Path:
    Path(logdir).mkdir(parents=True, exist_ok=True)
    path = Path(logdir) / f"execucao-{datetime.now():%Y%m%d}.log"
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt,
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(path, encoding="utf-8")])
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="radar_moradia", description="RADAR MORADIA v1.0")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--db", default="data/radar.db")
    ap.add_argument("--saida", default="reports")
    ap.add_argument("--logs", default="logs")
    ap.add_argument("--fonte", action="append", help="limitar a uma fonte (pode repetir)")
    a = ap.parse_args(argv)
    setup_logging(a.logs)
    resumo = run(load_config(a.config), a.db, a.saida, only=a.fonte)
    # Código de saída 2 se TODAS as fontes falharam (alerta no GitHub Actions)
    if resumo["fontes"] and not any(f["ok"] for f in resumo["fontes"]):
        logging.getLogger("radar").error("Todas as fontes falharam nesta execução")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
