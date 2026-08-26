"""Task 6: token auth on FastAPI control plane + Flask dashboard.

Covers: 401 fail-closed behavior, /api/health exemption, token bootstrap
(get_api_token), and the non-loopback bind startup guard (assert_safe_bind).
"""

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from config import assert_safe_bind, get_api_token
from tests.conftest import auth_headers

TOKEN = "test-token-123"


@pytest.fixture(autouse=True)
def _token_env(monkeypatch):
    monkeypatch.setenv("BUDDY_API_TOKEN", TOKEN)


# ---------------------------------------------------------------------------
# FastAPI control plane (assistant/api_server.py)
# ---------------------------------------------------------------------------


def _api_client():
    from fastapi.testclient import TestClient

    from assistant.api_server import app

    return TestClient(app)


def test_fastapi_rejects_missing_token():
    response = _api_client().get("/api/status")

    assert response.status_code == 401


def test_fastapi_rejects_wrong_token():
    response = _api_client().get("/api/status", headers={"X-Buddy-Token": "wrong"})

    assert response.status_code == 401


def test_fastapi_accepts_correct_token():
    response = _api_client().get("/api/status", headers=auth_headers(TOKEN))

    assert response.status_code == 200


def test_fastapi_health_is_exempt():
    response = _api_client().get("/api/health")

    assert response.status_code == 200


def test_fastapi_websocket_wrong_token_rejected():
    from fastapi import WebSocketDisconnect

    for path in ("/ws", "/aionui"):
        with pytest.raises(Exception) as excinfo:
            with _api_client().websocket_connect(f"{path}?token=wrong"):
                pass
        assert isinstance(excinfo.value, WebSocketDisconnect), (
            f"{path} should reject at handshake"
        )
        assert excinfo.value.code == 4401


def test_fastapi_websocket_correct_token_accepted():
    client = _api_client()
    pong = None
    try:
        with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
    except Exception:
        # Teardown may raise from pre-existing disconnect handling under the
        # test transport; only handshake + round-trip are asserted here.
        pass
    assert pong == {"type": "pong"}


def test_fastapi_options_preflight_is_exempt():
    response = _api_client().options("/api/status")

    assert response.status_code == 405


def test_fastapi_protected_post_without_token_rejected():
    response = _api_client().post("/api/chat", json={"message": "hi"})

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Flask dashboard (dashboard/app.py)
# ---------------------------------------------------------------------------


def _dash_client():
    from dashboard.app import app as dash_app

    return dash_app.test_client()


def test_flask_rejects_missing_token():
    response = _dash_client().get("/api/status")

    assert response.status_code == 401


def test_flask_rejects_wrong_token():
    response = _dash_client().get("/api/status", headers={"X-Buddy-Token": "nope"})

    assert response.status_code == 401


def test_flask_accepts_correct_token():
    response = _dash_client().get("/api/status", headers=auth_headers(TOKEN))

    assert response.status_code == 200


def test_flask_health_is_exempt():
    response = _dash_client().get("/api/health")

    assert response.status_code == 200


class _EmptyBridge:
    def current_state(self):
        return "idle"

    def drain(self, timeout=20.0):
        return iter(())


def test_flask_sse_stream_accepts_query_param_token(monkeypatch):
    """EventSource cannot set headers — SSE GETs may authenticate via ?token=."""
    import dashboard.app as dash_module

    monkeypatch.setattr(dash_module, "_bridge", _EmptyBridge())
    client = dash_module.app.test_client()

    denied = client.get("/stream")
    with_header = client.get("/stream", headers=auth_headers(TOKEN))
    with_query = client.get(f"/stream?token={TOKEN}")

    assert denied.status_code == 401
    assert with_header.status_code == 200
    assert with_query.status_code == 200


def test_flask_index_and_static_are_bootstrap_exempt():
    """/ must render to deliver the token; its static assets load with it."""
    import dashboard.app as dash_module

    client = dash_module.app.test_client()

    page = client.get("/")
    css = client.get("/static/style.css")

    assert page.status_code == 200
    assert "window.__BUDDY_TOKEN__" in page.get_data(as_text=True)
    assert css.status_code != 401


def test_flask_index_injects_token_for_js():
    import dashboard.app as dash_module

    html = dash_module.app.test_client().get("/").get_data(as_text=True)

    assert "window.__BUDDY_TOKEN__" in html
    assert TOKEN in html


def test_flask_options_preflight_is_exempt():
    response = _dash_client().options("/api/status")

    assert response.status_code == 200


def test_flask_protected_post_without_token_rejected():
    response = _dash_client().post("/api/wake")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# In-repo MCP clients attach the auth header (Fix round 2)
# ---------------------------------------------------------------------------


def _load_mcp_module(rel_path: str, name: str):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_buddy_mcp_client_attaches_token_header(monkeypatch):
    import asyncio

    mod = _load_mcp_module("mcp-server/server.py", "buddy_mcp_server")
    monkeypatch.setenv("BUDDY_API_TOKEN", TOKEN)

    captured = {}

    class _FakeResp:
        async def json(self):
            return {"ok": True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            captured.update(kwargs)
            captured["url"] = url
            return _FakeResp()

    monkeypatch.setattr(mod.aiohttp, "ClientSession", _FakeSession)

    result = asyncio.run(mod.call_buddy_api("/api/status"))

    assert result == {"ok": True}
    assert captured["headers"]["X-Buddy-Token"] == TOKEN


def test_companion_ready_probe_attaches_token_header(monkeypatch):
    mod = _load_mcp_module(
        "mcp-server/jarvis_companion_mcp.py", "jarvis_companion_mcp_mod"
    )
    monkeypatch.setenv("BUDDY_API_TOKEN", TOKEN)

    recorded = {}

    class _CM:
        def __enter__(self):
            return object()

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        recorded.update({k.lower(): v for k, v in request.header_items()})
        return _CM()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    assert mod._dashboard_is_ready() is True
    assert recorded.get("x-buddy-token") == TOKEN


# ---------------------------------------------------------------------------
# get_api_token bootstrap (config.py)
# ---------------------------------------------------------------------------


def test_get_api_token_creates_file_once(monkeypatch, tmp_path):
    monkeypatch.delenv("BUDDY_API_TOKEN", raising=False)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)

    first = get_api_token()
    second = get_api_token()

    assert first == second
    assert first
    token_file = tmp_path / "data" / "api_token"
    assert token_file.read_text(encoding="utf-8").strip() == first


def test_get_api_token_env_takes_precedence_over_file(monkeypatch, tmp_path):
    monkeypatch.setenv("BUDDY_API_TOKEN", TOKEN)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)

    assert get_api_token() == TOKEN
    assert not (tmp_path / "data" / "api_token").exists()


def test_get_api_token_does_not_log_value(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("BUDDY_API_TOKEN", raising=False)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)

    with caplog.at_level(logging.INFO):
        token = get_api_token()

    assert token not in caplog.text
    assert "api_token" in caplog.text


# ---------------------------------------------------------------------------
# assert_safe_bind startup guard (config.py)
# ---------------------------------------------------------------------------


def test_assert_safe_bind_raises_for_nonloopback_without_env(monkeypatch):
    monkeypatch.delenv("BUDDY_API_TOKEN", raising=False)

    with pytest.raises(RuntimeError):
        assert_safe_bind("0.0.0.0")


def test_assert_safe_bind_allows_loopback_hosts(monkeypatch):
    monkeypatch.delenv("BUDDY_API_TOKEN", raising=False)

    for host in ("127.0.0.1", "localhost", "::1"):
        assert_safe_bind(host)


def test_assert_safe_bind_allows_nonloopback_with_env_token(monkeypatch):
    monkeypatch.setenv("BUDDY_API_TOKEN", TOKEN)

    assert_safe_bind("0.0.0.0")
