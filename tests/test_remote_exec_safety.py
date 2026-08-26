"""Task 8: Remote desktop/tool execution behind forced confirmation.

Contract under test (HTTP callers have no human confirmation channel):
- HIGH/CRITICAL-classified actions → 202 requires_confirmation or 403 blocked;
  the underlying executor is NEVER invoked.
- Policy-denied (CRITICAL) → 403 blocked.
- LOW/sub-min-level risk → executes normally (200).
- Every gated decision writes an audit row to the authority audit DB.
"""

import json
import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.conftest import TEST_TOKEN, auth_headers


class ControlledRunner:
    """Real ToolRunner that records whether execution was attempted."""

    def __init__(self, gate, log_dir):
        from assistant.tool_runner import ToolRunner

        self._inner = ToolRunner(
            log_dir=log_dir, confirmation_callback=lambda prompt: False
        )
        self._gate = gate
        self.executed = []

    def _get_gate(self):
        return self._gate

    async def execute(self, tool_name, args, **kwargs):
        self.executed.append((tool_name, args))
        return await self._inner.execute(tool_name, args, **kwargs)


class FakeRouter:
    def __init__(self, runner):
        self.tool_runner = runner


class FakeAssistant:
    def __init__(self, runner):
        self.skill_router = FakeRouter(runner)
        self.pipeline_calls = []

    async def process_text_chat(self, message, speak=False, source="api"):
        self.pipeline_calls.append(message)
        return f"pipeline:{message}"


def _audit_rows(db_path, tool_name):
    with sqlite3.connect(str(db_path)) as conn:
        return conn.execute(
            "SELECT action_outcome, was_approved FROM authority_log "
            "WHERE tool_name = ?",
            (tool_name,),
        ).fetchall()


@pytest.fixture
def remote_env(tmp_path, monkeypatch):
    """Install a fake assistant whose runner uses a controlled AuthorityGate."""
    import assistant.api_server as api_server
    import assistant.authority_gate as authority_gate

    saved_assistant = api_server._assistant
    audit_db = tmp_path / "authority_audit.db"

    def install(policy: dict | None):
        if policy is None:
            policy_path = tmp_path / "absent_policy.json"
        else:
            policy_path = tmp_path / "safety_policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
        monkeypatch.setattr(authority_gate, "_POLICY_PATH", policy_path)

        gate = authority_gate.AuthorityGate(audit_db_path=audit_db)
        runner = ControlledRunner(gate, tmp_path)
        assistant = FakeAssistant(runner)
        api_server.set_assistant(assistant)
        return {
            "client": TestClient(api_server.app),
            "gate": gate,
            "runner": runner,
            "assistant": assistant,
            "audit_db": audit_db,
        }

    yield install

    api_server.set_assistant(saved_assistant)


def _post(client, path, payload):
    return client.post(path, json=payload, headers=auth_headers(TEST_TOKEN))


# ---------------------------------------------------------------------------
# /buddy/tool + /api/skills/run (direct tool execution over HTTP)
# ---------------------------------------------------------------------------


def test_high_risk_remote_tool_returns_202_never_executes(remote_env):
    env = remote_env({"tool_risks": {"run_command": "HIGH"}})

    response = _post(
        env["client"],
        "/buddy/tool",
        {"tool": "run_command", "args": {"command": "echo hi"}},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "requires_confirmation"
    assert env["runner"].executed == []
    rows = _audit_rows(env["audit_db"], "run_command")
    assert rows and rows[0][0] == "confirm" and rows[0][1] == 0
    assert env["gate"].has_pending() is False


def test_critical_risk_remote_tool_blocked_403(remote_env):
    env = remote_env({"tool_risks": {"run_command": "CRITICAL"}})

    response = _post(
        env["client"],
        "/buddy/tool",
        {"tool": "run_command", "args": {"command": "echo hi"}},
    )

    assert response.status_code == 403
    assert response.json()["status"] == "blocked"
    assert env["runner"].executed == []
    rows = _audit_rows(env["audit_db"], "run_command")
    assert rows and rows[0][0] == "blocked" and rows[0][1] == 0


def test_low_risk_remote_tool_executes_normally(remote_env):
    env = remote_env({"tool_risks": {"test_safe_read": "LOW"}})

    response = _post(
        env["client"],
        "/buddy/tool",
        {"tool": "test_safe_read", "args": {"path": "x"}},
    )

    assert response.status_code == 200
    assert len(env["runner"].executed) == 1
    assert response.json()["status"] in {"ok", "error"}


def test_skills_run_route_enforces_same_contract(remote_env):
    env = remote_env({"tool_risks": {"run_command": "HIGH"}})

    response = _post(env["client"], "/api/skills/run", {"skill_name": "run_command"})

    assert response.status_code == 202
    assert response.json()["status"] == "requires_confirmation"
    assert env["runner"].executed == []


def test_dangerous_args_escalate_to_blocked_over_http(remote_env):
    env = remote_env(None)  # builtin policy only

    response = _post(
        env["client"],
        "/buddy/tool",
        {
            "tool": "computer_use",
            "args": {"command": "system_action", "action": "shutdown"},
        },
    )

    assert response.status_code == 403
    assert response.json()["status"] == "blocked"
    assert env["runner"].executed == []


# ---------------------------------------------------------------------------
# /api/desktop/execute (freeform action piped into the chat pipeline)
# ---------------------------------------------------------------------------


def test_desktop_execute_high_action_returns_202_pipeline_not_invoked(remote_env):
    env = remote_env({"tool_risks": {"run_command": "HIGH"}})

    response = _post(
        env["client"],
        "/api/desktop/execute",
        {"action": "run_command", "target": "dir"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "requires_confirmation"
    assert env["assistant"].pipeline_calls == []
    assert env["runner"].executed == []


def test_desktop_execute_critical_action_blocked_403(remote_env):
    env = remote_env({"tool_risks": {"format_drive": "CRITICAL"}})

    response = _post(env["client"], "/api/desktop/execute", {"action": "format_drive"})

    assert response.status_code == 403
    assert response.json()["status"] == "blocked"
    assert env["assistant"].pipeline_calls == []
    rows = _audit_rows(env["audit_db"], "format_drive")
    assert rows and rows[0][0] == "blocked" and rows[0][1] == 0


def test_desktop_execute_safe_action_still_runs_pipeline(remote_env):
    env = remote_env(None)  # builtin policy; screenshot is sub-HIGH risk

    response = _post(env["client"], "/api/desktop/execute", {"action": "screenshot"})

    assert response.status_code == 200
    assert len(env["assistant"].pipeline_calls) == 1
    assert "result" in response.json()
