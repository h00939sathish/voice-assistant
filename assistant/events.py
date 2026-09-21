"""
Events - Event-driven communication for Buddy Voice Assistant.
Implements the Observer pattern for decoupled component interaction.
"""

import asyncio
import inspect
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base class for all system events"""

    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "system"


@dataclass
class StateChangeEvent(Event):
    """Fired when the assistant changes its operational state"""

    old_state: str = "UNKNOWN"
    new_state: str = "IDLE"


@dataclass
class SpeechDetectedEvent(Event):
    """Fired when speech is detected (start of listening)"""

    confidence: float = 0.0


@dataclass
class TranscriptionEvent(Event):
    """Fired when speech is transcribed to text"""

    text: str = ""
    confidence: float = 0.0


@dataclass
class ResponseEvent(Event):
    """Fired when the assistant generates a response"""

    text: str = ""
    is_skill: bool = False


@dataclass
class StatusEvent(Event):
    """Fired to display intermediate system activity out to the UI"""

    text: str = ""


@dataclass
class ErrorEvent(Event):
    """Fired when an error occurs"""

    error: Exception | None = None
    component: str = "unknown"


@dataclass
class UsageEvent(Event):
    """Fired to track usage analytics"""

    action: str = ""  # "skill_used", "tool_used", "llm_call", "wake_word", "error"
    name: str = ""  # skill name, tool name, LLM provider
    duration_ms: int = 0
    success: bool = True
    details: str = ""  # additional context


# ==================== Tool / Task / Subsystem Events ====================


@dataclass
class ToolStartedEvent(Event):
    """Fired when a tool begins execution."""

    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolFinishedEvent(Event):
    """Fired when a tool completes successfully."""

    tool_name: str = ""
    duration_ms: int = 0
    summary: str = ""


@dataclass
class ToolFailedEvent(Event):
    """Fired when a tool fails after all retries."""

    tool_name: str = ""
    error: str = ""
    duration_ms: int = 0


@dataclass
class TaskLifecycleEvent(Event):
    """Fired on task state transitions (started, paused, resumed, completed, failed)."""

    task_id: str = ""
    action: str = ""  # started | paused | resumed | completed | failed
    goal: str = ""


@dataclass
class SubsystemStateEvent(Event):
    """Fired when a subsystem's health state changes."""

    subsystem: str = ""  # mic, wake_word, stt, tts, llm, mcp, memory, scheduler
    state: str = "unknown"  # healthy, degraded, down, initializing
    detail: str = ""


@dataclass
class ConfirmationEvent(Event):
    """Fired when an action awaits or receives user confirmation."""

    tool_name: str = ""
    action: str = ""  # requested | approved | denied | timed_out
    dry_run: str = ""
    confirmation_id: str = ""


# ==================== Event Bus with JSONL Persistence ====================

import json as _json
from pathlib import Path as _Path

_EVENTS_LOG_PATH = _Path(__file__).parent.parent / "data" / "events.jsonl"


_MAX_EVENTS_LOG_BYTES = 10 * 1024 * 1024  # 10 MB


class EventBus:
    """
    Centralized asynchronous event bus.
    Allows components to subscribe to and publish events without direct dependencies.
    Persists all events to data/events.jsonl for dashboard consumption.
    """

    def __init__(self, persist: bool = True):
        self._subscribers: dict[type[Event], set[Callable]] = {}
        self._persist = persist
        self._lock = threading.Lock()
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = None

    def subscribe(self, event_type: type[Event], handler: Callable):
        """Subscribe a handler to an event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = set()
            self._subscribers[event_type].add(handler)

    def unsubscribe(self, event_type: type[Event], handler: Callable):
        """Unsubscribe a handler from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type].discard(handler)

    def publish(self, event: Event):
        """
        Publish an event to all subscribers and persist to JSONL.
        """
        event_type = type(event)

        if self._persist:
            self._persist_event(event)

        with self._lock:
            handlers = list(self._subscribers.get(event_type, set()))

        if not handlers:
            return

        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                try:
                    asyncio.create_task(self._safe_execute_async(handler, event))
                except RuntimeError:
                    logger.warning(
                        f"Dropped async handler {handler} — no running event loop"
                    )
            else:
                if self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(
                        self._safe_execute_sync, handler, event
                    )
                else:
                    self._safe_execute_sync(handler, event)

    def _persist_event(self, event: Event):
        """Append event as a JSON line to the events log. Rotates at 10 MB."""
        try:
            _EVENTS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

            # Rotate if oversized
            if (
                _EVENTS_LOG_PATH.exists()
                and _EVENTS_LOG_PATH.stat().st_size > _MAX_EVENTS_LOG_BYTES
            ):
                self._rotate_events_log()

            record = {
                "type": type(event).__name__,
                "timestamp": event.timestamp.isoformat()
                if isinstance(event.timestamp, datetime)
                else str(event.timestamp),
                "source": event.source,
            }
            for key, value in vars(event).items():
                if key not in ("timestamp", "source"):
                    if isinstance(value, (str, int, float, bool, type(None))):
                        record[key] = value
                    elif isinstance(value, dict):
                        record[key] = value
                    else:
                        record[key] = str(value)

            with open(_EVENTS_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(_json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.debug(f"Failed to persist event: {e}")

    def _rotate_events_log(self):
        """Rotate events.jsonl, keeping up to 3 historical files."""
        try:
            _EVENTS_LOG_PATH.rename(_EVENTS_LOG_PATH.with_suffix(".jsonl.1"))
            for i in range(2, 0, -1):
                older = _EVENTS_LOG_PATH.with_suffix(f".jsonl.{i}")
                newer = _EVENTS_LOG_PATH.with_suffix(f".jsonl.{i + 1}")
                if older.exists():
                    older.rename(newer)
        except Exception as e:
            logger.debug(f"Events log rotation failed: {e}")

    async def _safe_execute_async(self, handler: Callable, event: Event):
        """Execute async handler with error protection."""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Error in async event handler {handler}: {e}")

    def _safe_execute_sync(self, handler: Callable, event: Event):
        """Execute sync handler with error protection."""
        try:
            handler(event)
        except Exception as e:
            logger.error(f"Error in sync event handler {handler}: {e}")

    @staticmethod
    def read_recent_events(limit: int = 50) -> list[dict[str, Any]]:
        """Read the last N events from the JSONL log."""
        if not _EVENTS_LOG_PATH.exists():
            return []
        try:
            with open(_EVENTS_LOG_PATH, encoding="utf-8") as f:
                lines = f.readlines()
            events = []
            for line in lines[-limit:]:
                line = line.strip()
                if line:
                    events.append(_json.loads(line))
            return events
        except Exception:
            return []


# Global EventBus instance
bus = EventBus()
