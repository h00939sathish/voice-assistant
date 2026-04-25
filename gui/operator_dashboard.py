"""
Operator Dashboard — Lightweight local interface for Buddy system observability.

Pure consumer of the event bus. Reads from events.jsonl and execution_log.jsonl.
Never accesses module internals directly.

Displays:
- Last 20 actions with tool name, status, duration
- Current task state (if any active)
- Subsystem health states
- Tool failure history
- API latency / call counts
"""

import json
import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class OperatorDashboard:
    """
    Read-only dashboard that consumes event and execution log data.

    Can be used headlessly (get data dicts) or with a PyQt6 GUI.
    The GUI is optional — import errors are handled gracefully.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self._data_dir = data_dir
        self._events_path = data_dir / "events.jsonl"
        self._exec_log_path = data_dir / "execution_log.jsonl"
        self._task_state_path = data_dir / "task_state.json"
        self._audit_db_path = data_dir / "authority_audit.db"

    # ------------------------------------------------------------------
    # Data accessors (pure readers — no module imports)
    # ------------------------------------------------------------------

    def get_recent_actions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Read the last N tool executions from the execution log."""
        return self._read_jsonl(self._exec_log_path, limit)

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Read the last N events from the event stream."""
        return self._read_jsonl(self._events_path, limit)

    def get_task_state(self) -> Optional[Dict[str, Any]]:
        """Read current task executor state."""
        if not self._task_state_path.exists():
            return None
        try:
            with open(self._task_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_subsystem_health(self) -> Dict[str, str]:
        """
        Derive subsystem health from recent events.
        Returns a dict like {"llm": "healthy", "mcp": "degraded", ...}
        """
        default_subsystems = {
            "mic": "unknown", "wake_word": "unknown", "stt": "unknown",
            "tts": "unknown", "llm": "unknown", "mcp": "unknown",
            "memory": "unknown", "scheduler": "unknown",
        }
        events = self.get_recent_events(100)
        for event in reversed(events):
            if event.get("type") == "SubsystemStateEvent":
                sub = event.get("subsystem", "")
                if sub in default_subsystems:
                    default_subsystems[sub] = event.get("state", "unknown")
        return default_subsystems

    def get_tool_failure_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent tool failures from the event stream."""
        events = self.get_recent_events(200)
        failures = [
            e for e in events
            if e.get("type") in ("ToolFailedEvent",)
            or (e.get("type") == "StatusEvent" and "failed" in e.get("text", "").lower())
        ]
        return failures[-limit:]

    def get_api_stats(self) -> Dict[str, Any]:
        """Compute basic API usage stats from the execution log."""
        actions = self._read_jsonl(self._exec_log_path, 500)
        if not actions:
            return {"total_calls": 0, "by_tool": {}, "avg_latency_ms": 0, "failure_rate": 0.0}

    def _safe_parse_datetime(self, ts_str: str) -> Optional[datetime]:
        """Safely parse datetime string."""
        try:
            if not ts_str:
                return None
            # Handle various timestamp formats
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(ts_str[:19], fmt)
                except ValueError:
                    continue
            return datetime.fromisoformat(ts_str)
        except (ValueError, TypeError, OSError):
            return None

    def get_session_summary(self, days: int = 1) -> Dict[str, Any]:
        """Get session usage summary for the last N days."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        
        events = self.get_recent_events(2000)
        recent = [
            e for e in events
            if self._safe_parse_datetime(e.get("timestamp")) and self._safe_parse_datetime(e.get("timestamp")) > cutoff
        ]
        
        # Count by event type
        event_counts: Dict[str, int] = {}
        for e in recent:
            t = e.get("type", "unknown")
            event_counts[t] = event_counts.get(t, 0) + 1
        
        # System state changes
        state_changes = [e for e in recent if e.get("type") == "StateChangeEvent"]
        
        # Skills used
        skills_used = len([e for e in recent if e.get("action") == "skill_used"])
        
        # Errors
        errors = len([e for e in recent if e.get("type") == "ErrorEvent"])
        
        return {
            "period_days": days,
            "event_count": len(recent),
            "event_breakdown": event_counts,
            "state_changes": len(state_changes),
            "skills_used": skills_used,
            "errors": errors,
        }

    def get_skill_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get skill usage statistics for the last N days."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        
        events = self.get_recent_events(1000)
        skill_events = [
            e for e in events
            if e.get("type") == "UsageEvent" 
            and e.get("action") == "skill_used"
            and self._safe_parse_datetime(e.get("timestamp"))
            and self._safe_parse_datetime(e.get("timestamp")) > cutoff
        ]
        
        by_skill: Dict[str, int] = {}
        for e in skill_events:
            skill = e.get("name", "unknown")
            by_skill[skill] = by_skill.get(skill, 0) + 1
        
        return {
            "period_days": days,
            "total_skill_uses": len(skill_events),
            "by_skill": dict(sorted(by_skill.items(), key=lambda x: -x[1])),
            "top_skill": max(by_skill, key=by_skill.get) if by_skill else None,
        }

    def get_llm_latency_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get LLM response latency statistics."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        
        events = self.get_recent_events(500)
        latency_events = [
            e for e in events
            if e.get("type") == "UsageEvent"
            and e.get("action") == "llm_call"
            and self._safe_parse_datetime(e.get("timestamp"))
            and self._safe_parse_datetime(e.get("timestamp")) > cutoff
        ]
        
        if not latency_events:
            return {"period_days": days, "total_calls": 0, "avg_latency_ms": 0}
        
        latencies = [e.get("duration_ms", 0) for e in latency_events if e.get("duration_ms")]
        avg_ms = sum(latencies) / len(latencies) if latencies else 0
        
        return {
            "period_days": days,
            "total_calls": len(latency_events),
            "avg_latency_ms": round(avg_ms, 1),
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
        }

        total = len(actions)
        by_tool: Dict[str, int] = {}
        total_duration = 0
        failures = 0

        for a in actions:
            tool = a.get("tool_name", "unknown")
            by_tool[tool] = by_tool.get(tool, 0) + 1
            total_duration += a.get("duration_ms", 0)
            if a.get("status") in ("error", "retryable"):
                failures += 1

        return {
            "total_calls": total,
            "by_tool": dict(sorted(by_tool.items(), key=lambda x: -x[1])),
            "avg_latency_ms": round(total_duration / total) if total else 0,
            "failure_rate": round(failures / total, 3) if total else 0.0,
            "slowest_tools": self._get_slowest_tools(actions),
        }

    def get_authority_audit(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Read recent authority gate audit entries."""
        if not self._audit_db_path.exists():
            return []
        try:
            import sqlite3
            conn = sqlite3.connect(str(self._audit_db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM authority_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def get_full_status(self) -> Dict[str, Any]:
        """Aggregate all dashboard data into a single status report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "recent_actions": self.get_recent_actions(10),
            "task_state": self.get_task_state(),
            "subsystem_health": self.get_subsystem_health(),
            "tool_failures": self.get_tool_failure_history(5),
            "api_stats": self.get_api_stats(),
            "skill_usage": self.get_skill_usage_stats(7),
            "session_summary": self.get_session_summary(1),
            "llm_latency": self.get_llm_latency_stats(7),
        }

    # ------------------------------------------------------------------
    # CLI display
    # ------------------------------------------------------------------

    def print_status(self):
        """Print a formatted status report to the terminal."""
        status = self.get_full_status()

        print("\n" + "=" * 60)
        print("  🤖 BUDDY OPERATOR DASHBOARD")
        print("=" * 60)

        # Subsystem health
        print("\n📊 Subsystem Health:")
        health = status["subsystem_health"]
        for sub, state in health.items():
            icon = {"healthy": "🟢", "degraded": "🟡", "down": "🔴"}.get(state, "⚪")
            print(f"  {icon} {sub:12s} → {state}")

        # Skill usage
        skill_stats = status.get("skill_usage", {})
        if skill_stats.get("total_skill_uses"):
            print(f"\n🎯 Skills (last {skill_stats.get('period_days', 7)} days):")
            print(f"  Total uses: {skill_stats['total_skill_uses']}")
            by_skill = skill_stats.get("by_skill", {})
            if by_skill:
                print("  By skill:")
                for skill, count in list(by_skill.items())[:5]:
                    print(f"    {skill:20s} → {count}")

        # Session summary
        session = status.get("session_summary", {})
        if session.get("event_count"):
            print(f"\n📈 Session (last 24h):")
            print(f"  Events: {session['event_count']}")
            print(f"  Skills used: {session['skills_used']}")
            print(f"  Errors: {session['errors']}")

        # LLM latency
        llm = status.get("llm_latency", {})
        if llm.get("total_calls"):
            print(f"\n⚡ LLM Latency:")
            print(f"  Calls: {llm['total_calls']}")
            print(f"  Avg: {llm['avg_latency_ms']}ms")
            print(f"  Range: {llm.get('min_latency_ms', 0)}-{llm.get('max_latency_ms', 0)}ms")

        # Recent actions
        print(f"\n🔧 Recent Actions (last {len(status['recent_actions'])}):")
        for action in status["recent_actions"]:
            status_icon = {"ok": "✅", "error": "❌", "retryable": "🔄",
                          "requires_confirmation": "⚠️", "blocked": "🛡️"}.get(
                action.get("status", ""), "❓")
            print(f"  {status_icon} {action.get('tool_name', '?'):20s} "
                  f"{action.get('duration_ms', 0):5d}ms  {action.get('result_summary', '')[:40]}")

        # API stats
        stats = status["api_stats"]
        if stats["total_calls"]:
            print(f"\n📊 API Stats:")
            print(f"  Total calls: {stats['total_calls']}")
            print(f"  Avg latency: {stats['avg_latency_ms']}ms")
            print(f"  Failure rate: {stats['failure_rate']*100:.1f}%")

        # Active tasks
        task_data = status["task_state"]
        if task_data and task_data.get("tasks"):
            print(f"\n📋 Active Tasks:")
            for tid, t in task_data["tasks"].items():
                state_icon = {"running": "🏃", "paused": "⏸️", "completed": "✅",
                             "failed": "❌", "pending": "⏳"}.get(t.get("state", ""), "❓")
                print(f"  {state_icon} [{tid}] {t.get('goal', '')[:40]} ({t.get('state', '')})")

        print("\n" + "=" * 60)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_jsonl(self, path: Path, limit: int) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            entries = []
            for line in lines[-limit:]:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
            return entries
        except Exception:
            return []

    @staticmethod
    def _get_slowest_tools(actions: List[Dict], top_n: int = 5) -> List[Dict[str, Any]]:
        """Find the slowest tool calls."""
        sorted_actions = sorted(actions, key=lambda a: a.get("duration_ms", 0), reverse=True)
        return [
            {"tool_name": a.get("tool_name"), "duration_ms": a.get("duration_ms", 0)}
            for a in sorted_actions[:top_n]
        ]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dashboard = OperatorDashboard()
    dashboard.print_status()
