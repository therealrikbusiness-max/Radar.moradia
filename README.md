# RADAR MORADIA v1.0

Monitor automatizado de anúncios de aluguel em **Paulínia/SP** e **Barão Geraldo (Campinas)**,
focado em kitnet, studio, edícula, casa de fundos, casa de 1 quarto e casas pequenas.
Ele roda sozinho no **GitHub Actions**, sem depender de computador pessoal.

## Onde ver os resultados (pelo iPhone)

- **Relatório:** [`reports/relatorio.md`](reports/relatorio.md), atualizado a cada execução (há também o `relatorio.json`).
- **Página de cada execução:** aba *Actions* → *radar-moradia* → execução. O relatório aparece no resumo.
- **Notificações:** quando surge anúncio novo ou atualizado dentro dos critérios, o robô abre uma
  **Issue**, e o app do GitHub avisa no celular (ative as notificações de Issues do repositório).
- **Rodar agora:** *Actions* → *radar-moradia* → *Run workflow*.

## Critérios (editáveis em `config.yaml`)

| Categoria | Regra |
|---|---|
| 🟢 Prioridade | total mensal conhecido ≤ R$ 900 |
| 🟡 Elegível | total ≤ R$ 1.100 (teto, com condomínio e taxas conhecidas) |
| 🔵 Excepcional | acima do teto (até R$ 1.400) e pontuação ≥ 70. Aparece numa seção separada e **não** conta como elegível |

A pontuação (0–100) soma pontos por região, tipo, preço, mobília, contas incluídas
(água, luz, internet), geladeira/fogão, garantia facilitada e moradia individual. Perde pontos
se houver sinal de moradia compartilhada. Os motivos aparecem em cada anúncio.

Regiões com peso: Morumbi, Centro, Vila Presidente Médici, São José, Betel, João Aranha
(Paulínia), Barão Geraldo e sub-bairros (Campinas), além de bairros com acesso pela
Rod. Zeferino Vaz e Transportes Cavalinho (Bom Retiro, Nova Paulínia, Santa Terezinha…).
Em Campinas, só entram os bairros listados.

## Fontes

| Fonte | Situação | Como |
|---|---|---|
| **Chaves na Mão** | ✅ integrada | **Servidor MCP oficial** (`/api/mcp/`), liberado no robots.txt e indicado no `llms.txt` do portal para agentes. Nenhuma página HTML é raspada. |
| Feed VRSync de imobiliária | ⚙️ pronto, desativado | Formato XML que imobiliárias usam para exportar anúncios. Ative em `config.yaml` com a URL do feed, **só com autorização da imobiliária**. |
| QuintoAndar | ❌ excluída | Os Termos de Uso proíbem *web scraping*. |
| OLX, VivaReal, ZAP, Wimóveis | ❌ inacessíveis | robots.txt responde 403 a robôs. |
| Trovit, Nestoria, Mitula | ❌ inacessíveis | robots.txt responde 401. |
| Imovelweb, Casa Mineira | ❌ inacessíveis | Página com desafio anti-robô (403). Não é contornado. |

Regras de acesso do código (`radar_moradia/http.py`):
- Sempre consulta o robots.txt antes, com suporte a `*` e `$`. robots.txt com 401/403 = fonte bloqueada.
- Identifica-se com User-Agent próprio e espera ≥ 4 s entre requisições ao mesmo host.
- 401/403/429 ou CAPTCHA: a fonte é marcada como **bloqueada** e o código **não insiste nem contorna**.
- Lê o cabeçalho de limite de taxa do MCP e para antes de esgotá-lo.

## Dados de cada anúncio

`uid`, título, bairro, município, endereço, aluguel, condomínio, IPTU, outras taxas,
**total mensal conhecido**, mobiliado, contas incluídas, caução/garantia, URL, data de
publicação, última verificação, telefone, link `wa.me` (só para celular válido) e status
(`novo`, `atualizado`, `repetido`, `indisponivel`).
**Nada é inventado:** o que o anúncio não publica fica `null` (no JSON) ou "não informado" (no Markdown).

> Limitação atual: o MCP do Chaves na Mão devolve título, preço, bairro, quartos, área e URL.
> Descrição, telefone, condomínio e caução **não** vêm na resposta, e raspar a página do
> anúncio violaria os Termos de Uso. Esses campos ficam "não informado": confira no link.

## Estrutura

```
radar_moradia/
  http.py          cliente educado (robots.txt, ritmo, bloqueios)
  mcp_client.py    cliente MCP (JSON-RPC sobre HTTP)
  sources/         um módulo por fonte (chavesnamao.py, vrsync_feed.py)
  normalize.py     preços, taxas, tipo, mobília, contas, caução, telefone/wa.me
  scoring.py       filtros de região/tipo/preço e pontuação
  dedup.py         duplicatas entre anúncios/fontes
  storage.py       SQLite (data/radar.db) + histórico de mudanças
  report.py        relatório Markdown e JSON
  pipeline.py      orquestração (uma fonte com falha não derruba as outras)
  notify.py        Issue no GitHub com as novidades
tests/             testes automatizados (pytest), com respostas reais como fixture
config.yaml        critérios, regiões, fontes e consultas
.github/workflows/ monitor.yml (3x/dia), tests.yml
```

## Adicionar uma fonte

1. Crie `radar_moradia/sources/minha_fonte.py` com uma classe `Source` cujo `fetch()` devolve `SourceResult`.
2. Registre-a em `radar_moradia/sources/__init__.py`.
3. Configure-a em `config.yaml` → `fontes`.
4. Antes, confirme que os **Termos de Uso** e o **robots.txt** permitem acesso automatizado.

## Execução local (opcional)

```bash
pip install -r requirements.txt pytest
python -m pytest -q
python -m radar_moradia            # ou: --fonte chavesnamao
```
