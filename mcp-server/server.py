"""
Buddy MCP Server

Exposes Buddy's capabilities as MCP tools for AionUI.
"""

import json
import asyncio
import aiohttp
from typing import Any, Optional

BUDDY_API_URL = "http://localhost:8765"
BUDDY_DASHBOARD_URL = "http://localhost:5050"


async def call_buddy_api(
    endpoint: str,
    method: str = "GET",
    data: dict = None,
    base_url: str = None,
) -> dict:
    """Call Buddy API."""
    url = f"{base_url or BUDDY_API_URL}{endpoint}"
    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url) as resp:
                return await resp.json()
        elif method == "POST":
            async with session.post(url, json=data) as resp:
                return await resp.json()


async def get_status() -> str:
    """Get Buddy status."""
    result = await call_buddy_api("/api/status")
    return json.dumps(result, indent=2)


async def get_state() -> str:
    """Get current Buddy state."""
    result = await call_buddy_api("/api/state")
    return json.dumps(result, indent=2)


async def companion_wake() -> str:
    """Trigger Jarvis click-to-talk through the dashboard companion API."""
    result = await call_buddy_api(
        "/api/companion/wake",
        method="POST",
        base_url=BUDDY_DASHBOARD_URL,
    )
    return json.dumps(result, indent=2)


async def companion_state() -> str:
    """Get Jarvis companion state for AionUi pet synchronization."""
    result = await call_buddy_api(
        "/api/companion/state",
        base_url=BUDDY_DASHBOARD_URL,
    )
    return json.dumps(result, indent=2)


async def speak(text: str) -> str:
    """Make Buddy speak."""
    result = await call_buddy_api("/api/speak", method="POST", data={"text": text})
    return json.dumps(result)


async def chat(message: str) -> str:
    """Chat with Buddy."""
    result = await call_buddy_api("/api/chat", method="POST", data={"message": message})
    return json.dumps(result)


async def query_memory(query: str, limit: int = 5) -> str:
    """Query Buddy's memory."""
    result = await call_buddy_api("/api/memory/query", method="POST", data={"query": query, "limit": limit})
    return json.dumps(result)


async def list_skills() -> str:
    """List available Buddy skills."""
    result = await call_buddy_api("/api/skills")
    return json.dumps(result)


async def run_skill(skill_name: str, params: dict = None) -> str:
    """Run a Buddy skill."""
    result = await call_buddy_api("/api/skills/run", method="POST", data={"skill_name": skill_name, "params": params or {}})
    return json.dumps(result)


async def desktop_execute(action: str, target: str = None) -> str:
    """Execute desktop action."""
    result = await call_buddy_api("/api/desktop/execute", method="POST", data={"action": action, "target": target})
    return json.dumps(result)


async def desktop_screenshot() -> str:
    """Take screenshot."""
    result = await call_buddy_api("/api/desktop/screenshot")
    return json.dumps(result)


async def list_windows() -> str:
    """List open windows."""
    result = await call_buddy_api("/api/desktop/windows")
    return json.dumps(result)


async def start_wake_word(threshold: float = 0.5) -> str:
    """Start wake word detection."""
    result = await call_buddy_api("/api/wake-word/start", method="POST", data={"threshold": threshold})
    return json.dumps(result)


async def stop_wake_word() -> str:
    """Stop wake word detection."""
    result = await call_buddy_api("/api/wake-word/stop", method="POST")
    return json.dumps(result)


TOOLS = [
    {
        "name": "buddy_status",
        "description": "Get Buddy assistant status",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "buddy_state",
        "description": "Get current Buddy state (IDLE, LISTENING, THINKING, SPEAKING, ERROR)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "buddy_companion_wake",
        "description": "Trigger Jarvis click-to-talk using the AionUi desktop pet companion flow",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "buddy_companion_state",
        "description": "Get Jarvis companion state for AionUi desktop pet animation mapping",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "buddy_speak",
        "description": "Make Buddy speak text via TTS",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to speak"}},
            "required": ["text"]
        }
    },
    {
        "name": "buddy_chat",
        "description": "Chat with Buddy's LLM brain",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Message to send"}},
            "required": ["message"]
        }
    },
    {
        "name": "buddy_memory_query",
        "description": "Query Buddy's long-term memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "number", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "buddy_skills",
        "description": "List available Buddy skills",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "buddy_run_skill",
        "description": "Execute a Buddy skill",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string"},
                "params": {"type": "object"}
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "buddy_desktop",
        "description": "Execute desktop automation action",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "target": {"type": "string"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "buddy_screenshot",
        "description": "Take desktop screenshot",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "buddy_windows",
        "description": "List open windows",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "buddy_start_wake_word",
        "description": "Start wake word detection",
        "inputSchema": {
            "type": "object",
            "properties": {"threshold": {"type": "number", "default": 0.5}}
        }
    },
    {
        "name": "buddy_stop_wake_word",
        "description": "Stop wake word detection",
        "inputSchema": {"type": "object", "properties": {}}
    }
]


if __name__ == "__main__":
    import sys
    
    # Simple MCP server using stdin/stdout
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            request = json.loads(line)
            method = request.get("method")
            params = request.get("params", {})
            
            # Map to function
            func_map = {
                "get_status": get_status,
                "get_state": get_state,
                "companion_wake": companion_wake,
                "companion_state": companion_state,
                "speak": lambda: speak(params.get("text", "")),
                "chat": lambda: chat(params.get("message", "")),
                "query_memory": lambda: query_memory(params.get("query", ""), params.get("limit", 5)),
                "list_skills": list_skills,
                "run_skill": lambda: run_skill(params.get("skill_name", ""), params.get("params")),
                "desktop_execute": lambda: desktop_execute(params.get("action", ""), params.get("target")),
                "desktop_screenshot": desktop_screenshot,
                "list_windows": list_windows,
                "start_wake_word": lambda: start_wake_word(params.get("threshold", 0.5)),
                "stop_wake_word": stop_wake_word,
            }
            
            result = asyncio.run(func_map[method]())
            print(json.dumps({"result": result}))
            
        except Exception as e:
            print(json.dumps({"error": str(e)}))
