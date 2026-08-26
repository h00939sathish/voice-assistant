from dashboard import app as dashboard_app
from tests.conftest import TEST_TOKEN, auth_headers


class StubBridge:
    def __init__(self, state="idle"):
        self._state = state

    def current_state(self):
        return self._state


def test_companion_wake_triggers_existing_listener_when_idle(monkeypatch):
    calls = []
    monkeypatch.setattr(dashboard_app, "_bridge", StubBridge("idle"))
    monkeypatch.setattr(dashboard_app, "_wake_callback", lambda: calls.append("wake"))

    client = dashboard_app.app.test_client()
    response = client.post("/api/companion/wake", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 200
    assert response.get_json() == {"accepted": True, "state": "LISTENING"}
    assert calls == ["wake"]


def test_companion_wake_rejects_overlapping_activation(monkeypatch):
    calls = []
    monkeypatch.setattr(dashboard_app, "_bridge", StubBridge("speaking"))
    monkeypatch.setattr(dashboard_app, "_wake_callback", lambda: calls.append("wake"))

    client = dashboard_app.app.test_client()
    response = client.post("/api/companion/wake", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 409
    assert response.get_json() == {
        "accepted": False,
        "reason": "assistant_busy",
        "state": "SPEAKING",
    }
    assert calls == []


def test_companion_wake_reports_unavailable_when_callback_missing(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_bridge", StubBridge("idle"))
    monkeypatch.setattr(dashboard_app, "_wake_callback", None)

    client = dashboard_app.app.test_client()
    response = client.post("/api/companion/wake", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 503
    assert response.get_json() == {
        "accepted": False,
        "reason": "wake_unavailable",
        "state": "IDLE",
    }


def test_companion_state_reports_current_state_for_reconnect(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_bridge", StubBridge("processing"))
    monkeypatch.setattr(dashboard_app, "_wake_callback", lambda: None)

    client = dashboard_app.app.test_client()
    response = client.get("/api/companion/state", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "PROCESSING"
    assert payload["wake_word_enabled"] is True
    assert isinstance(payload["timestamp"], str)
