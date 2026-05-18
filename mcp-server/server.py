"""
Buddy/Jarvis MCP Server

Exposes Buddy's capabilities as MCP tools for AionUI.
Speaks the standard MCP stdio JSON-RPC protocol.
"""

import asyncio
import json
import sys

import aiohttp

BUDDY_API_URL = "http://localhost:8765"
BUDDY_DASHBOARD_URL = "http://localhost:5050"


async def call_buddy_api(
    endpoint: str, method: str = "GET", data: dict = None, base_url: str = None
) -> dict:
    url = f"{base_url or BUDDY_API_URL}{endpoint}"
    try:
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    return await resp.json()
            elif method == "POST":
                async with session.post(
                    url, json=data, timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    return await resp.json()
    except Exception as e:
        return {"error": str(e), "buddy_offline": True}


TOOLS = [
    {
        "name": "buddy_status",
        "description": "Get Buddy/Jarvis assistant status and current state",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_state",
        "description": "Get current Buddy state (IDLE, LISTENING, THINKING, SPEAKING, ERROR)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_wake",
        "description": "Wake Jarvis and trigger click-to-talk / voice listening mode",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_companion_state",
        "description": "Get Jarvis companion state for AionUi desktop pet animation sync",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_speak",
        "description": "Make Jarvis speak text out loud via TTS",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text for Jarvis to speak"}
            },
            "required": ["text"],
        },
    },
    {
        "name": "buddy_chat",
        "description": "Send a message to Jarvis's LLM brain and get a response. Routes through the full skill pipeline (weather, calendar, reminders, browser, system, etc.)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to send to Jarvis",
                },
                "speak": {
                    "type": "boolean",
                    "description": "Whether Jarvis should also speak the response",
                    "default": False,
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "buddy_memory_query",
        "description": "Query Jarvis's long-term memory for past conversations and facts",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memory",
                },
                "limit": {"type": "number", "description": "Max results", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "buddy_clear_memory",
        "description": "Clear Jarvis's conversation memory",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_skills",
        "description": "List all available Jarvis skills (time, weather, calendar, reminder, browser, system, memory, etc.)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_run_skill",
        "description": "Execute a specific Jarvis skill directly",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to run",
                },
                "params": {
                    "type": "object",
                    "description": "Parameters to pass to the skill",
                },
            },
            "required": ["skill_name"],
        },
    },
    {
        "name": "buddy_toggle_mic",
        "description": "Toggle Jarvis microphone on or off",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_desktop_screenshot",
        "description": "Take a screenshot of the desktop via Jarvis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_desktop_windows",
        "description": "List all open windows on the desktop via Jarvis",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_desktop_execute",
        "description": "Execute a desktop automation action via Jarvis desktop agent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to execute (e.g. open_app, click, type)",
                },
                "target": {
                    "type": "string",
                    "description": "Target of the action (e.g. app name, window title)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "buddy_reminders",
        "description": "Get list of pending Jarvis reminders",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_operator_status",
        "description": "Get full Jarvis operator dashboard status — subsystem health, recent actions, tool metrics",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_voice",
        "description": "Send a base64-encoded WAV audio file to Jarvis for full voice processing: STT → skill pipeline → LLM → TTS. Use this when you have audio bytes to process through the complete voice pipeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "audio_base64": {
                    "type": "string",
                    "description": "Base64-encoded WAV audio bytes",
                },
                "speak": {
                    "type": "boolean",
                    "description": "Whether Jarvis should speak the response out loud",
                    "default": True,
                },
            },
            "required": ["audio_base64"],
        },
    },
    {
        "name": "buddy_models",
        "description": "List all available models Jarvis can use (local Ollama models + cloud providers like Gemini, Groq)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "buddy_set_model",
        "description": "Switch Jarvis to a different LLM model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Model name (e.g. phi4-mini, llama3.2, gemini-2.0-flash)",
                },
                "provider": {
                    "type": "string",
                    "description": "Provider name (ollama, gemini, groq, nvidia, openrouter)",
                },
            },
            "required": ["model"],
        },
    },
]


async def handle_tool_call(name: str, arguments: dict) -> str:
    if name == "buddy_status":
        r = await call_buddy_api("/api/status")
        return json.dumps(r, indent=2)

    elif name == "buddy_state":
        r = await call_buddy_api("/api/state")
        return json.dumps(r, indent=2)

    elif name == "buddy_wake":
        r = await call_buddy_api(
            "/api/companion/wake", method="POST", base_url=BUDDY_DASHBOARD_URL
        )
        return json.dumps(r, indent=2)

    elif name == "buddy_companion_state":
        r = await call_buddy_api("/api/companion/state", base_url=BUDDY_DASHBOARD_URL)
        return json.dumps(r, indent=2)

    elif name == "buddy_speak":
        r = await call_buddy_api(
            "/api/speak", method="POST", data={"text": arguments.get("text", "")}
        )
        return json.dumps(r)

    elif name == "buddy_chat":
        r = await call_buddy_api(
            "/api/chat",
            method="POST",
            data={
                "message": arguments.get("message", ""),
                "speak": arguments.get("speak", False),
            },
            base_url=BUDDY_DASHBOARD_URL,
        )
        return json.dumps(r, indent=2)

    elif name == "buddy_memory_query":
        r = await call_buddy_api(
            "/api/memory/query",
            method="POST",
            data={
                "query": arguments.get("query", ""),
                "limit": arguments.get("limit", 5),
            },
        )
        return json.dumps(r, indent=2)

    elif name == "buddy_clear_memory":
        r = await call_buddy_api(
            "/api/clear_memory", method="POST", base_url=BUDDY_DASHBOARD_URL
        )
        return json.dumps(r)

    elif name == "buddy_skills":
        r = await call_buddy_api("/api/skills")
        return json.dumps(r, indent=2)

    elif name == "buddy_run_skill":
        r = await call_buddy_api(
            "/api/skills/run",
            method="POST",
            data={
                "skill_name": arguments.get("skill_name", ""),
                "params": arguments.get("params", {}),
            },
        )
        return json.dumps(r, indent=2)

    elif name == "buddy_toggle_mic":
        r = await call_buddy_api(
            "/api/toggle_mic", method="POST", base_url=BUDDY_DASHBOARD_URL
        )
        return json.dumps(r)

    elif name == "buddy_desktop_screenshot":
        r = await call_buddy_api("/api/desktop/screenshot")
        return json.dumps({"status": "screenshot taken", "path": r.get("path", "")})

    elif name == "buddy_desktop_windows":
        r = await call_buddy_api("/api/desktop/windows")
        return json.dumps(r, indent=2)

    elif name == "buddy_desktop_execute":
        r = await call_buddy_api(
            "/api/desktop/execute",
            method="POST",
            data={
                "action": arguments.get("action", ""),
                "target": arguments.get("target"),
            },
        )
        return json.dumps(r, indent=2)

    elif name == "buddy_reminders":
        r = await call_buddy_api("/api/reminders", base_url=BUDDY_DASHBOARD_URL)
        return json.dumps(r, indent=2)

    elif name == "buddy_operator_status":
        r = await call_buddy_api("/api/operator", base_url=BUDDY_DASHBOARD_URL)
        return json.dumps(r, indent=2)

    elif name == "buddy_voice":
        # Multipart POST with base64 audio → /api/voice
        import aiohttp

        audio_b64 = arguments.get("audio_base64", "")
        speak = arguments.get("speak", True)
        if not audio_b64:
            return json.dumps({"error": "No audio_base64 provided"})
        try:
            import base64

            audio_bytes = base64.b64decode(audio_b64)
            url = f"{BUDDY_API_URL}/api/voice?speak={str(speak).lower()}"
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field(
                    "file", audio_bytes, filename="audio.wav", content_type="audio/wav"
                )
                async with session.post(
                    url, data=form, timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    r = await resp.json()
            return json.dumps(r, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "buddy_models":
        r = await call_buddy_api("/api/models")
        return json.dumps(r, indent=2)

    elif name == "buddy_set_model":
        model = arguments.get("model", "")
        provider = arguments.get("provider", "")
        params = f"model={model}"
        if provider:
            params += f"&provider={provider}"
        r = await call_buddy_api(f"/api/models/set?{params}", method="POST")
        return json.dumps(r, indent=2)

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


def send(obj: dict):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


async def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        if method == "initialize":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "buddy-jarvis-mcp", "version": "1.0.0"},
                    },
                }
            )

        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                result_text = await handle_tool_call(tool_name, arguments)
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": result_text}]},
                    }
                )
            except Exception as e:
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": json.dumps({"error": str(e)})}
                            ],
                            "isError": True,
                        },
                    }
                )

        elif method == "notifications/initialized":
            pass  # no response needed

        else:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


if __name__ == "__main__":
    asyncio.run(main())
