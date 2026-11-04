"""Notificação opcional: abre uma Issue no GitHub quando surgem anúncios novos/atualizados
relevantes. A Issue gera notificação no app do GitHub (iPhone). Usa GITHUB_TOKEN do Actions."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests


def novidades(js: dict) -> list[dict]:
    out = []
    for sec in ("prioridade", "elegiveis", "excepcionais_acima_do_teto"):
        for it in js.get(sec, []):
            if it.get("status") in ("novo", "atualizado"):
                out.append(dict(it, _secao=sec))
    return out


def corpo(itens: list[dict]) -> str:
    linhas = ["Novos/atualizados no RADAR MORADIA:", ""]
    for it in itens:
        total = it.get("total_mensal")
        t = f"R$ {total:,.0f}".replace(",", ".") if total else "valor não informado"
        sec = {"prioridade": "🟢", "elegiveis": "🟡", "excepcionais_acima_do_teto": "🔵 acima do teto"}[it["_secao"]]
        wa = f" · [WhatsApp]({it['whatsapp_link']})" if it.get("whatsapp_link") else ""
        linhas.append(f"- {sec} **{t}** — [{it['titulo']}]({it['url']}) — "
                      f"{it.get('bairro') or '?'}, {it.get('municipio') or '?'} ({it['status']}){wa}")
    linhas += ["", "Relatório completo: `reports/relatorio.md`"]
    return "\n".join(linhas)


def main(path="reports/relatorio.json") -> int:
    js = json.loads(Path(path).read_text(encoding="utf-8"))
    itens = novidades(js)
    if not itens:
        print("Sem novidades relevantes; nenhuma notificação.")
        return 0
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print(corpo(itens))
        return 0
    r = requests.post(f"https://api.github.com/repos/{repo}/issues",
                      headers={"Authorization": f"Bearer {token}",
                               "Accept": "application/vnd.github+json"},
                      json={"title": f"🏠 {len(itens)} anúncio(s) novo(s) — {js['gerado_em'][:16]}",
                            "body": corpo(itens), "labels": ["radar"]}, timeout=30)
    print("Issue:", r.status_code, r.json().get("html_url"))
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
