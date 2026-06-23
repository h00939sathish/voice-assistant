"""
Tool Runner — Single chokepoint for all tool execution in Buddy.

Owns:
- Authority gate check before execution
- Idempotency-aware retries (only safe/read-only tools)
- Normalized result schema
- Structured JSONL execution logging
- Dry-run summary generation for confirm-level actions
- Event emission for the dashboard pipeline

Result statuses:
    ok, error, retryable, requires_confirmation, blocked, clarification_needed
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


class ToolStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    RETRYABLE = "retryable"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    BLOCKED = "blocked"
    CLARIFICATION_NEEDED = "clarification_needed"


@dataclass
class ToolResult:
    """Normalized result returned from every tool execution."""

    status: ToolStatus
    summary: str
    data: Any = None
    duration_ms: int = 0
    error: str | None = None
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)

    def to_content_str(self) -> str:
        """Produce a string suitable for injecting back into the LLM conversation."""
        if self.status == ToolStatus.OK:
            return str(self.data) if self.data is not None else self.summary
        if self.status == ToolStatus.REQUIRES_CONFIRMATION:
            return self.summary
        if self.status == ToolStatus.BLOCKED:
            return f"🛡️ BLOCKED: {self.summary}"
        if self.status == ToolStatus.CLARIFICATION_NEEDED:
            return f"❓ Clarification needed: {self.summary}"
        # error / retryable — surface the error
        return f"Error executing {self.tool_name}: {self.error or self.summary}"


# ---------------------------------------------------------------------------
# Execution log entry
# ---------------------------------------------------------------------------


@dataclass
class ExecutionLogEntry:
    timestamp: str
    user_intent: str
    tool_name: str
    args: dict[str, Any]
    status: str
    duration_ms: int
    result_summary: str
    failure_reason: str | None = None


# ---------------------------------------------------------------------------
# Safety policy loader
# ---------------------------------------------------------------------------

_DEFAULT_POLICY_PATH = Path(__file__).parent.parent / "data" / "safety_policy.json"

# Tools explicitly marked as idempotent (safe to retry)
_IDEMPOTENT_TOOLS: set = {
    "weather",
    "mock_weather",
    "get_time",
    "search_web",
    "search_tools",
    "memory_control",
    "google_search",
}

# Only explicitly low-risk read-only operations are safe to auto-retry by default.
_SAFE_RISK_NAMES = {"LOW"}


def _load_safety_policy(path: Path = _DEFAULT_POLICY_PATH) -> dict | None:
    """Load external safety policy overrides if the file exists."""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load safety_policy.json: {e}")
    return None


# ---------------------------------------------------------------------------
# ToolRunner
# ---------------------------------------------------------------------------


class ToolRunner:
    """
    Central execution wrapper.

    Usage:
        runner = ToolRunner()
        result = await runner.execute("weather", {"city": "Tokyo"}, user_intent="what's the weather")
    """

    # Retry configuration
    MAX_RETRIES = 2
    RETRY_BACKOFF_MS = 500  # doubles each attempt

    def __init__(
        self,
        log_dir: Path | None = None,
        confirmation_callback: Callable | None = None,
        status_callback: Callable[[str], None] | None = None,
        allow_terminal_confirmation: bool = True,
    ):
        if log_dir is None:
            log_dir = Path(__file__).parent.parent / "data"
        log_dir.mkdir(parents=True, exist_ok=True)

        self._log_path = log_dir / "execution_log.jsonl"
        self._confirmation_cb = confirmation_callback
        self._status_cb = status_callback
        self._allow_terminal_confirmation = allow_terminal_confirmation

        # Import authority gate lazily to avoid circular imports
        self._gate = None

        # Load external policy overrides
        self._policy_overrides = _load_safety_policy()
        self._policy_idempotent_tools = {
            str(tool_name).strip().lower()
            for tool_name in (self._policy_overrides or {}).get("idempotent_tools", [])
            if str(tool_name).strip()
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        user_intent: str = "",
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """
        Execute a tool through the full safety pipeline:
        1. Authority gate check
        2. Dry-run for confirm-level actions
        3. Confirmation transport (callback / terminal / auto-deny)
        4. Execution with idempotency-aware retries
        5. JSONL logging
        """
        start_ns = time.perf_counter_ns()
        context = context or {}

        # Authority gate check
        gate = self._get_gate()
        allowed, reason = gate.check(tool_name, args)
        risk = gate.classify_risk(tool_name, args)
        outcome = gate.get_action_outcome(tool_name, args)
        if outcome not in {"safe", "confirm", "blocked"}:
            if allowed:
                outcome = "safe"
            elif getattr(risk, "name", "") == "CRITICAL":
                outcome = "blocked"
            else:
                outcome = "confirm"
        self._publish_event("tool_started", tool_name=tool_name, args=args)

        if outcome == "blocked":
            result = ToolResult(
                status=ToolStatus.BLOCKED,
                summary=reason,
                tool_name=tool_name,
                args=args,
                duration_ms=self._elapsed_ms(start_ns),
            )
            gate.log_action(tool_name, args, was_approved=False, risk_level=risk)
            self._emit_status(f"🛡️ Blocked: {tool_name}")
            self._publish_event(
                "confirmation",
                tool_name=tool_name,
                action="denied",
                dry_run=result.summary,
            )
            self._write_log(result, user_intent)
            return result

        if outcome == "confirm":
            dry_run = self._generate_dry_run(tool_name, args)
            self._emit_status(f"⚠️ Awaiting confirmation: {tool_name}")
            self._publish_event(
                "confirmation",
                tool_name=tool_name,
                action="requested",
                dry_run=dry_run,
            )

            approved = await self._request_confirmation(tool_name, args, dry_run)
            if not approved:
                result = ToolResult(
                    status=ToolStatus.REQUIRES_CONFIRMATION,
                    summary=f"Action '{tool_name}' was denied. Dry-run: {dry_run}",
                    tool_name=tool_name,
                    args=args,
                    duration_ms=self._elapsed_ms(start_ns),
                )
                gate.log_action(tool_name, args, was_approved=False, risk_level=risk)
                self._publish_event(
                    "confirmation",
                    tool_name=tool_name,
                    action="denied",
                    dry_run=dry_run,
                )
                self._write_log(result, user_intent)
                return result
            else:
                gate.log_action(tool_name, args, was_approved=True, risk_level=risk)
                self._publish_event(
                    "confirmation",
                    tool_name=tool_name,
                    action="approved",
                    dry_run=dry_run,
                )

        # ------ Step 2: Resolve skill instance ------
        from assistant.skills_registry import registry

        instance = None
        is_mcp = tool_name.startswith("mcp__")

        if is_mcp:
            parts = tool_name.split("__", 2)
            if len(parts) == 3:
                args["_mcp_server"] = parts[1]
                args["_mcp_tool"] = parts[2]
                instance = registry.create_instance("mcp")
        elif tool_name in registry.get_skill_names():
            instance = registry.create_instance(tool_name)

        if instance is None:
            result = ToolResult(
                status=ToolStatus.ERROR,
                summary=f"Skill '{tool_name}' not found or not available.",
                error=f"No registered skill named '{tool_name}'",
                tool_name=tool_name,
                args=args,
                duration_ms=self._elapsed_ms(start_ns),
            )
            self._write_log(result, user_intent)
            return result

        # ------ Step 3: Execute with optional retries ------
        can_retry = self._is_safe_to_retry(tool_name, risk)
        last_error: str | None = None

        attempts = (self.MAX_RETRIES + 1) if can_retry else 1
        for attempt in range(attempts):
            try:
                self._emit_status(f"Executing {tool_name}...")
                raw = await instance.handle_tool_call(args, context=context)

                result = ToolResult(
                    status=ToolStatus.OK,
                    summary=self._truncate(str(raw), 200),
                    data=raw,
                    tool_name=tool_name,
                    args=args,
                    duration_ms=self._elapsed_ms(start_ns),
                )
                self._publish_event(
                    "tool_finished",
                    tool_name=tool_name,
                    duration_ms=result.duration_ms,
                    summary=result.summary,
                )
                self._write_log(result, user_intent)
                return result

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    f"Tool {tool_name} attempt {attempt + 1}/{attempts} failed: {last_error}"
                )
                if attempt < attempts - 1:
                    backoff = (self.RETRY_BACKOFF_MS * (2**attempt)) / 1000.0
                    self._emit_status(
                        f"Retrying {tool_name} in {backoff:.1f}s ({attempt + 2}/{attempts})..."
                    )
                    await asyncio.sleep(backoff)

        # All attempts exhausted
        final_status = ToolStatus.RETRYABLE if can_retry else ToolStatus.ERROR
        result = ToolResult(
            status=final_status,
            summary=f"{tool_name} failed after {attempts} attempt(s).",
            error=last_error,
            tool_name=tool_name,
            args=args,
            duration_ms=self._elapsed_ms(start_ns),
        )
        self._publish_event(
            "tool_failed",
            tool_name=tool_name,
            error=last_error or result.summary,
            duration_ms=result.duration_ms,
        )
        self._write_log(result, user_intent)
        self._emit_status(f"❌ {tool_name} failed: {last_error}")
        return result

    # ------------------------------------------------------------------
    # Dry-run generation
    # ------------------------------------------------------------------

    def _generate_dry_run(self, tool_name: str, args: dict[str, Any]) -> str:
        """Create a human-readable preview of what a tool call would do."""
        parts = [f"Action: {tool_name}"]

        # Describe key arguments
        for key, value in (args or {}).items():
            if key.startswith("_"):
                continue
            display = self._truncate(str(value), 80)
            parts.append(f"  {key}: {display}")

        # Add risk-specific warnings
        gate = self._get_gate()
        risk = gate.classify_risk(tool_name, args)
        if risk.name == "CRITICAL":
            parts.append("⛔ This action is IRREVERSIBLE.")
        elif risk.name == "HIGH":
            parts.append(
                "⚠️ This action may modify files, send messages, or run system commands."
            )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Confirmation transport
    # ------------------------------------------------------------------

    async def _request_confirmation(
        self, tool_name: str, args: dict[str, Any], dry_run: str
    ) -> bool:
        """
        Request user confirmation through the best available transport:
        1. GUI callback (PyQt6 dialog)
        2. Terminal input() fallback
        3. Auto-deny after 30s timeout
        """
        prompt = f"🔒 Confirm action?\n\n{dry_run}\n\nProceed? (yes/no)"

        # 1. GUI callback
        if self._confirmation_cb:
            try:
                result = self._confirmation_cb(prompt)
                if asyncio.iscoroutine(result):
                    return await asyncio.wait_for(result, timeout=30.0)
                return bool(result)
            except TimeoutError:
                logger.warning("Confirmation GUI timed out — auto-denying")
                return False
            except Exception as e:
                logger.warning(f"Confirmation callback error: {e}")

        if not self._allow_terminal_confirmation:
            logger.info(
                "No non-blocking confirmation transport is configured — auto-denying"
            )
            return False

        # 2. Terminal fallback
        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(input, prompt + " > "),
                timeout=30.0,
            )
            return answer.strip().lower() in {"yes", "y", "approve"}
        except TimeoutError:
            logger.warning("Confirmation timed out after 30s — auto-denying")
            return False
        except (EOFError, OSError):
            # No terminal attached
            logger.warning("No terminal available for confirmation — auto-denying")
            return False

    # ------------------------------------------------------------------
    # Retry policy
    # ------------------------------------------------------------------

    def _is_safe_to_retry(self, tool_name: str, risk) -> bool:
        """Only retry idempotent / read-only tools. Never blind-retry destructive ops."""
        normalized_tool = (tool_name or "").strip().lower()
        if normalized_tool.startswith("mcp__"):
            parts = normalized_tool.split("__", 2)
            if len(parts) == 3 and parts[2]:
                normalized_tool = parts[2]

        if normalized_tool in _IDEMPOTENT_TOOLS:
            return True
        if normalized_tool in self._policy_idempotent_tools:
            return True
        if risk.name in _SAFE_RISK_NAMES:
            return True
        return False

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _write_log(self, result: ToolResult, user_intent: str):
        """Append a structured log entry to the JSONL file."""
        entry = ExecutionLogEntry(
            timestamp=datetime.now().isoformat(),
            user_intent=user_intent,
            tool_name=result.tool_name,
            args=result.args,
            status=result.status.value,
            duration_ms=result.duration_ms,
            result_summary=result.summary,
            failure_reason=result.error,
        )
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry), default=str) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write execution log: {e}")

        # Emit event for dashboard / event_bus consumers
        try:
            # Use StatusEvent for now; Task 6 will add ToolEvent
            from assistant.events import StatusEvent, bus

            status_text = (
                f"[{result.status.value}] {result.tool_name} ({result.duration_ms}ms)"
            )
            bus.publish(StatusEvent(text=status_text, source="tool_runner"))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_gate(self):
        """Lazy-load AuthorityGate to avoid circular imports."""
        if self._gate is None:
            from assistant.authority_gate import AuthorityGate

            self._gate = AuthorityGate()
        return self._gate

    def _emit_status(self, text: str):
        """Forward status to the registered callback."""
        if self._status_cb:
            try:
                self._status_cb(text)
            except Exception:
                pass

    def set_confirmation_callback(self, callback: Callable | None) -> None:
        """Update confirmation transport callback at runtime."""
        self._confirmation_cb = callback

    def set_allow_terminal_confirmation(self, enabled: bool) -> None:
        """Enable/disable blocking terminal confirmation fallback."""
        self._allow_terminal_confirmation = bool(enabled)

    def _publish_event(self, event_kind: str, **payload: Any) -> None:
        """Publish typed runtime events for dashboards and observers."""
        try:
            from assistant.events import (
                ConfirmationEvent,
                ToolFailedEvent,
                ToolFinishedEvent,
                ToolStartedEvent,
                bus,
            )

            event_map = {
                "tool_started": ToolStartedEvent,
                "tool_finished": ToolFinishedEvent,
                "tool_failed": ToolFailedEvent,
                "confirmation": ConfirmationEvent,
            }
            event_cls = event_map.get(event_kind)
            if event_cls is None:
                return
            bus.publish(event_cls(**payload))
        except Exception:
            pass

    @staticmethod
    def _elapsed_ms(start_ns: int) -> int:
        return int((time.perf_counter_ns() - start_ns) / 1_000_000)

    @staticmethod
    def _truncate(text: str, max_len: int = 200) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    # ------------------------------------------------------------------
    # Log query (for dashboard / debugging)
    # ------------------------------------------------------------------

    def get_recent_logs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Read the last N log entries from the JSONL file."""
        if not self._log_path.exists():
            return []
        try:
            with open(self._log_path, encoding="utf-8") as f:
                lines = f.readlines()
            entries = []
            for line in lines[-limit:]:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
            return entries
        except Exception as e:
            logger.warning(f"Failed to read execution log: {e}")
            return []
