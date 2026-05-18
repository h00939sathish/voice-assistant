import importlib


def test_agent_core_imports_and_registers_default_tools():
    core_module = importlib.import_module("assistant.core")

    core = core_module.BuddyCore()

    assert "code_exec" in core.list_tools()
