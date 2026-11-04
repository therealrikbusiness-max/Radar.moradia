"""Relatórios Markdown e JSON."""
from __future__ import annotations

import json
from pathlib import Path

from .models import STATUS_INDISPONIVEL, Listing
from .normalize import format_phone
from .scoring import CAT_ELEGIVEL, CAT_EXCEPCIONAL, CAT_PRIORIDADE

NI = "não informado"


def _money(v) -> str:
    if v is None:
        return NI
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _bool(v) -> str:
    return NI if v is None else ("sim" if v else "não")


def _card(it: Listing) -> str:
    tel = format_phone(it.telefone) if it.telefone else NI
    wa = f"[{it.whatsapp_link}]({it.whatsapp_link})" if it.whatsapp_link else "—"
    taxas = []
    if it.condominio is not None:
        taxas.append(f"condomínio {_money(it.condominio)}")
    if it.iptu is not None:
        taxas.append(f"IPTU {_money(it.iptu)}")
    if it.outras_taxas is not None:
        taxas.append(f"outras {_money(it.outras_taxas)}")
    linhas = [
        f"### [{it.titulo}]({it.url})",
        f"- **Total mensal conhecido:** {_money(it.total_mensal)} "
        f"(aluguel {_money(it.aluguel)}; taxas: {', '.join(taxas) if taxas else NI})",
        f"- **Local:** {it.bairro or NI} — {it.municipio or NI}"
        + (f" · {it.endereco}" if it.endereco else ""),
        f"- **Tipo:** {it.tipo or NI} · **Quartos:** {it.quartos if it.quartos is not None else NI}"
        f" · **Área:** {f'{it.area_m2:g} m²' if it.area_m2 else NI}",
        f"- **Mobiliado:** {_bool(it.mobiliado)} · **Contas incluídas:** "
        f"{', '.join(it.contas_incluidas) if it.contas_incluidas else NI}",
        f"- **Caução/garantia:** {it.caucao or NI}",
        f"- **Contato:** {tel} · WhatsApp: {wa}" + (f" · {it.anunciante}" if it.anunciante else ""),
        f"- **Publicado:** {it.data_publicacao or NI} · **Verificado:** {it.ultima_verificacao}"
        f" · **Status:** {it.status} · **Fonte:** {it.fonte} (id {it.id_fonte})",
        f"- **Pontuação:** {it.pontuacao}/100 — {'; '.join(it.motivos)}",
    ]
    if it.duplicata_de:
        linhas.append(f"- ⚠️ Provável duplicata de `{it.duplicata_de}`")
    return "\n".join(linhas)


def build(items: list[Listing], fontes: list[dict], agora: str, cfg: dict) -> tuple[str, dict]:
    ativos = [i for i in items if i.status != STATUS_INDISPONIVEL]
    def sec(cat):
        return sorted((i for i in ativos if i.categoria == cat and not i.duplicata_de),
                      key=lambda x: (-x.pontuacao, x.total_mensal or 1e9))
    prio, eleg, exc = sec(CAT_PRIORIDADE), sec(CAT_ELEGIVEL), sec(CAT_EXCEPCIONAL)
    indisp = [i for i in items if i.status == STATUS_INDISPONIVEL]
    orc = cfg["orcamento"]

    md = [f"# RADAR MORADIA — relatório de {agora}", ""]
    md.append(f"Critérios: total até **{_money(orc['prioridade_max'])}** (prioridade) e teto "
              f"**{_money(orc['teto'])}**, Paulínia e Barão Geraldo/Campinas, kitnet, studio, "
              "edícula, casa de fundos, casa de 1 quarto ou casa pequena.")
    md.append("")
    md.append("## Fontes nesta execução")
    md.append("| Fonte | Situação | Anúncios coletados | Observação |")
    md.append("|---|---|---|---|")
    for f in fontes:
        sit = "bloqueada" if f["bloqueada"] else ("ok" if f["ok"] else "falhou")
        md.append(f"| {f['fonte']} | {sit} | {f['coletados']} | {'; '.join(f['erros'])[:200] or '—'} |")
    md.append("")
    novos = [i for i in ativos if i.status == "novo" and i.categoria in (CAT_PRIORIDADE, CAT_ELEGIVEL, CAT_EXCEPCIONAL)]
    md.append(f"**Resumo:** {len(prio)} prioridade · {len(eleg)} elegíveis · {len(exc)} excepcionais "
              f"(acima do teto) · {len(novos)} novos relevantes · {len(indisp)} indisponíveis")
    md.append("")
    for titulo, lista in ((f"## 🟢 Prioridade (até {_money(orc['prioridade_max'])})", prio),
                          (f"## 🟡 Elegíveis (até {_money(orc['teto'])})", eleg),
                          ("## 🔵 Excepcionais — ACIMA DO TETO (não elegíveis, apenas referência)", exc)):
        md.append(titulo)
        md.append("")
        md.extend([_card(i) + "\n" for i in lista] or ["_Nenhum anúncio nesta categoria._", ""])
    if indisp:
        md.append("## ⚫ Indisponíveis desde a última verificação")
        md.extend(f"- [{i.titulo}]({i.url}) — {i.bairro or NI}, {_money(i.total_mensal)}" for i in indisp[:30])
        md.append("")
    md.append("---")
    md.append("Dados conforme publicados pelos anunciantes; campos \"não informado\" não foram publicados. "
              "Confirme valores e condições diretamente com o anunciante antes de qualquer pagamento.")

    js = {
        "gerado_em": agora,
        "criterios": orc,
        "fontes": fontes,
        "prioridade": [i.to_dict() for i in prio],
        "elegiveis": [i.to_dict() for i in eleg],
        "excepcionais_acima_do_teto": [i.to_dict() for i in exc],
        "indisponiveis": [i.to_dict() for i in indisp],
        "descartados_qtd": sum(1 for i in ativos if i.categoria == "descartado"),
    }
    return "\n".join(md) + "\n", js


def write(md: str, js: dict, outdir: str | Path) -> None:
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    (p / "relatorio.md").write_text(md, encoding="utf-8")
    (p / "relatorio.json").write_text(json.dumps(js, ensure_ascii=False, indent=2, default=str),
                                      encoding="utf-8")
