"""
Integration tests for the tool execution pipeline:
    llm_router → tool_runner → authority_gate

Tests ToolRunner execution, safety gate checks, and normalized result schema.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from assistant.authority_gate import ActionOutcome, AuthorityGate, RiskLevel
from assistant.tool_runner import ToolResult, ToolRunner, ToolStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Temp directory for logs and state."""
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture
def safety_policy(tmp_data_dir):
    """Create a test safety policy."""
    policy = {
        "tools": {
            "get_weather": "LOW",
            "send_email": "HIGH",
            "delete_all_files": "CRITICAL",
            "set_volume": "MEDIUM",
        }
    }
    policy_path = tmp_data_dir / "data" / "safety_policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    return policy_path


@pytest.fixture
def gate(safety_policy, tmp_data_dir):
    """AuthorityGate with test policy."""
    audit_path = tmp_data_dir / "data" / "authority_audit.db"
    with patch("assistant.authority_gate._POLICY_PATH", safety_policy):
        g = AuthorityGate(audit_db_path=audit_path)
        g.enabled = True
        g.min_level = RiskLevel.HIGH
        g.reload_policy()
        return g


@pytest.fixture
def runner(tmp_data_dir):
    """ToolRunner with test data dir."""
    r = ToolRunner(status_callback=lambda s: None)
    r._log_path = tmp_data_dir / "data" / "execution_log.jsonl"
    return r


# ---------------------------------------------------------------------------
# Authority Gate Tests
# ---------------------------------------------------------------------------


class TestAuthorityGate:
    def test_low_risk_is_safe(self, gate):
        outcome = gate.get_action_outcome("get_weather")
        assert outcome == ActionOutcome.SAFE

    def test_high_risk_requires_confirm(self, gate):
        outcome = gate.get_action_outcome("send_email")
        assert outcome == ActionOutcome.CONFIRM

    def test_critical_is_blocked(self, gate):
        outcome = gate.get_action_outcome("delete_all_files")
        assert outcome == ActionOutcome.BLOCKED

    def test_unknown_tool_defaults_to_medium(self, gate):
        risk = gate.classify_risk("unknown_tool")
        assert risk == RiskLevel.MEDIUM

    def test_check_allows_safe_tool(self, gate):
        allowed, reason = gate.check("get_weather", {})
        assert allowed is True

    def test_check_blocks_critical_tool(self, gate):
        allowed, reason = gate.check("delete_all_files", {})
        assert allowed is False
        assert "blocked" in reason.lower() or "CRITICAL" in reason

    def test_policy_summary(self, gate):
        summary = gate.get_policy_summary()
        assert "get_weather" in summary["safe"]
        assert "delete_all_files" in summary["blocked"]

    def test_from_risk_with_min_level(self):
        # MEDIUM risk with min_level=MEDIUM → confirm
        assert (
            ActionOutcome.from_risk(RiskLevel.MEDIUM, RiskLevel.MEDIUM)
            == ActionOutcome.CONFIRM
        )
        # MEDIUM risk with min_level=HIGH → safe
        assert (
            ActionOutcome.from_risk(RiskLevel.MEDIUM, RiskLevel.HIGH)
            == ActionOutcome.SAFE
        )
        # CRITICAL always blocked regardless of min_level
        assert (
            ActionOutcome.from_risk(RiskLevel.CRITICAL, RiskLevel.LOW)
            == ActionOutcome.BLOCKED
        )


# ---------------------------------------------------------------------------
# ToolRunner Tests
# ---------------------------------------------------------------------------


class TestToolRunner:
    @pytest.mark.asyncio
    async def test_result_schema(self, runner):
        """ToolResult has the expected fields."""
        result = ToolResult(
            status=ToolStatus.OK,
            data={"key": "value"},
            summary="Test passed",
            tool_name="test_tool",
            args={},
            duration_ms=42,
        )
        assert result.status == ToolStatus.OK
        assert result.summary == "Test passed"
        assert result.duration_ms == 42

    @pytest.mark.asyncio
    async def test_result_to_content_str(self, runner):
        """to_content_str returns machine-readable content."""
        result = ToolResult(
            status=ToolStatus.OK,
            data={"answer": 42},
            summary="Got answer",
            tool_name="calculator",
            args={},
        )
        content = result.to_content_str()
        assert "42" in content

    @pytest.mark.asyncio
    async def test_blocked_tool_returns_blocked_status(self, runner):
        """CRITICAL tools should be blocked outright."""
        # Mock the gate to block
        mock_gate = MagicMock()
        mock_gate.check.return_value = (False, "CRITICAL → blocked")
        mock_gate.classify_risk.return_value = RiskLevel.CRITICAL
        mock_gate.log_action = MagicMock()
        runner._get_gate = lambda: mock_gate

        result = await runner.execute("delete_all_files", {})
        assert result.status == ToolStatus.BLOCKED

    def test_tool_status_enum_values(self):
        """All expected status values exist."""
        assert ToolStatus.OK == "ok"
        assert ToolStatus.ERROR == "error"
        assert ToolStatus.RETRYABLE == "retryable"
        assert ToolStatus.REQUIRES_CONFIRMATION == "requires_confirmation"
        assert ToolStatus.BLOCKED == "blocked"


# ---------------------------------------------------------------------------
# Decision Layer Tests (via LLMRouter._decide_action)
# ---------------------------------------------------------------------------


class TestDecisionLayer:
    @pytest.fixture
    def router_cls(self):
        """Import LLMRouter class for decision testing."""
        from assistant.llm_router import LLMRouter

        return LLMRouter

    @pytest.mark.asyncio
    async def test_greeting_is_answer_direct(self, router_cls):
        r = MagicMock(spec=router_cls)
        r._NO_TOOL_PATTERNS = router_cls._NO_TOOL_PATTERNS
        r._ACTION_VERBS = router_cls._ACTION_VERBS
        result = await router_cls._decide_action(r, "hello")
        assert result == "answer_direct"

    @pytest.mark.asyncio
    async def test_short_noaction_is_answer_direct(self, router_cls):
        r = MagicMock(spec=router_cls)
        r._NO_TOOL_PATTERNS = router_cls._NO_TOOL_PATTERNS
        r._ACTION_VERBS = router_cls._ACTION_VERBS
        result = await router_cls._decide_action(r, "how are you")
        assert result == "answer_direct"

    @pytest.mark.asyncio
    async def test_compound_is_multi_step(self, router_cls):
        r = MagicMock(spec=router_cls)
        r._NO_TOOL_PATTERNS = router_cls._NO_TOOL_PATTERNS
        r._ACTION_VERBS = router_cls._ACTION_VERBS
        result = await router_cls._decide_action(
            r, "search weather and then send email"
        )
        assert result == "multi_step"

    @pytest.mark.asyncio
    async def test_single_action_is_single_tool(self, router_cls):
        r = MagicMock(spec=router_cls)
        r._NO_TOOL_PATTERNS = router_cls._NO_TOOL_PATTERNS
        r._ACTION_VERBS = router_cls._ACTION_VERBS
        result = await router_cls._decide_action(r, "search for restaurants near me")
        assert result == "single_tool"
