"""Task 3 contract tests: dashboard serves live data only — no fictional panels."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dashboard.app as dashboard_app
from assistant.task_executor import Task, TaskState, TaskStep
from tests.conftest import TEST_TOKEN, auth_headers

FICTIONAL_STRINGS = [
    "ternary bonsai",
    "deepseek v4 pro",
    "railway",
    "openbb",
    "sathish",
]

REMOVED_ROUTES = [
    "/api/ecosystem",
    "/api/routing",
    "/api/objectives",
    "/api/automations",
    "/api/alerts",
]


class StubBridge:
    def __init__(self, state="idle"):
        self._state = state

    def current_state(self):
        return self._state


class FakeExecutor:
    """Minimal stand-in exposing the TaskExecutor surface the dashboard reads."""

    def __init__(self):
        self.task = Task(
            id="t1",
            goal="draft report",
            state=TaskState.RUNNING,
            current_step_index=0,
            steps=[
                TaskStep(
                    tool_name="write_file",
                    args={},
                    description="Draft the report",
                )
            ],
        )

    def get_all_tasks(self):
        return [self.task]

    def get_active_task(self):
        return self.task


class FakeRouter:
    """Minimal stand-in exposing last provider health-check results."""

    def get_provider_health(self):
        return [{"provider": "ollama", "ok": True, "model": "qwen3"}]


def _client():
    return dashboard_app.app.test_client()


def _wire_live(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_bridge", StubBridge("idle"))
    monkeypatch.setattr(dashboard_app, "_task_executor_source", FakeExecutor())
    monkeypatch.setattr(dashboard_app, "_llm_router", FakeRouter())


def _assert_no_fictional_strings(payload_text: str) -> None:
    lowered = payload_text.lower()
    for fictional in FICTIONAL_STRINGS:
        assert fictional not in lowered, f"found fictional string: {fictional}"


# ---------------------------------------------------------------------------
# Live data endpoints
# ---------------------------------------------------------------------------


def test_objective_comes_from_running_task(monkeypatch):
    _wire_live(monkeypatch)

    response = _client().get("/api/objective", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 200
    assert response.get_json() == {"objective": "draft report"}
    _assert_no_fictional_strings(response.get_data(as_text=True))


def test_tasks_queue_reflects_task_executor(monkeypatch):
    _wire_live(monkeypatch)

    response = _client().get("/api/tasks", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 200
    tasks = response.get_json()
    assert isinstance(tasks, list)
    assert len(tasks) == 1
    assert tasks[0]["goal"] == "draft report"
    assert tasks[0]["state"] == "running"
    assert any(
        step["description"] == "Draft the report" for step in tasks[0]["steps"]
    )
    _assert_no_fictional_strings(response.get_data(as_text=True))


def test_model_routing_reflects_provider_health(monkeypatch):
    _wire_live(monkeypatch)

    response = _client().get("/api/model-routing", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 200
    rows = response.get_json()
    assert rows == [{"provider": "ollama", "status": "online", "model": "qwen3"}]
    _assert_no_fictional_strings(response.get_data(as_text=True))


def test_memory_owner_name_from_config(monkeypatch):
    _wire_live(monkeypatch)
    monkeypatch.setattr(dashboard_app, "USER_NAME", "TestOwner")

    response = _client().get("/api/memory", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["name"] == "TestOwner"
    _assert_no_fictional_strings(response.get_data(as_text=True))


def test_status_reports_bridge_state_and_live_tasks(monkeypatch):
    _wire_live(monkeypatch)

    response = _client().get("/api/status", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "idle"
    assert any(t["goal"] == "draft report" for t in payload["tasks"])
    assert "agents" not in payload
    _assert_no_fictional_strings(response.get_data(as_text=True))


def test_agent_log_served_from_bridge_events(monkeypatch):
    class BridgeWithEvents(StubBridge):
        def recent_tool_events(self, limit=20):
            return [
                {
                    "tool_name": "search_web",
                    "kind": "finished",
                    "summary": "2 results",
                    "timestamp": "2026-08-26T10:00:00",
                }
            ]

    monkeypatch.setattr(dashboard_app, "_bridge", BridgeWithEvents("idle"))
    monkeypatch.setattr(dashboard_app, "_task_executor_source", FakeExecutor())
    monkeypatch.setattr(dashboard_app, "_llm_router", FakeRouter())

    response = _client().get("/api/agent/log", headers=auth_headers(TEST_TOKEN))

    assert response.status_code == 200
    entries = response.get_json()
    assert len(entries) == 1
    assert "search_web" in entries[0]["message"]
    _assert_no_fictional_strings(response.get_data(as_text=True))


# ---------------------------------------------------------------------------
# Removed fictional panels return 404
# ---------------------------------------------------------------------------


def test_removed_panel_routes_return_404(monkeypatch):
    _wire_live(monkeypatch)
    client = _client()

    for route in REMOVED_ROUTES:
        response = client.get(route, headers=auth_headers(TEST_TOKEN))
        assert response.status_code == 404, f"{route} should be removed (404)"


# ---------------------------------------------------------------------------
# Graceful empty states when live references are missing
# ---------------------------------------------------------------------------


def test_missing_live_refs_yield_empty_states_not_errors(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_bridge", None)
    monkeypatch.setattr(dashboard_app, "_task_executor_source", None)
    monkeypatch.setattr(dashboard_app, "_llm_router", None)
    client = _client()

    objective = client.get("/api/objective", headers=auth_headers(TEST_TOKEN))
    assert objective.status_code == 200
    assert objective.get_json() == {"objective": None}

    tasks = client.get("/api/tasks", headers=auth_headers(TEST_TOKEN))
    assert tasks.status_code == 200
    assert tasks.get_json() == []

    routing = client.get("/api/model-routing", headers=auth_headers(TEST_TOKEN))
    assert routing.status_code == 200
    assert routing.get_json() == []

    agent_log = client.get("/api/agent/log", headers=auth_headers(TEST_TOKEN))
    assert agent_log.status_code == 200
    assert agent_log.get_json() == []
