import importlib.util
import json
from pathlib import Path

CLIENT_PATH = (
    Path(__file__).resolve().parents[1]
    / "mcp-tools"
    / "google-mcp"
    / "apps_script_client.py"
)


def _load_client_module():
    spec = importlib.util.spec_from_file_location(
        "google_apps_script_client", CLIENT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def test_call_bridge_sends_secret_in_body_not_query_string(monkeypatch):
    module = _load_client_module()
    module.APPS_SCRIPT_URL = "https://script.google.com/macros/s/test/exec"
    module.APPS_SCRIPT_SECRET = "top-secret"

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return _FakeResponse('{"ok": true}')

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    result = module.call_bridge("gmail_search", {"query": "from:boss"})

    assert result["ok"] is True
    assert captured["url"] == "https://script.google.com/macros/s/test/exec"
    payload = json.loads(captured["body"])
    assert payload["action"] == "gmail_search"
    assert payload["secret"] == "top-secret"
    assert payload["params"] == {"query": "from:boss"}
    assert "secret=" not in captured["url"]
    assert captured["timeout"] == module.TIMEOUT


def test_is_configured_requires_url_and_secret():
    module = _load_client_module()
    module.APPS_SCRIPT_URL = "https://script.google.com/macros/s/test/exec"
    module.APPS_SCRIPT_SECRET = ""
    assert module.is_configured() is False

    module.APPS_SCRIPT_SECRET = "secret"
    assert module.is_configured() is True


def test_call_bridge_rejects_secret_that_matches_script_id():
    module = _load_client_module()
    module.APPS_SCRIPT_URL = (
        "https://script.google.com/macros/s/"
        "AKfycbybaMxiDix4wMgh0j8mDSeWCvs_Q1tUG9JyYCv7K7R1vffRnYq8mi89f9Ty8H8lXSKHsA"
        "/exec"
    )
    module.APPS_SCRIPT_SECRET = (
        "AKfycbybaMxiDix4wMgh0j8mDSeWCvs_Q1tUG9JyYCv7K7R1vffRnYq8mi89f9Ty8H8lXSKHsA"
    )

    result = module.call_bridge("calendar_list", {"days_ahead": 1})

    assert result["ok"] is False
    assert "deployment ID" in result["error"]
