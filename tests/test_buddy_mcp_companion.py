import importlib.util
from pathlib import Path

import pytest

SERVER_PATH = Path(__file__).parent.parent / "mcp-server" / "server.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("buddy_mcp_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_companion_wake_calls_dashboard_endpoint(monkeypatch):
    server = load_server_module()
    calls = []

    async def fake_call(endpoint, method="GET", data=None, base_url=None):
        calls.append(
            {
                "endpoint": endpoint,
                "method": method,
                "data": data,
                "base_url": base_url,
            }
        )
        return {"accepted": True, "state": "LISTENING"}

    monkeypatch.setattr(server, "call_buddy_api", fake_call)

    result = await server.companion_wake()

    assert calls == [
        {
            "endpoint": "/api/companion/wake",
            "method": "POST",
            "data": None,
            "base_url": server.BUDDY_DASHBOARD_URL,
        }
    ]
    assert '"accepted": true' in result
    assert '"state": "LISTENING"' in result


@pytest.mark.asyncio
async def test_companion_state_calls_dashboard_endpoint(monkeypatch):
    server = load_server_module()
    calls = []

    async def fake_call(endpoint, method="GET", data=None, base_url=None):
        calls.append(
            {
                "endpoint": endpoint,
                "method": method,
                "data": data,
                "base_url": base_url,
            }
        )
        return {"state": "IDLE", "wake_word_enabled": True, "timestamp": "now"}

    monkeypatch.setattr(server, "call_buddy_api", fake_call)

    result = await server.companion_state()

    assert calls == [
        {
            "endpoint": "/api/companion/state",
            "method": "GET",
            "data": None,
            "base_url": server.BUDDY_DASHBOARD_URL,
        }
    ]
    assert '"state": "IDLE"' in result
    assert '"wake_word_enabled": true' in result


def test_companion_tools_are_advertised():
    server = load_server_module()
    tool_names = {tool["name"] for tool in server.TOOLS}

    assert "buddy_companion_wake" in tool_names
    assert "buddy_companion_state" in tool_names
