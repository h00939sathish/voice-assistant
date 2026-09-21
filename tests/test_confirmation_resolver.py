"""Confirmation transport: the dashboard-driven async resolver.

Contract under test (ToolRunner._request_confirmation + resolve_confirmation):
- When an external resolver is registered, a HIGH/confirm action parks a Future
  keyed by confirmation_id, invokes resolver(tool_name, confirmation_id), and
  BLOCKS until resolve_confirmation() settles it — approve executes, deny cancels.
- resolve_confirmation() on an unknown id returns False (nothing pending).
- With no decision, the wait fails closed on timeout (auto-deny), matching the
  security posture that an unanswered confirmation never runs the action.
"""

import asyncio

import pytest

from assistant.tool_runner import ToolRunner


async def _park_until_pending(runner, cid):
    task = asyncio.create_task(
        runner._request_confirmation(
            "run_command", {"command": "ls"}, "Dry run", confirmation_id=cid
        )
    )
    for _ in range(100):
        await asyncio.sleep(0)
        if runner.has_pending_confirmation(cid):
            return task
    raise AssertionError("confirmation future was never parked")


@pytest.mark.asyncio
async def test_dashboard_resolver_approve_unblocks_action(tmp_path):
    runner = ToolRunner(log_dir=tmp_path, allow_terminal_confirmation=False)
    seen = {}
    runner.set_confirmation_resolver(lambda t, c: seen.setdefault("args", (t, c)))

    task = await _park_until_pending(runner, "cid-approve")
    assert seen["args"] == ("run_command", "cid-approve")

    assert runner.resolve_confirmation("run_command", "cid-approve", True) is True
    assert await task is True
    assert runner.has_pending_confirmation("cid-approve") is False


@pytest.mark.asyncio
async def test_dashboard_resolver_deny_cancels_action(tmp_path):
    runner = ToolRunner(log_dir=tmp_path, allow_terminal_confirmation=False)
    runner.set_confirmation_resolver(lambda t, c: None)

    task = await _park_until_pending(runner, "cid-deny")
    assert runner.resolve_confirmation("run_command", "cid-deny", False) is True
    assert await task is False


@pytest.mark.asyncio
async def test_resolve_unknown_confirmation_id_is_false(tmp_path):
    runner = ToolRunner(log_dir=tmp_path)
    assert runner.resolve_confirmation("run_command", "does-not-exist", True) is False


@pytest.mark.asyncio
async def test_dashboard_confirmation_times_out_fail_closed(tmp_path, monkeypatch):
    runner = ToolRunner(log_dir=tmp_path, allow_terminal_confirmation=False)
    monkeypatch.setattr(ToolRunner, "CONFIRM_TIMEOUT_SECONDS", 0.05)
    runner.set_confirmation_resolver(lambda t, c: None)

    # No external decision arrives → the wait must expire and deny.
    approved = await runner._request_confirmation(
        "run_command", {"command": "ls"}, "Dry run", confirmation_id="cid-timeout"
    )
    assert approved is False
    assert runner.has_pending_confirmation("cid-timeout") is False


@pytest.mark.asyncio
async def test_resolver_wired_end_to_end_through_execute(tmp_path, monkeypatch):
    """execute() drives the resolver path for a confirm-level tool."""
    import assistant.authority_gate as ag
    from assistant.skills_registry import registry
    from assistant.tool_runner import ToolStatus

    # Force the gate to treat this tool as a confirm-level action.
    gate = ag.AuthorityGate(audit_db_path=tmp_path / "audit.db")
    monkeypatch.setitem(gate._tool_risk_map, "confirm_probe", ag.RiskLevel.HIGH)

    class ProbeSkill:
        def __init__(self):
            self.calls = 0

        async def handle_tool_call(self, args, context=None):
            self.calls += 1
            return "ran"

    probe = ProbeSkill()
    monkeypatch.setattr(registry, "get_skill_names", lambda: {"confirm_probe"})
    monkeypatch.setattr(registry, "create_instance", lambda name: probe)

    runner = ToolRunner(log_dir=tmp_path, allow_terminal_confirmation=False)
    runner._gate = gate
    runner.set_confirmation_resolver(lambda t, c: None)

    task = asyncio.create_task(
        runner.execute("confirm_probe", {"x": 1}, user_intent="probe")
    )
    # Find the parked confirmation id from the runner's pending registry.
    cid = None
    for _ in range(100):
        await asyncio.sleep(0)
        pending = list(runner._pending_confirms.keys())
        if pending:
            cid = pending[0]
            break
    assert cid is not None, "execute() did not park a confirmation"

    assert runner.resolve_confirmation("confirm_probe", cid, True) is True
    result = await task
    assert result.status == ToolStatus.OK
    assert probe.calls == 1
