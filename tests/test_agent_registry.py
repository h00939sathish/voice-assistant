"""
Unit tests for AgentRegistry and specialist role selection.
"""

import pytest
from assistant.agent_registry import AgentRegistry, AgentRole


def test_agent_registry_default_roles():
    """Verify built-in specialist roles are registered."""
    registry = AgentRegistry()
    roles = registry.list_roles()
    role_names = [r["name"] for r in roles]

    assert "researcher" in role_names
    assert "coder" in role_names
    assert "system_admin" in role_names
    assert "executive_assistant" in role_names


def test_intent_matching():
    """Verify intent resolution matches appropriate specialist role."""
    registry = AgentRegistry()

    role = registry.select_role_for_intent("search for latest news about AI")
    assert role is not None
    assert role.name == "researcher"

    role = registry.select_role_for_intent("write a python script to parse logs")
    assert role is not None
    assert role.name == "coder"

    role = registry.select_role_for_intent("check cpu and memory usage")
    assert role is not None
    assert role.name == "system_admin"

    role = registry.select_role_for_intent("set a reminder for tomorrow")
    assert role is not None
    assert role.name == "executive_assistant"
