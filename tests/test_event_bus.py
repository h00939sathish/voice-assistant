"""
Unit tests for the Event Bus system.
"""

import asyncio

import pytest

from assistant.events import Event, EventBus, StateChangeEvent


@pytest.mark.asyncio
async def test_event_subscription_and_publish():
    """Verify that subscribers receive published events"""
    bus = EventBus()
    received_events = []

    async def mock_handler(event: StateChangeEvent):
        received_events.append(event)

    bus.subscribe(StateChangeEvent, mock_handler)

    test_event = StateChangeEvent(old_state="IDLE", new_state="LISTENING")
    bus.publish(test_event)

    # Wait for async task to process
    await asyncio.sleep(0.1)

    assert len(received_events) == 1
    assert received_events[0] == test_event
    assert received_events[0].new_state == "LISTENING"


@pytest.mark.asyncio
async def test_multiple_event_types():
    """Verify that handlers only receive their subscribed event types"""
    bus = EventBus()
    state_events = []

    async def state_handler(event: StateChangeEvent):
        state_events.append(event)

    bus.subscribe(StateChangeEvent, state_handler)

    # Publish a different event type
    bus.publish(Event())
    await asyncio.sleep(0.1)
    assert len(state_events) == 0

    # Publish correct event type
    bus.publish(StateChangeEvent("A", "B"))
    await asyncio.sleep(0.1)
    assert len(state_events) == 1


@pytest.mark.asyncio
async def test_unsubscribe():
    """Verify that unsubscribed handlers no longer receive events"""
    bus = EventBus()
    count = 0

    async def handler(event):
        nonlocal count
        count += 1

    bus.subscribe(StateChangeEvent, handler)
    bus.publish(StateChangeEvent("A", "B"))
    await asyncio.sleep(0.1)
    assert count == 1

    bus.unsubscribe(StateChangeEvent, handler)
    bus.publish(StateChangeEvent("B", "C"))
    await asyncio.sleep(0.1)
    assert count == 1
