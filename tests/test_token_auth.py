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


def test_fastapi_websocket_unaffected_by_http_auth():
    """Documents current scope: WS handshake is not HTTP-token gated (see report).

    Teardown may raise from the endpoint's receive loop after disconnect
    (pre-existing behaviour under the test transport); the assertion covers
    handshake + round-trip only.
    """
    client = _api_client()
    pong = None
    try:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
    except Exception:
        pass
    assert pong == {"type": "pong"}


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
