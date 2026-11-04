import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).parent / "fixtures"

from radar_moradia.pipeline import load_config  # noqa: E402


@pytest.fixture
def cfg():
    return load_config(ROOT / "config.yaml")


@pytest.fixture
def fixture_json():
    def _load(name):
        return json.loads((FIX / name).read_text(encoding="utf-8"))
    return _load


@pytest.fixture
def fixture_text():
    def _load(name):
        return (FIX / name).read_text(encoding="utf-8")
    return _load


class FakeResponse:
    def __init__(self, status=200, text="", headers=None, content=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}
        self.content = content if content is not None else text.encode()


class FakeSession:
    """Sessão HTTP falsa: roteia GET/POST por URL para respostas pré-definidas."""

    def __init__(self, get_routes=None, post_handler=None):
        self.headers = {}
        self.get_routes = get_routes or {}
        self.post_handler = post_handler
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        for prefix, resp in self.get_routes.items():
            if url.startswith(prefix):
                return resp(url) if callable(resp) else resp
        return FakeResponse(404, "")

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        return self.post_handler(url, json, headers)
