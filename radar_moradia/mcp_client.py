"""Cliente mínimo MCP (transporte Streamable HTTP, JSON-RPC 2.0).

Usado para falar com servidores MCP *oficiais e públicos* de portais, que são o
canal que o próprio portal oferece para consumo automatizado."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .http import PoliteClient, SourceBlocked, SourceError

log = logging.getLogger(__name__)
PROTOCOL = "2025-06-18"


class MCPClient:
    def __init__(self, http: PoliteClient, endpoint: str, client_name: str = "radar-moradia"):
        self.http = http
        self.endpoint = endpoint
        self.client_name = client_name
        self.session_id: Optional[str] = None
        self._id = 0
        self.last_headers: dict = {}

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream",
             "MCP-Protocol-Version": PROTOCOL}
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    @staticmethod
    def _parse_body(resp_text: str, content_type: str) -> dict:
        if "text/event-stream" in content_type:
            # Pega o último evento "data:" que contenha JSON-RPC
            payload = None
            for line in resp_text.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
            if not payload:
                raise SourceError("Resposta SSE sem dados")
            return json.loads(payload)
        return json.loads(resp_text)

    def _post(self, body: dict, expect_response: bool = True) -> Optional[dict]:
        if not self.http.robots(self.endpoint).allowed(self.http.ua, self.endpoint):
            raise SourceBlocked(f"robots.txt não permite {self.endpoint}")
        self.http._throttle(self.endpoint.split("/")[2])
        self.http.requests_made += 1
        try:
            r = self.http.s.post(self.endpoint, json=body, headers=self._headers(),
                                 timeout=self.http.timeout)
        except Exception as e:  # rede
            raise SourceError(f"MCP inacessível: {e}") from e
        self.last_headers = dict(r.headers)
        if r.status_code in (401, 403, 429):
            raise SourceBlocked(f"MCP recusou acesso: HTTP {r.status_code}")
        if r.status_code >= 400:
            raise SourceError(f"MCP HTTP {r.status_code}: {r.text[:200]}")
        sid = r.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        if not expect_response or not r.text.strip():
            return None
        data = self._parse_body(r.text, r.headers.get("Content-Type", ""))
        if "error" in data:
            raise SourceError(f"MCP erro: {data['error']}")
        return data.get("result")

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def initialize(self) -> dict:
        res = self._post({"jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
                          "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                                     "clientInfo": {"name": self.client_name, "version": "1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_response=False)
        return res or {}

    def list_tools(self) -> list[dict]:
        res = self._post({"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/list"})
        return (res or {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> Any:
        """Retorna o conteúdo estruturado (structuredContent) ou o JSON do texto."""
        res = self._post({"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}}) or {}
        if res.get("isError"):
            txt = " ".join(c.get("text", "") for c in res.get("content", []))
            raise SourceError(f"Ferramenta {name} retornou erro: {txt[:300]}")
        if "structuredContent" in res:
            return res["structuredContent"]
        for c in res.get("content", []):
            if c.get("type") == "text":
                try:
                    return json.loads(c["text"])
                except (ValueError, KeyError):
                    return {"_text": c.get("text", "")}
        return res
