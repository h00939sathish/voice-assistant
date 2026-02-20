"""
Events - Event-driven communication for Buddy Voice Assistant.
Implements the Observer pattern for decoupled component interaction.
"""
import logging
import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Type, Any, Callable, Optional, Union, Set
from enum import Enum, auto

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
class ErrorEvent(Event):
    """Fired when an error occurs"""
    error: Optional[Exception] = None
    component: str = "unknown"


class EventBus:
    """
    Centralized asynchronous event bus.
    Allows components to subscribe to and publish events without direct dependencies.
    """

    def __init__(self):
        self._subscribers: Dict[Type[Event], Set[Callable]] = {}
        self._loop = asyncio.get_event_loop()

    def subscribe(self, event_type: Type[Event], handler: Callable):
        """Subscribe a handler to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = set()
        self._subscribers[event_type].add(handler)
        logger.debug(f"Subscribed {handler.__name__ if hasattr(handler, '__name__') else 'lambda'} to {event_type.__name__}")

    def unsubscribe(self, event_type: Type[Event], handler: Callable):
        """Unsubscribe a handler from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type].discard(handler)

    def publish(self, event: Event):
        """
        Publish an event to all subscribers.
        Executes handlers asynchronously.
        """
        event_type = type(event)
        handlers = self._subscribers.get(event_type, set())
        
        if not handlers:
            return

        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                asyncio.create_task(self._safe_execute_async(handler, event))
            else:
                self._loop.call_soon_threadsafe(self._safe_execute_sync, handler, event)

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


# Global EventBus instance
bus = EventBus()
