"""
Unit tests for Core Assistant State Machine and Sub-Agent Routing logic.
"""

import pytest
from assistant.state_machine import AssistantState, is_valid_transition, explain_invalid_transition
from assistant.events import EventBus, StateChangeEvent, StatusEvent


def test_valid_state_transitions():
    """Verify valid transitions across state machine lifecycle."""
    assert is_valid_transition(AssistantState.STARTING, AssistantState.IDLE)
    assert is_valid_transition(AssistantState.IDLE, AssistantState.LISTENING)
    assert is_valid_transition(AssistantState.LISTENING, AssistantState.PROCESSING)
    assert is_valid_transition(AssistantState.PROCESSING, AssistantState.SPEAKING)
    assert is_valid_transition(AssistantState.SPEAKING, AssistantState.IDLE)


def test_invalid_state_transitions():
    """Verify invalid transition prevention and explanation generation."""
    assert not is_valid_transition(AssistantState.STARTING, AssistantState.SPEAKING)
    explanation = explain_invalid_transition(AssistantState.STARTING, AssistantState.SPEAKING)
    assert "Invalid transition" in explanation or "STARTING" in explanation


def test_event_bus_state_dispatch():
    """Test EventBus event subscription and dispatching for StateChangeEvent."""
    bus = EventBus()
    received_events = []

    def state_listener(event: StateChangeEvent):
        received_events.append(event)

    bus.subscribe(StateChangeEvent, state_listener)
    bus.publish(StateChangeEvent(old_state=AssistantState.IDLE.value, new_state=AssistantState.LISTENING.value))

    assert len(received_events) == 1
    assert received_events[0].old_state == AssistantState.IDLE.value
    assert received_events[0].new_state == AssistantState.LISTENING.value
