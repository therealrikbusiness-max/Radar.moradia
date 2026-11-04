"""Cliente HTTP 'educado': respeita robots.txt, identifica-se, limita ritmo e
NÃO tenta contornar bloqueios (403/401/429/CAPTCHA => a fonte é marcada como bloqueada)."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)


class SourceBlocked(Exception):
    """A fonte recusou o acesso (robots.txt, 401/403/429, CAPTCHA). Não insistir."""


class SourceError(Exception):
    """Falha temporária (rede, 5xx, formato inesperado)."""


# ------------------------------------------------------------------ robots.txt
@dataclass
class RobotsRules:
    """Regras de robots.txt com suporte a '*' e '$' (RFC 9309), por grupo de UA."""

    groups: list[tuple[list[str], list[tuple[bool, str]]]] = field(default_factory=list)
    disallow_all: bool = False

    @classmethod
    def parse(cls, text: str) -> "RobotsRules":
        groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = (p.strip() for p in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and agents:
                    groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(val.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if agents and (val or key == "allow"):
                    rules.append((key == "allow", val))
            else:
                last_was_agent = False
        if agents:
            groups.append((agents, rules))
        return cls(groups=groups)

    def _group_for(self, ua: str) -> list[tuple[bool, str]]:
        token = ua.split("/")[0].strip().lower()
        best: Optional[list] = None
        for agents, rules in self.groups:
            if any(a != "*" and a in token for a in agents):
                return rules
            if "*" in agents and best is None:
                best = rules
        return best or []

    @staticmethod
    def _match(pattern: str, path: str) -> bool:
        anchored = pattern.endswith("$")
        p = pattern[:-1] if anchored else pattern
        rx = "^" + ".*".join(re.escape(part) for part in p.split("*"))
        if anchored:
            rx += "$"
        return re.match(rx, path) is not None

    def allowed(self, ua: str, url: str) -> bool:
        if self.disallow_all:
            return False
        u = urlparse(url)
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        verdict, length = True, -1
        for allow, pattern in self._group_for(ua):
            if self._match(pattern, path):
                plen = len(pattern)
                # regra mais específica vence; empate => allow vence
                if plen > length or (plen == length and allow):
                    verdict, length = allow, plen
        return verdict


# ------------------------------------------------------------------ cliente
class PoliteClient:
    def __init__(self, user_agent: str, timeout: int = 30, min_interval: float = 4.0,
                 retries: int = 3, session: Optional[requests.Session] = None):
        self.ua = user_agent
        self.timeout = timeout
        self.min_interval = min_interval
        self.retries = retries
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9"})
        self._robots: dict[str, RobotsRules] = {}
        self._last: dict[str, float] = {}
        self.requests_made = 0

    def robots(self, url: str) -> RobotsRules:
        u = urlparse(url)
        host = f"{u.scheme}://{u.netloc}"
        if host not in self._robots:
            try:
                r = self._raw_get(host + "/robots.txt")
                if r.status_code == 200:
                    rules = RobotsRules.parse(r.text)
                elif r.status_code in (404, 410):
                    rules = RobotsRules()  # sem robots.txt => permitido
                else:
                    # 401/403/5xx: tratar como proibido (conservador)
                    rules = RobotsRules(disallow_all=True)
                    log.warning("robots.txt de %s retornou %s: fonte tratada como bloqueada",
                                host, r.status_code)
            except requests.RequestException as e:
                raise SourceError(f"robots.txt inacessível em {host}: {e}") from e
            self._robots[host] = rules
        return self._robots[host]

    def _throttle(self, host: str) -> None:
        wait = self.min_interval - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def _raw_get(self, url: str) -> requests.Response:
        self._throttle(urlparse(url).netloc)
        self.requests_made += 1
        return self.s.get(url, timeout=self.timeout)

    def get(self, url: str) -> requests.Response:
        if not self.robots(url).allowed(self.ua, url):
            raise SourceBlocked(f"robots.txt não permite {url}")
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                r = self._raw_get(url)
            except requests.RequestException as e:
                last_exc = e
                log.warning("Falha de rede (%s/%s) em %s: %s", attempt, self.retries, url, e)
                time.sleep(2 ** attempt)
                continue
            if r.status_code in (401, 403, 429):
                raise SourceBlocked(f"HTTP {r.status_code} em {url} (acesso recusado; não contornado)")
            if r.status_code >= 500:
                last_exc = SourceError(f"HTTP {r.status_code} em {url}")
                time.sleep(2 ** attempt)
                continue
            if re.search(r"captcha|cf-chl|challenge-platform", r.text[:5000], re.I):
                raise SourceBlocked(f"CAPTCHA/desafio detectado em {url}; não contornado")
            return r
        raise SourceError(f"Falha após {self.retries} tentativas em {url}: {last_exc}")
