import asyncio
import importlib.util
from pathlib import Path

import pytest


def load_api_server():
    path = Path(__file__).resolve().parents[1] / "assistant" / "api_server.py"
    spec = importlib.util.spec_from_file_location("api_server_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_buddy_routes_are_registered():
    api_server = load_api_server()

    paths = {
        getattr(route, "path", "")
        for route in api_server.app.routes
        if getattr(route, "path", "").startswith("/buddy")
    }

    assert {
        "/buddy/status",
        "/buddy/state",
        "/buddy/chat",
        "/buddy/chat/stream",
        "/buddy/tool",
        "/buddy/tools",
        "/buddy/voice",
        "/buddy/voice-command",
        "/buddy/events",
        "/buddy/wake-word/start",
        "/buddy/wake-word/stop",
    }.issubset(paths)


def test_status_reports_starting_before_assistant_injection():
    api_server = load_api_server()

    status = asyncio.run(api_server.status())

    assert status["status"] == "starting"
    assert status["assistant"] == "disconnected"


@pytest.mark.asyncio
async def test_chat_pipeline_uses_assistant_text_pipeline():
    api_server = load_api_server()

    class Assistant:
        async def process_text_chat(self, message, speak=False, source="api"):
            return f"{source}:{speak}:{message}"

    response = await api_server._run_chat_pipeline(
        Assistant(), "hello", speak=True, source="test"
    )

    assert response == "test:True:hello"


def test_tool_request_normalizes_aliases():
    api_server = load_api_server()

    req = api_server.BuddyToolRequest(tool="weather", command="weather in Pune")
    tool_name, args = api_server._normalize_tool_request(req)

    assert tool_name == "weather"
    assert args["command"] == "weather in Pune"
