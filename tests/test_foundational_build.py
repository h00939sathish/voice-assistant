import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assistant.authority_gate import ActionOutcome, AuthorityGate, RiskLevel
from assistant.llm_router import LLMRouter
from assistant.long_term_memory import LongTermMemory
from assistant.operator_dashboard import OperatorDashboard
from assistant.skills_registry import SkillsRegistry
from assistant.task_executor import TaskExecutor, TaskStep, TaskState
from assistant.tool_runner import ToolResult, ToolRunner, ToolStatus
from dashboard.app import (
    _merge_operator_payloads,
    _compute_live_api_metrics,
    _compute_authority_summary,
)
from skills.browser_skill import BrowserSkill


def test_authority_gate_applies_configurable_min_level(tmp_path):
    gate = AuthorityGate(audit_db_path=tmp_path / "authority_audit.db")
    gate.min_level = RiskLevel.MEDIUM

    allowed, _ = gate.check("open_app", {"name": "Calculator"})

    assert allowed is False
    assert gate.get_action_outcome("open_app", {"name": "Calculator"}) == ActionOutcome.CONFIRM


def test_authority_gate_infers_contextual_risk_for_multiplexer_tools(tmp_path):
    gate = AuthorityGate(audit_db_path=tmp_path / "authority_audit.db")

    assert gate.classify_risk("calendar", {"action": "list"}) == RiskLevel.LOW
    assert gate.classify_risk("calendar", {"action": "create", "summary": "Standup"}) == RiskLevel.HIGH
    assert gate.classify_risk("clipboard", {"command": "read clipboard"}) == RiskLevel.LOW
    assert gate.classify_risk("clipboard", {"command": "copy hello world"}) == RiskLevel.HIGH


def test_authority_gate_classifies_mcp_tool_by_underlying_name(tmp_path):
    gate = AuthorityGate(audit_db_path=tmp_path / "authority_audit.db")

    assert gate.classify_risk("mcp__router__search_web", {}) == RiskLevel.LOW
    assert gate.classify_risk("mcp__router__shutdown_system", {}) == RiskLevel.CRITICAL


def test_tool_runner_only_auto_retries_low_risk_or_explicit_idempotent_tools(tmp_path):
    runner = ToolRunner(log_dir=tmp_path)

    assert runner._is_safe_to_retry("weather", RiskLevel.LOW) is True
    assert runner._is_safe_to_retry("open_app", RiskLevel.MEDIUM) is False

    runner._policy_idempotent_tools = {"custom_fetch"}
    assert runner._is_safe_to_retry("custom_fetch", RiskLevel.MEDIUM) is True


@pytest.mark.asyncio
async def test_tool_runner_denies_confirmation_level_action_before_execution(tmp_path):
    runner = ToolRunner(log_dir=tmp_path, confirmation_callback=lambda _prompt: False)

    result = await runner.execute(
        "calendar",
        {"action": "create", "summary": "Standup", "start_time": "2026-03-26T09:00:00"},
        user_intent="Schedule the standup",
    )

    assert result.status == ToolStatus.REQUIRES_CONFIRMATION
    assert "calendar" in result.summary.lower()


@pytest.mark.asyncio
async def test_tool_runner_can_disable_terminal_confirmation(tmp_path):
    runner = ToolRunner(log_dir=tmp_path, allow_terminal_confirmation=False)

    with patch("builtins.input", side_effect=AssertionError("terminal input should not be called")):
        result = await runner.execute(
            "calendar",
            {"action": "create", "summary": "Standup", "start_time": "2026-03-26T09:00:00"},
            user_intent="Schedule the standup",
        )

    assert result.status == ToolStatus.REQUIRES_CONFIRMATION


@pytest.mark.asyncio
async def test_task_executor_persists_progress_between_steps(tmp_path):
    class SnapshotRunner:
        def __init__(self, state_path):
            self.state_path = state_path
            self.snapshot = None

        async def execute(self, tool_name, args, *, user_intent="", context=None):
            if tool_name == "step_two":
                self.snapshot = json.loads(self.state_path.read_text(encoding="utf-8"))
            return ToolResult(
                status=ToolStatus.OK,
                summary=f"{tool_name} completed",
                data={"tool_name": tool_name},
                tool_name=tool_name,
                args=args,
            )

    runner = SnapshotRunner(tmp_path / TaskExecutor.STATE_FILE)
    executor = TaskExecutor(runner, state_dir=tmp_path)
    task = executor.create_task(
        "Run two steps",
        [
            TaskStep(tool_name="step_one", args={}),
            TaskStep(tool_name="step_two", args={}),
        ],
    )

    await executor.run(task.id)

    assert runner.snapshot is not None
    persisted_task = runner.snapshot["tasks"][task.id]
    assert persisted_task["current_step_index"] == 1
    assert persisted_task["steps"][0]["status"] == "done"


def test_task_executor_workflow_templates_and_summary(tmp_path):
    class NoopRunner:
        async def execute(self, tool_name, args, *, user_intent="", context=None):
            return ToolResult(
                status=ToolStatus.OK,
                summary=f"{tool_name} completed",
                data={"tool_name": tool_name},
                tool_name=tool_name,
                args=args,
            )

    executor = TaskExecutor(NoopRunner(), state_dir=tmp_path)
    steps = [TaskStep(tool_name="search_web", args={"query": "daily brief"})]
    assert executor.register_workflow("daily_brief", steps, "Daily summary workflow")

    task = executor.create_task_from_workflow("daily_brief", goal="Run daily brief")
    assert task is not None
    assert task.goal == "Run daily brief"
    assert len(task.steps) == 1

    task.state = TaskState.RUNNING
    summary = executor.get_task_summary()
    assert "Active task" in summary
    assert task.id in summary


@pytest.mark.asyncio
async def test_llm_router_handles_task_control_without_provider_calls():
    class StubTask:
        def __init__(self, task_id: str, state: TaskState):
            self.id = task_id
            self.goal = "Run task"
            self.state = state
            self.updated_at = "2026-03-25T18:00:00"

    class StubExecutor:
        def __init__(self):
            self.active = StubTask("run123", TaskState.RUNNING)
            self.paused = StubTask("pause123", TaskState.PAUSED)
            self.pause_called = None
            self.resume_called = None

        def get_task_summary(self):
            return "Active task run123: Run task (step 1/1)"

        def get_all_tasks(self):
            return [self.active, self.paused]

        def get_active_task(self):
            return self.active

        def get_latest_paused_task(self):
            return self.paused

        def get_task(self, task_id):
            if task_id == self.active.id:
                return self.active
            if task_id == self.paused.id:
                return self.paused
            return None

        def pause(self, task_id=None):
            self.pause_called = task_id

        async def resume(self, task_id):
            self.resume_called = task_id
            return self.paused

    router = LLMRouter()
    stub = StubExecutor()
    router.set_task_executor(stub)

    status = await router.chat("task status", history=[])
    assert status.startswith("Active task run123")

    paused = await router.chat("pause current task", history=[])
    assert "Pause requested for task run123" in paused
    assert stub.pause_called == "run123"

    resumed = await router.chat("resume last task", history=[])
    assert "Resuming task pause123 in the background." == resumed
    await asyncio.sleep(0)
    assert stub.resume_called == "pause123"


@pytest.mark.asyncio
async def test_llm_router_stops_after_confirmation_denial():
    router = LLMRouter()
    router._ollama_available = True
    router._check_ollama = lambda: True
    router._dynamic_tool_discovery = False
    router._decide_action = AsyncMock(return_value="use_tools")
    router._classify_intent = AsyncMock(return_value="fast")
    router._get_all_tools_async = AsyncMock(return_value=[{
        "type": "function",
        "function": {
            "name": "clipboard",
            "description": "Clipboard control",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    }])
    router._tool_runner.execute = AsyncMock(return_value=ToolResult(
        status=ToolStatus.REQUIRES_CONFIRMATION,
        summary="Action 'clipboard' was denied.",
        tool_name="clipboard",
        args={"command": "copy YouTube"},
    ))

    tool_call_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "clipboard",
                    "arguments": {"command": "copy YouTube"},
                }
            }
        ],
    }

    with patch("ollama.chat") as mock_chat:
        mock_chat.return_value = {"message": tool_call_msg}
        response = await router.chat("Copy YouTube")

    assert "too many steps" in response.lower() or "denied" in response.lower()
    assert mock_chat.call_count == 1


def test_skills_registry_prefers_custom_tool_schema_for_browser():
    tools = SkillsRegistry.get_tool_definitions()
    tool_names = {tool["function"]["name"] for tool in tools}

    assert "browser_search" in tool_names
    assert "browser_navigate" in tool_names
    assert "browser" not in tool_names


def test_browser_skill_normalizes_generic_search_command():
    skill = BrowserSkill()
    tool_name, args = LLMRouter._normalize_model_tool_call(
        "browser",
        {"command": "open Edge Browser and search for YouTube"},
        "open Edge Browser and search for YouTube",
    )

    assert tool_name == "browser_search"
    assert args["query"] == "YouTube"


def test_long_term_memory_prompt_reads_canonical_categories(tmp_path):
    memory = LongTermMemory(tmp_path / "memory.db")
    memory.remember_this("My favorite editor is VS Code", category="profile")
    memory.always_do("temperature", "use Celsius")

    facts = memory.get_facts_for_prompt()

    assert "My favorite editor is VS Code" in facts
    assert "use Celsius" in facts


def test_operator_dashboard_reads_runtime_artifacts(tmp_path):
    events_path = tmp_path / "events.jsonl"
    exec_path = tmp_path / "execution_log.jsonl"
    task_state_path = tmp_path / "task_state.json"

    events_path.write_text(
        "\n".join([
            json.dumps({"type": "SubsystemStateEvent", "subsystem": "llm", "state": "healthy"}),
            json.dumps({"type": "SubsystemStateEvent", "subsystem": "stt", "state": "initializing"}),
        ]),
        encoding="utf-8",
    )
    exec_path.write_text(
        json.dumps({
            "tool_name": "weather",
            "status": "ok",
            "duration_ms": 120,
            "result_summary": "Sunny",
        }) + "\n",
        encoding="utf-8",
    )
    task_state_path.write_text(
        json.dumps({
            "tasks": {
                "abc123": {
                    "goal": "Check weather",
                    "state": "running",
                    "steps": [],
                }
            }
        }),
        encoding="utf-8",
    )

    dashboard = OperatorDashboard(tmp_path)
    status = dashboard.get_full_status()

    assert status["subsystem_health"]["llm"] == "healthy"
    assert status["subsystem_health"]["stt"] == "initializing"
    assert status["recent_actions"][0]["tool_name"] == "weather"
    assert "abc123" in status["task_state"]["tasks"]


def test_operator_payload_merge_prefers_live_bridge_and_keeps_persisted_details():
    bridge_status = {
        "state": "processing",
        "timestamp": "2026-03-25T10:00:00",
        "subsystem_health": {"llm": "healthy", "mcp": "degraded"},
        "recent_tool_events": [
            {
                "tool_name": "search_web",
                "duration_ms": 210,
                "summary": "2 results",
                "kind": "finished",
            },
            {
                "tool_name": "send_email",
                "duration_ms": 430,
                "error": "denied",
                "kind": "failed",
            },
            {
                "tool_name": "send_email",
                "action": "requested",
                "dry_run": "Would send an email",
                "kind": "confirmation",
            },
        ],
        "active_tasks": {
            "task-1": {"goal": "Check weather", "action": "running"}
        },
    }
    file_status = {
        "timestamp": "2026-03-25T09:59:00",
        "subsystem_health": {"llm": "down", "stt": "healthy"},
        "recent_actions": [
            {"tool_name": "weather", "duration_ms": 120, "result_summary": "Sunny", "status": "ok"}
        ],
        "task_state": None,
        "tool_failures": [{"tool_name": "send_email", "error": "denied"}],
        "api_stats": {"total_calls": 7},
    }

    merged = _merge_operator_payloads(bridge_status, file_status)

    assert merged["state"] == "processing"
    assert merged["subsystem_health"]["llm"] == "healthy"
    assert merged["subsystem_health"]["stt"] == "healthy"
    assert merged["recent_actions"][0]["tool_name"] == "search_web"
    assert any(action["tool_name"] == "weather" for action in merged["recent_actions"])
    assert merged["task_state"]["tasks"]["task-1"]["state"] == "running"
    assert merged["api_stats"]["total_calls"] == 7
    assert merged["api_stats"]["live_recent_calls"] == 3
    assert merged["operator_metrics"]["recent_failures"] >= 1
    assert len(merged["confirmation_events"]) >= 1
    assert "approved" in merged["authority_summary"]


def test_compute_live_api_metrics_and_authority_summary():
    metrics = _compute_live_api_metrics([
        {"kind": "finished", "tool_name": "search_web", "duration_ms": 120},
        {"kind": "failed", "tool_name": "send_email", "duration_ms": 90},
        {"kind": "confirmation", "tool_name": "send_email", "action": "requested"},
        {"kind": "finished", "tool_name": "search_web", "duration_ms": 180},
    ])
    assert metrics["live_recent_calls"] == 4
    assert metrics["live_recent_success"] == 2
    assert metrics["live_recent_failures"] == 1
    assert metrics["live_recent_confirmations"] == 1
    assert metrics["live_top_tools"]["search_web"] == 2

    summary = _compute_authority_summary([
        {"was_approved": 1, "action_outcome": "confirm", "risk_level": 3},
        {"was_approved": 0, "action_outcome": "confirm", "risk_level": 3},
        {"was_approved": 0, "action_outcome": "blocked", "risk_level": 4},
    ])
    assert summary["approved"] == 1
    assert summary["denied"] == 1
    assert summary["blocked"] == 1
    assert summary["high_risk_events"] == 3
