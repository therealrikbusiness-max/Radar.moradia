"""Normalização: preços, tipo de imóvel, mobília, contas, caução, telefones."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Optional

from .models import Listing


def norm(text: Optional[str]) -> str:
    """Minúsculas, sem acentos, espaços colapsados."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


_MONEY_RE = re.compile(r"r\$\s*([\d.]+(?:,\d{1,2})?)", re.I)


def parse_money(value) -> Optional[float]:
    """'R$ 1.100,00' -> 1100.0 ; 950 -> 950.0 ; '' -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    s = str(value).strip()
    if not s:
        return None
    m = _MONEY_RE.search(s)
    raw = m.group(1) if m else re.sub(r"[^\d.,]", "", s)
    if not raw or not re.search(r"\d", raw):
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        raw = raw.replace(".", "")
    try:
        v = float(raw)
    except ValueError:
        return None
    return v if v > 0 else None


def _fee_from_text(text_n: str, labels: list[str]) -> Optional[float]:
    for lab in labels:
        m = re.search(lab + r"[^\d\n]{0,25}?r\$\s*([\d.]+(?:,\d{1,2})?)", text_n)
        if m:
            return parse_money("R$ " + m.group(1))
        # "valor de 280,00 de condomínio" / "R$ 150 de condomínio"
        m = re.search(r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d{2,4})\s+(?:reais\s+)?(?:de|do|da)\s+" + lab, text_n)
        if m:
            return parse_money("R$ " + m.group(1))
    return None


def fees_from_text(text: str) -> dict:
    """Extrai condomínio/IPTU citados no texto (só quando há valor explícito)."""
    t = norm(text)
    out = {
        "condominio": _fee_from_text(t, [r"condominio", r"cond\.", r"taxa de conservacao"]),
        "iptu": _fee_from_text(t, [r"iptu"]),
    }
    return out


# ---------------------------------------------------------------- tipo
_TIPOS = [
    ("edicula", [r"\bedicula\b"]),
    ("casa_fundos", [r"casa (de|nos) fundos", r"\bfundos\b"]),
    ("kitnet", [r"\bkit ?net\b", r"\bkitinete?\b", r"\bquitinete?\b", r"\bkit\b"]),
    ("studio", [r"\bstudio\b", r"\bestudio\b", r"\bloft\b"]),
]


def detect_tipo(titulo: str, descricao: str = "", quartos: Optional[int] = None,
                tipo_fonte: str = "") -> Optional[str]:
    t = norm(f"{tipo_fonte} {titulo}")
    full = norm(f"{tipo_fonte} {titulo} {descricao}")
    for tipo, pats in _TIPOS:
        if any(re.search(p, t) for p in pats):
            return tipo
    for tipo, pats in _TIPOS[:2]:  # edícula/fundos citados só na descrição
        if any(re.search(p, full) for p in pats):
            return tipo
    for tipo, pats in _TIPOS[2:]:
        if any(re.search(p, full) for p in pats):
            return tipo
    if re.search(r"\bcasa\b|\bsobrado\b", t):
        if quartos == 1 or re.search(r"\b(1|um) (quarto|dormitorio|dorm)\b", full):
            return "casa_1_quarto"
        if quartos is None and re.search(r"casa (pequena|independente)|casinha", full):
            return "casa_pequena"
        return "casa"
    if re.search(r"apartamento|\bapto?\b|flat", t):
        return "apartamento"
    return None


# ---------------------------------------------------------------- mobília/contas/caução
def detect_mobiliado(text: str) -> Optional[bool]:
    t = norm(text)
    if re.search(r"(nao|sem) (e )?mobiliad|sem mobilia|vazi[ao]\b", t):
        return False
    if re.search(r"semi[- ]?mobiliad", t):
        return True  # parcialmente; detalhado nos motivos
    if re.search(r"\bmobiliad|com mobilia|\bmobilia\b", t):
        return True
    return None


_CONTAS = {
    "agua": r"agua|sanasa|sabesp",
    "luz": r"\bluz\b|energia|cpfl",
    "internet": r"internet|wi-?fi",
    "gas": r"\bgas\b",
    "iptu": r"iptu",
    "condominio": r"condominio",
}
_INCL = r"(inclus[oa]s?|incluid[oa]s?|incluso|inclui|ja incluso|ja inclus[oa])"


def detect_contas(text: str) -> list[str]:
    t = norm(text)
    found = []
    for nome, pat in _CONTAS.items():
        if re.search(rf"({pat})[^.;\n]{{0,40}}{_INCL}", t) or re.search(
            rf"{_INCL}[^.;\n]{{0,40}}({pat})", t
        ):
            found.append(nome)
    # "condomínio ... refere-se ao rateio: SANASA, CPFL, IPTU e internet"
    m = re.search(r"condominio[^.]{0,80}?rateio[^.]{0,120}", t)
    if m:
        for nome, pat in _CONTAS.items():
            if nome != "condominio" and re.search(pat, m.group(0)) and nome not in found:
                found.append(nome)
    if not found and re.search(r"contas inclusas|tudo incluso|contas incluidas", t):
        found.append("contas (não especificadas)")
    return found


def detect_caucao(text: str) -> Optional[str]:
    """Trecho publicado sobre garantia (caução, fiador, seguro-fiança...)."""
    if not text:
        return None
    for sent in re.split(r"(?<=[.!?;\n])\s+", text):
        n = norm(sent)
        if re.search(r"caucao|fiador|seguro[- ]fianca|deposito|garantia|sem fiador|titulo de capitalizacao", n):
            return sent.strip()[:200]
    return None


def detect_quartos(text: str) -> Optional[int]:
    m = re.search(r"\b(\d)\s*(quartos?|dormitorios?|dorms?)\b", norm(text))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- telefone
_DDDS = {11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38,
         41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68,
         69, 71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95,
         96, 97, 98, 99}
_PHONE_RE = re.compile(r"(?:\+?55[\s.-]?)?\(?\b(\d{2})\)?[\s.-]?(9?\d{4})[\s.-]?(\d{4})\b")


def find_phones(text: str) -> list[str]:
    """Telefones brasileiros válidos no texto, em formato só dígitos (DDD+número)."""
    out = []
    for m in _PHONE_RE.finditer(text or ""):
        ddd, a, b = m.groups()
        if int(ddd) not in _DDDS:
            continue
        num = ddd + a + b
        if len(a) == 5 and not a.startswith("9"):
            continue
        if len(a) == 4 and a[0] not in "2345":  # fixo começa com 2-5
            continue
        if num not in out:
            out.append(num)
    return out


def whatsapp_link(phone: Optional[str]) -> Optional[str]:
    """wa.me apenas para celular válido (DDD + 9 dígitos começando em 9)."""
    if not phone:
        return None
    d = re.sub(r"\D", "", phone)
    if d.startswith("55") and len(d) == 13:
        d = d[2:]
    if len(d) == 11 and int(d[:2]) in _DDDS and d[2] == "9":
        return f"https://wa.me/55{d}"
    return None


def format_phone(d: str) -> str:
    d = re.sub(r"\D", "", d)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return d


# ---------------------------------------------------------------- pipeline
def make_uid(fonte: str, id_fonte: str) -> str:
    return hashlib.sha1(f"{fonte}:{id_fonte}".encode()).hexdigest()[:16]


def normalize(item: Listing) -> Listing:
    """Completa campos derivados SEM inventar: só o que está no texto publicado."""
    texto = f"{item.titulo}\n{item.descricao}"
    item.uid = item.uid or make_uid(item.fonte, item.id_fonte)
    if item.municipio:
        item.municipio = item.municipio.strip()
    if item.bairro:
        item.bairro = item.bairro.strip()
    fees = fees_from_text(item.descricao)
    if item.condominio is None and fees["condominio"]:
        item.condominio = fees["condominio"]
    if item.iptu is None and fees["iptu"]:
        item.iptu = fees["iptu"]
    if item.quartos is None:
        item.quartos = detect_quartos(texto)
    if item.tipo is None or item.tipo in ("casa", "apartamento", "outro"):
        item.tipo = detect_tipo(item.titulo, item.descricao, item.quartos, item.tipo or "") or item.tipo
    if item.mobiliado is None:
        item.mobiliado = detect_mobiliado(texto)
    if not item.contas_incluidas:
        item.contas_incluidas = detect_contas(texto)
    if item.caucao is None:
        item.caucao = detect_caucao(item.descricao)
    if item.telefone is None:
        phones = find_phones(texto)
        if phones:
            item.telefone = phones[0]
    if item.telefone and not item.whatsapp_link:
        item.whatsapp_link = whatsapp_link(item.telefone)
    item.preco_titulo = None
    item.alertas = [a for a in item.alertas if not a.startswith("preço no título")]
    pt = price_in_title(item.titulo)
    if pt and item.aluguel and abs(pt - item.aluguel) >= 1:
        item.preco_titulo = pt
        item.alertas.append(f"preço no título (R$ {pt:,.2f}) diverge do preço do anúncio "
                            f"(R$ {item.aluguel:,.2f}); confirme".replace(",", "X").replace(".", ",").replace("X", "."))
    item.total_mensal = total_mensal(item)
    return item


def price_in_title(titulo: str) -> Optional[float]:
    """Valor de aluguel citado no título ('por R$ 1.300,00/mês'). Ignora preços de venda."""
    t = norm(titulo)
    val = r"r\$\s*([\d.]+(?:,\d{1,2})?)"
    m = re.search(r"(?:aluguel|locacao) por " + val, t)
    if m:
        return parse_money("R$ " + m.group(1))
    if "venda" in t:
        return None
    m = re.search(val + r"\s*(?:/\s*mes|mensa|$|\s*-)", t)
    return parse_money("R$ " + m.group(1)) if m else None


def total_mensal(item: Listing) -> Optional[float]:
    """Aluguel + taxas conhecidas (taxas declaradas inclusas não somam)."""
    if item.aluguel is None:
        return None
    total = item.aluguel
    for nome in ("condominio", "iptu", "outras_taxas"):
        v = getattr(item, nome)
        if v and nome not in item.contas_incluidas:
            total += v
    return round(total, 2)
