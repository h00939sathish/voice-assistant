import importlib.util
import json
import urllib.error
from pathlib import Path

SERVER_PATH = Path(__file__).parent.parent / "mcp-server" / "jarvis_companion_mcp.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("jarvis_companion_mcp", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_jarvis_click_to_talk_posts_to_companion_wake(monkeypatch):
    server = load_server_module()
    calls = []

    def fake_request(method, endpoint):
        calls.append({"method": method, "endpoint": endpoint})
        return {"accepted": True, "state": "LISTENING"}

    monkeypatch.setattr(server, "_request_json", fake_request)

    result = server.jarvis_click_to_talk()

    assert calls == [{"method": "POST", "endpoint": "/api/companion/wake"}]
    assert "LISTENING" in result
    assert "accepted" in result


def test_jarvis_companion_state_reads_current_state(monkeypatch):
    server = load_server_module()
    calls = []

    def fake_request(method, endpoint):
        calls.append({"method": method, "endpoint": endpoint})
        return {"state": "IDLE", "wake_word_enabled": True, "timestamp": "now"}

    monkeypatch.setattr(server, "_request_json", fake_request)

    result = server.jarvis_companion_state()

    assert calls == [{"method": "GET", "endpoint": "/api/companion/state"}]
    assert "IDLE" in result
    assert "wake_word_enabled" in result


def test_jarvis_click_to_talk_reports_dashboard_unavailable(monkeypatch):
    server = load_server_module()

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    result = server.jarvis_click_to_talk()

    assert "jarvis_dashboard_unavailable" in result
    assert "connection refused" in result


def test_jarvis_click_to_talk_autostarts_jarvis_then_retries(monkeypatch):
    server = load_server_module()
    calls = []
    starts = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"accepted": True, "state": "LISTENING"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise urllib.error.URLError("connection refused")
        return FakeResponse()

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        server, "_start_jarvis_background", lambda: starts.append(True) or 1234
    )
    monkeypatch.setattr(server, "_wait_for_dashboard", lambda: True)

    result = server.jarvis_click_to_talk()

    assert starts == [True]
    assert len(calls) == 2
    assert "LISTENING" in result


def test_jarvis_autostart_can_be_disabled(monkeypatch):
    server = load_server_module()
    monkeypatch.setenv("JARVIS_COMPANION_AUTOSTART", "false")

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    def fail_start():
        raise AssertionError("autostart should be disabled")

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(server, "_start_jarvis_background", fail_start)

    result = server.jarvis_click_to_talk()

    assert "jarvis_dashboard_unavailable" in result
    assert "connection refused" in result
