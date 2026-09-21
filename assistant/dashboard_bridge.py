"""
Dashboard Bridge — subscribes to the EventBus and pushes events to the Flask SSE queue.
Also collects operator-level data (tool events, subsystem health, task state)
for the dashboard API.
"""

import logging
import queue
from datetime import datetime
from typing import Any

from assistant.events import (
    ConfirmationEvent,
    EventBus,
    ResponseEvent,
    StateChangeEvent,
    StatusEvent,
    SubsystemStateEvent,
    TaskLifecycleEvent,
    ToolFailedEvent,
    ToolFinishedEvent,
    ToolStartedEvent,
    TranscriptionEvent,
)

logger = logging.getLogger("buddy.dashboard_bridge")

_MAX_TOOL_HISTORY = 100


class DashboardBridge:
    """
    Sits between the EventBus and the Flask dashboard.
    Puts JSON-serialisable dicts into an unbounded queue that Flask SSE drains.
    Also accumulates operator data for REST queries.
    """

    def __init__(self, event_bus: EventBus):
        self._sse_queue: queue.Queue = queue.Queue(maxsize=500)
        self._current_state: str = "idle"
        self._subsystem_health: dict[str, str] = {}
        self._recent_tool_events: list[dict[str, Any]] = []
        self._active_tasks: dict[str, dict[str, Any]] = {}
        self._subscribe(event_bus)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _subscribe(self, bus: EventBus) -> None:
        bus.subscribe(StateChangeEvent, self._on_state_change)
        bus.subscribe(TranscriptionEvent, self._on_transcription)
        bus.subscribe(ResponseEvent, self._on_response)
        bus.subscribe(StatusEvent, self._on_status)
        bus.subscribe(ToolStartedEvent, self._on_tool_started)
        bus.subscribe(ToolFinishedEvent, self._on_tool_finished)
        bus.subscribe(ToolFailedEvent, self._on_tool_failed)
        bus.subscribe(TaskLifecycleEvent, self._on_task_lifecycle)
        bus.subscribe(SubsystemStateEvent, self._on_subsystem_state)
        bus.subscribe(ConfirmationEvent, self._on_confirmation)

    def _push(self, event_type: str, data: dict) -> None:
        try:
            self._sse_queue.put_nowait({"type": event_type, "data": data})
        except queue.Full:
            pass  # Dashboard is too slow — drop rather than block the voice loop

    def _record_tool_event(self, kind: str, data: dict) -> None:
        data["kind"] = kind
        data["timestamp"] = datetime.now().isoformat()
        self._recent_tool_events.append(data)
        if len(self._recent_tool_events) > _MAX_TOOL_HISTORY:
            self._recent_tool_events = self._recent_tool_events[-_MAX_TOOL_HISTORY:]

    # ------------------------------------------------------------------
    # EventBus handlers
    # ------------------------------------------------------------------

    def _on_state_change(self, event: StateChangeEvent) -> None:
        self._current_state = event.new_state.lower()
        self._push("state", {"state": self._current_state})

    def _on_transcription(self, event: TranscriptionEvent) -> None:
        self._push(
            "message",
            {
                "role": "user",
                "text": event.text,
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
            },
        )

    def _on_response(self, event: ResponseEvent) -> None:
        self._push(
            "message",
            {
                "role": "assistant",
                "text": event.text,
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
            },
        )

    def _on_status(self, event: StatusEvent) -> None:
        self._push("status", {"text": event.text, "source": event.source})

    def _on_tool_started(self, event: ToolStartedEvent) -> None:
        data = {"tool_name": event.tool_name, "args": event.args}
        self._record_tool_event("started", data)
        self._push("tool", {"action": "started", **data})

    def _on_tool_finished(self, event: ToolFinishedEvent) -> None:
        data = {
            "tool_name": event.tool_name,
            "duration_ms": event.duration_ms,
            "summary": event.summary,
        }
        self._record_tool_event("finished", data)
        self._push("tool", {"action": "finished", **data})

    def _on_tool_failed(self, event: ToolFailedEvent) -> None:
        data = {
            "tool_name": event.tool_name,
            "error": event.error,
            "duration_ms": event.duration_ms,
        }
        self._record_tool_event("failed", data)
        self._push("tool", {"action": "failed", **data})

    def _on_task_lifecycle(self, event: TaskLifecycleEvent) -> None:
        self._active_tasks[event.task_id] = {
            "task_id": event.task_id,
            "action": event.action,
            "goal": event.goal,
        }
        self._push(
            "task",
            {"task_id": event.task_id, "action": event.action, "goal": event.goal},
        )

    def _on_subsystem_state(self, event: SubsystemStateEvent) -> None:
        self._subsystem_health[event.subsystem] = event.state
        self._push(
            "subsystem",
            {
                "subsystem": event.subsystem,
                "state": event.state,
                "detail": event.detail,
            },
        )

    def _on_confirmation(self, event: ConfirmationEvent) -> None:
        data = {
            "tool_name": event.tool_name,
            "action": event.action,
            "dry_run": event.dry_run,
            "confirmation_id": event.confirmation_id,
        }
        self._record_tool_event("confirmation", data)
        self._push("confirmation", data)

    # ------------------------------------------------------------------
    # Public API used by Flask
    # ------------------------------------------------------------------

    def current_state(self) -> str:
        return self._current_state

    def subsystem_health(self) -> dict[str, str]:
        return dict(self._subsystem_health)

    def recent_tool_events(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._recent_tool_events[-limit:]

    def active_tasks(self) -> dict[str, dict[str, Any]]:
        return dict(self._active_tasks)

    def operator_summary(self) -> dict[str, Any]:
        """Aggregate operator data for a single API call."""
        return {
            "state": self._current_state,
            "subsystem_health": self.subsystem_health(),
            "recent_tool_events": self.recent_tool_events(10),
            "active_tasks": self.active_tasks(),
            "timestamp": datetime.now().isoformat(),
        }

    def drain(self, timeout: float = 15.0):
        """
        Generator that yields SSE-formatted strings.
        Blocks up to `timeout` seconds waiting for the next event, then yields
        a keepalive comment so the browser connection stays alive.
        """
        import json

        while True:
            try:
                msg = self._sse_queue.get(timeout=timeout)
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"  # SSE comment — keeps connection alive
