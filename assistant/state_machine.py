from enum import Enum, auto


class AssistantState(Enum):
    """Voice assistant states"""

    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()
    STARTING = auto()
    ERROR = auto()
    SHUTTING_DOWN = auto()


_ALL_TRANSITIONS: dict[AssistantState, set[AssistantState]] = {
    AssistantState.STARTING: {
        AssistantState.IDLE,
        AssistantState.SHUTTING_DOWN,
    },
    AssistantState.IDLE: {
        AssistantState.LISTENING,
        AssistantState.PROCESSING,
        AssistantState.SPEAKING,
        AssistantState.SHUTTING_DOWN,
    },
    AssistantState.LISTENING: {
        AssistantState.PROCESSING,
        AssistantState.IDLE,
        AssistantState.SHUTTING_DOWN,
    },
    AssistantState.PROCESSING: {
        AssistantState.SPEAKING,
        AssistantState.LISTENING,
        AssistantState.IDLE,
        AssistantState.ERROR,
        AssistantState.SHUTTING_DOWN,
    },
    AssistantState.SPEAKING: {
        AssistantState.IDLE,
        AssistantState.LISTENING,
        AssistantState.SHUTTING_DOWN,
    },
    AssistantState.ERROR: {
        AssistantState.IDLE,
        AssistantState.SHUTTING_DOWN,
    },
    AssistantState.SHUTTING_DOWN: set(),
}


def is_valid_transition(old: AssistantState, new: AssistantState) -> bool:
    """Return True if the state transition is allowed."""
    allowed = _ALL_TRANSITIONS.get(old, set())
    return new in allowed


def explain_invalid_transition(old: AssistantState, new: AssistantState) -> str | None:
    """Return a human-readable reason if the transition is invalid, else None."""
    if is_valid_transition(old, new):
        return None
    allowed = _ALL_TRANSITIONS.get(old, set())
    allowed_names = ", ".join(s.name for s in sorted(allowed, key=lambda s: s.name))
    return f"Illegal transition: {old.name} -> {new.name}. Allowed from {old.name}: [{allowed_names}]"
