"""
Authority Gate - Risk classification and confirmation for dangerous tool executions.

Classifies tool/skill invocations by risk level and maps them to action outcomes:
    safe     → auto-proceed
    confirm  → dry-run + ask user
    blocked  → refuse (CRITICAL actions)

Uses a single policy registry (data/safety_policy.json) so skills don't invent
their own rules. Falls back to built-in defaults when no policy file exists.

Logs all gated actions to an SQLite audit trail.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from config import AUTHORITY_GATE_ENABLED, AUTHORITY_MIN_LEVEL
except ImportError:
    AUTHORITY_GATE_ENABLED = True
    AUTHORITY_MIN_LEVEL = 3


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class ActionOutcome:
    """Maps a RiskLevel to a user-facing action decision."""

    SAFE = "safe"  # auto-proceed
    CONFIRM = "confirm"  # dry-run + ask user
    BLOCKED = "blocked"  # refuse

    @staticmethod
    def from_risk(risk: RiskLevel, min_level: RiskLevel = RiskLevel.HIGH) -> str:
        if risk == RiskLevel.CRITICAL:
            return ActionOutcome.BLOCKED
        if risk >= min_level:
            return ActionOutcome.CONFIRM
        return ActionOutcome.SAFE


# ---------------------------------------------------------------------------
# Default built-in policy (used when no safety_policy.json exists)
# ---------------------------------------------------------------------------

_BUILTIN_TOOL_RISK_MAP: dict[str, RiskLevel] = {
    # LOW — safe, read-only operations
    "weather": RiskLevel.LOW,
    "mock_weather": RiskLevel.LOW,
    "get_time": RiskLevel.LOW,
    "time": RiskLevel.LOW,
    "search_web": RiskLevel.LOW,
    "search_tools": RiskLevel.LOW,
    "memory_control": RiskLevel.LOW,
    "google_search": RiskLevel.LOW,
    "news": RiskLevel.LOW,
    "web": RiskLevel.LOW,
    "system_monitor": RiskLevel.LOW,
    "registry": RiskLevel.LOW,
    "feedback": RiskLevel.LOW,
    "waifu": RiskLevel.LOW,
    "browser_navigate": RiskLevel.LOW,
    "browser_extract_text": RiskLevel.LOW,
    # MEDIUM — state changes that are reversible
    "computer_use": RiskLevel.MEDIUM,
    "launch_app": RiskLevel.MEDIUM,
    "control_window": RiskLevel.MEDIUM,
    "system_action": RiskLevel.MEDIUM,
    "screen_question": RiskLevel.LOW,
    "spotify_play": RiskLevel.MEDIUM,
    "spotify_pause": RiskLevel.MEDIUM,
    "spotify_next": RiskLevel.MEDIUM,
    "set_volume": RiskLevel.MEDIUM,
    "open_app": RiskLevel.MEDIUM,
    "set_reminder": RiskLevel.MEDIUM,
    "browser": RiskLevel.MEDIUM,
    "browser_click": RiskLevel.MEDIUM,
    "browser_type": RiskLevel.MEDIUM,
    "calendar": RiskLevel.MEDIUM,
    "clipboard": RiskLevel.MEDIUM,
    "file_manager": RiskLevel.MEDIUM,
    "reminder": RiskLevel.MEDIUM,
    # HIGH — system changes or data modifications
    "run_command": RiskLevel.HIGH,
    "execute_command": RiskLevel.HIGH,
    "run_shell": RiskLevel.HIGH,
    "send_email": RiskLevel.HIGH,
    "send_message": RiskLevel.HIGH,
    "create_file": RiskLevel.HIGH,
    "write_file": RiskLevel.HIGH,
    "clipboard_write": RiskLevel.HIGH,
    # CRITICAL — irreversible / destructive
    "delete_file": RiskLevel.CRITICAL,
    "format_drive": RiskLevel.CRITICAL,
    "uninstall": RiskLevel.CRITICAL,
    "shutdown_system": RiskLevel.CRITICAL,
    "restart_system": RiskLevel.CRITICAL,
    "close_window": RiskLevel.HIGH,
}

_LOW_RISK_HINTS = (
    "read",
    "list",
    "show",
    "find",
    "search",
    "check",
    "status",
    "extract",
    "describe",
    "transcribe",
    "agenda",
    "upcoming",
)
_MEDIUM_RISK_HINTS = (
    "open",
    "launch",
    "play",
    "pause",
    "next",
    "previous",
    "set",
    "remind",
    "focus",
    "switch",
    "mute",
    "volume",
    "maximize",
    "minimize",
    "restore",
    "capture screen",
)
_HIGH_RISK_HINTS = (
    "create",
    "write",
    "save",
    "send",
    "message",
    "email",
    "copy",
    "paste",
    "force close",
    "run command",
    "execute command",
    "install",
    "schedule meeting",
    "calendar create",
)
_CRITICAL_RISK_HINTS = (
    "shutdown",
    "restart",
    "reboot",
    "format drive",
    "delete file",
    "remove file",
    "rm -rf",
    "del /f",
    "wipe disk",
)
_CONTEXTUAL_OVERRIDE_TOOLS = {
    "calendar",
    "clipboard",
    "file_manager",
    "reminder",
    "computer_use",
}

# Patterns in arguments that escalate risk to CRITICAL
_DANGEROUS_ARG_PATTERNS = [
    "rm -rf",
    "del /f",
    "format c:",
    "format d:",
    "shutdown",
    "restart",
    "taskkill",
    "drop table",
    "delete from",
    "truncate",
    "rmdir",
    "remove-item -recurse",
]


# ---------------------------------------------------------------------------
# Policy loader
# ---------------------------------------------------------------------------

_POLICY_PATH = Path(__file__).parent.parent / "data" / "safety_policy.json"


def _coerce_risk_level(value: Any) -> RiskLevel:
    """Best-effort parser for AUTHORITY_MIN_LEVEL config values."""
    if isinstance(value, RiskLevel):
        return value

    if isinstance(value, int):
        try:
            return RiskLevel(value)
        except ValueError:
            return RiskLevel.HIGH

    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized.isdigit():
            try:
                return RiskLevel(int(normalized))
            except ValueError:
                return RiskLevel.HIGH
        try:
            return RiskLevel[normalized]
        except KeyError:
            return RiskLevel.HIGH

    return RiskLevel.HIGH


def _load_policy() -> dict[str, RiskLevel]:
    """
    Load the authoritative risk map.
    Priority: safety_policy.json > built-in defaults.
    """
    merged = dict(_BUILTIN_TOOL_RISK_MAP)

    if _POLICY_PATH.exists():
        try:
            with open(_POLICY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            tool_risks = data.get("tool_risks")
            if tool_risks is None:
                tool_risks = data.get("tools", {})
            for tool_name, level_str in tool_risks.items():
                try:
                    merged[tool_name.lower()] = RiskLevel[level_str.upper()]
                except KeyError:
                    logger.warning(
                        f"Unknown risk level '{level_str}' for tool '{tool_name}'"
                    )
            logger.info(
                f"Loaded safety policy from {_POLICY_PATH} ({len(tool_risks)} overrides)"
            )
        except Exception as e:
            logger.warning(f"Failed to load safety_policy.json: {e}")

    return merged


def _iter_text_signals(args: dict | None) -> list[str]:
    """Collect short string signals from tool args for risk inference."""
    if not args:
        return []

    signals: list[str] = []
    for value in args.values():
        if isinstance(value, str):
            signals.append(value.lower())
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str):
                    signals.append(item.lower())
    return signals


def _match_hint_risk(text: str) -> RiskLevel | None:
    """Infer a risk level from normalized tool/action text."""
    if any(hint in text for hint in _CRITICAL_RISK_HINTS):
        return RiskLevel.CRITICAL
    if any(hint in text for hint in _HIGH_RISK_HINTS):
        return RiskLevel.HIGH
    if any(hint in text for hint in _MEDIUM_RISK_HINTS):
        return RiskLevel.MEDIUM
    if any(hint in text for hint in _LOW_RISK_HINTS):
        return RiskLevel.LOW
    return None


# ---------------------------------------------------------------------------
# AuthorityGate
# ---------------------------------------------------------------------------


class AuthorityGate:
    """
    Permission gate that classifies tool calls by risk and blocks dangerous ones.

    Usage:
        gate = AuthorityGate()
        allowed, reason = gate.check("run_command", {"command": "rm -rf /"})
        if not allowed:
            outcome = gate.get_action_outcome("run_command", {"command": "rm -rf /"})
            # outcome == "blocked"
    """

    def __init__(self, audit_db_path: Path | None = None):
        self.enabled = AUTHORITY_GATE_ENABLED
        self.min_level = _coerce_risk_level(AUTHORITY_MIN_LEVEL)

        if audit_db_path is None:
            base_dir = Path(__file__).parent.parent
            audit_db_path = base_dir / "data" / "authority_audit.db"

        self._audit_db_path = audit_db_path
        self._lock = threading.Lock()
        self._pending_approval: dict[str, Any] | None = None

        # Load policy registry (single source of truth)
        self._tool_risk_map = _load_policy()

        if self.enabled:
            self._init_audit_db()
            logger.info(f"   🛡️ Authority Gate active (min_level={self.min_level.name})")

    def _init_audit_db(self):
        """Create audit log table."""
        try:
            self._audit_db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._audit_db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS authority_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tool_name TEXT NOT NULL,
                        args TEXT,
                        risk_level INTEGER NOT NULL,
                        action_outcome TEXT NOT NULL DEFAULT 'safe',
                        was_approved INTEGER NOT NULL,
                        reason TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.warning(f"Authority audit DB init failed: {e}")

    # ------------------------------------------------------------------
    # Risk classification
    # ------------------------------------------------------------------

    def _normalize_tool_name(self, tool_name: str, args: dict | None) -> str:
        """Normalize dynamic tool names into a stable policy lookup key."""
        normalized = (tool_name or "").strip().lower()
        if normalized.startswith("mcp__"):
            parts = normalized.split("__", 2)
            if len(parts) == 3 and parts[2]:
                normalized = parts[2]

        if normalized == "mcp" and args:
            mcp_tool = args.get("_mcp_tool")
            if isinstance(mcp_tool, str) and mcp_tool.strip():
                normalized = mcp_tool.strip().lower()

        if normalized == "browser" and args:
            nested_tool = args.get("tool_name")
            if isinstance(nested_tool, str) and nested_tool.strip():
                normalized = nested_tool.strip().lower()

        return normalized

    def _infer_contextual_risk(
        self, tool_name: str, args: dict | None
    ) -> RiskLevel | None:
        """Infer risk for multiplexed skills where action depends on arguments."""
        signals = " ".join([tool_name, *_iter_text_signals(args)]).strip()
        if not signals:
            return None

        if tool_name == "calendar":
            if "create" in signals:
                return RiskLevel.HIGH
            if "list" in signals or "check_conflicts" in signals:
                return RiskLevel.LOW

        if tool_name == "clipboard":
            if "read" in signals or "what's on" in signals or "what is on" in signals:
                return RiskLevel.LOW
            if "copy" in signals or "paste" in signals or "write" in signals:
                return RiskLevel.HIGH

        if tool_name == "file_manager":
            if "delete file" in signals or "remove file" in signals:
                return RiskLevel.CRITICAL
            if any(
                word in signals
                for word in (
                    "list",
                    "find",
                    "read",
                    "latest download",
                    "show files",
                    "where is",
                )
            ):
                return RiskLevel.LOW
            if any(word in signals for word in ("move", "copy", "write", "create")):
                return RiskLevel.HIGH

        if tool_name == "reminder":
            if any(word in signals for word in ("list", "show reminders")):
                return RiskLevel.LOW
            if any(
                word in signals
                for word in ("set", "create", "cancel", "delete reminder", "cancel all")
            ):
                return RiskLevel.MEDIUM

        if tool_name == "computer_use":
            cmd = (args or {}).get("command", "")
            if cmd == "":
                return _match_hint_risk(signals)
            if cmd in ("screen_question",):
                return RiskLevel.LOW
            if cmd == "system_action":
                action = (args or {}).get("action", "")
                if action in ("shutdown", "restart"):
                    return RiskLevel.CRITICAL
                return RiskLevel.MEDIUM
            if cmd == "control_window":
                action = (args or {}).get("action", "")
                if action == "close":
                    return RiskLevel.HIGH
                return RiskLevel.MEDIUM
            if cmd == "accessibility":
                uia_action = (args or {}).get("uia_action", "")
                if uia_action in ("list", "find", "info", "wait_for"):
                    return RiskLevel.LOW
                return RiskLevel.MEDIUM
            if cmd in ("launch_app", "app_command", "keyboard"):
                return RiskLevel.MEDIUM

        return _match_hint_risk(signals)

    def classify_risk(self, tool_name: str, args: dict = None) -> RiskLevel:
        """Determine the risk level of a tool invocation."""
        normalized_tool = self._normalize_tool_name(tool_name, args)
        risk = self._tool_risk_map.get(normalized_tool)
        if risk is None:
            risk = (
                self._infer_contextual_risk(normalized_tool, args) or RiskLevel.MEDIUM
            )
        else:
            inferred = self._infer_contextual_risk(normalized_tool, args)
            if inferred is not None:
                if normalized_tool in _CONTEXTUAL_OVERRIDE_TOOLS:
                    risk = inferred
                else:
                    risk = max(risk, inferred)

        # Escalate if arguments contain dangerous patterns
        if args:
            args_str = json.dumps(args).lower()
            for pattern in _DANGEROUS_ARG_PATTERNS:
                if pattern in args_str:
                    risk = max(risk, RiskLevel.CRITICAL)
                    break

        return risk

    def get_action_outcome(self, tool_name: str, args: dict = None) -> str:
        """Map a tool call to its action outcome: safe, confirm, or blocked."""
        risk = self.classify_risk(tool_name, args)
        return ActionOutcome.from_risk(risk, self.min_level)

    # ------------------------------------------------------------------
    # Gate check
    # ------------------------------------------------------------------

    def check(self, tool_name: str, args: dict = None) -> tuple[bool, str]:
        """
        Check if a tool call is allowed.

        Returns:
            (allowed, reason) — allowed is True if the action can proceed
            immediately. False means it needs confirmation or is blocked.
        """
        if not self.enabled:
            return True, "Authority gate disabled"

        risk = self.classify_risk(tool_name, args)
        outcome = ActionOutcome.from_risk(risk, self.min_level)

        if outcome == ActionOutcome.SAFE:
            return True, f"Risk level {risk.name} → safe"

        if outcome == ActionOutcome.BLOCKED:
            self._pending_approval = None
            reason = (
                f"⛔ BLOCKED: '{tool_name}' is a {risk.name}-risk action and cannot proceed. "
                f"This action is too dangerous to execute automatically."
            )
            return False, reason

        # outcome == CONFIRM → needs user approval
        self._pending_approval = {
            "tool_name": tool_name,
            "args": args,
            "risk_level": risk,
            "outcome": outcome,
            "timestamp": datetime.now(),
        }
        reason = (
            f"⚠️ {risk.name} risk action: '{tool_name}'. "
            f"Say 'approve' or 'yes' to proceed, or 'deny' to cancel."
        )
        return False, reason

    # ------------------------------------------------------------------
    # Approval flow
    # ------------------------------------------------------------------

    def approve_pending(self) -> dict[str, Any] | None:
        """Approve the pending action and return its details."""
        with self._lock:
            if self._pending_approval:
                action = self._pending_approval.copy()
                self.log_action(
                    action["tool_name"],
                    action["args"],
                    was_approved=True,
                    risk_level=action["risk_level"],
                )
                self._pending_approval = None
                return action
        return None

    def deny_pending(self) -> bool:
        """Deny the pending action."""
        with self._lock:
            if self._pending_approval:
                self.log_action(
                    self._pending_approval["tool_name"],
                    self._pending_approval["args"],
                    was_approved=False,
                    risk_level=self._pending_approval["risk_level"],
                )
                self._pending_approval = None
                return True
        return False

    def has_pending(self) -> bool:
        """Check if there is a pending approval."""
        return self._pending_approval is not None

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def log_action(
        self, tool_name: str, args: dict, was_approved: bool, risk_level: RiskLevel
    ):
        """Log a gated action to the audit trail."""
        outcome = ActionOutcome.from_risk(risk_level, self.min_level)
        try:
            with sqlite3.connect(str(self._audit_db_path)) as conn:
                conn.execute(
                    """INSERT INTO authority_log
                       (tool_name, args, risk_level, action_outcome, was_approved, reason, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        tool_name,
                        json.dumps(args) if args else "{}",
                        int(risk_level),
                        outcome,
                        1 if was_approved else 0,
                        risk_level.name,
                        datetime.now(),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to log authority action: {e}")

    def get_audit_log(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent audit log entries."""
        try:
            with sqlite3.connect(str(self._audit_db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM authority_log ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    def reload_policy(self):
        """Reload the safety policy from disk."""
        self._tool_risk_map = _load_policy()

    def get_policy_summary(self) -> dict[str, list[str]]:
        """Group tools by their action outcome for display."""
        summary: dict[str, list[str]] = {"safe": [], "confirm": [], "blocked": []}
        for tool_name, risk in self._tool_risk_map.items():
            outcome = ActionOutcome.from_risk(risk, self.min_level)
            summary[outcome].append(tool_name)
        return summary
