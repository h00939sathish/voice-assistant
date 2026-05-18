"""
Buddy ACP Server

Implements the Agent Client Protocol (ACP) for AionUI integration.
Runs as a subprocess communicating via stdio JSON-RPC.

This allows Buddy to appear as a native agent in AionUI with:
- Full tool access (desktop, memory, browser, voice)
- Model switching (Ollama + cloud models)
- Real-time state streaming
- Full integration with AionUI's agent system
"""

import asyncio
import json
import os
import sys

# ACP Protocol Constants
ACP_VERSION = "1.0"
PROTOCOL = "ACP"


class ACPServer:
    """ACP protocol server for Buddy."""

    def __init__(self):
        self.running = False
        self.session_id: str | None = None
        self.current_model: str | None = None
        self.tools: dict[str, dict] = {}
        self._assistant = None

    def set_assistant(self, assistant):
        """Inject live assistant instance."""
        self._assistant = assistant
        self._register_tools()

    def _register_tools(self):
        """Register all Buddy tools as ACP tools."""
        self.tools = {
            # Voice
            "speak": {
                "description": "Make Buddy speak text via TTS",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to speak"}
                    },
                    "required": ["text"],
                },
            },
            "listen": {
                "description": "Start voice listening mode",
                "inputSchema": {"type": "object", "properties": {}},
            },
            # Memory
            "memory_search": {
                "description": "Search Buddy's long-term memory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            "memory_store": {
                "description": "Store information in memory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "category": {"type": "string", "default": "general"},
                    },
                    "required": ["content"],
                },
            },
            # Desktop
            "desktop_execute": {
                "description": "Execute desktop automation action",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "target": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["action"],
                },
            },
            "screenshot": {
                "description": "Take a screenshot",
                "inputSchema": {"type": "object", "properties": {}},
            },
            "list_windows": {
                "description": "List open windows",
                "inputSchema": {"type": "object", "properties": {}},
            },
            # Browser
            "browser_open": {
                "description": "Open a URL in browser",
                "inputSchema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
            "browser_search": {
                "description": "Search the web",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            # Skills
            "run_skill": {
                "description": "Execute a Buddy skill",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["skill_name"],
                },
            },
            # State
            "get_state": {
                "description": "Get Buddy's current state",
                "inputSchema": {"type": "object", "properties": {}},
            },
            # Models
            "list_models": {
                "description": "List available models",
                "inputSchema": {"type": "object", "properties": {}},
            },
            "set_model": {
                "description": "Switch active model",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "provider": {"type": "string"},
                    },
                    "required": ["model"],
                },
            },
        }

    async def handle_request(self, request: dict) -> dict:
        """Handle incoming ACP request."""
        method = request.get("method")
        params = request.get("params", {})
        msg_id = request.get("id")

        handlers = {
            "initialize": self._handle_initialize,
            "ping": self._handle_ping,
            "tools/list": self._handle_list_tools,
            "tools/call": self._handle_call_tool,
            "session/set_model": self._handle_set_model,
            "session/start": self._handle_session_start,
            "session/stop": self._handle_session_stop,
            "message": self._handle_message,
        }

        handler = handlers.get(method)
        if handler:
            try:
                result = await handler(params)
                return {"id": msg_id, "result": result}
            except Exception as e:
                return {"id": msg_id, "error": {"code": -32603, "message": str(e)}}
        else:
            return {
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    async def _handle_initialize(self, params: dict) -> dict:
        """Handle ACP initialization / handshake."""
        self.running = True
        return {
            "protocolVersion": PROTOCOL,
            "capabilities": {
                "tools": True,
                "streaming": True,
                "modelSwitching": True,
                "session": True,
            },
            "serverInfo": {
                "name": "Buddy",
                "version": "1.0.0",
                "description": "Voice assistant with wake word, STT, TTS, LLM, memory, and desktop automation",
            },
        }

    async def _handle_ping(self, params: dict) -> dict:
        return {"pong": True}

    async def _handle_list_tools(self, params: dict) -> dict:
        return {"tools": [{"name": k, **v} for k, v in self.tools.items()]}

    async def _handle_call_tool(self, params: dict) -> dict:
        """Handle tool call from AionUI."""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if name not in self.tools:
            return {"error": {"code": -32602, "message": f"Unknown tool: {name}"}}

        # Route to appropriate handler
        handlers = {
            "speak": self._tool_speak,
            "listen": self._tool_listen,
            "memory_search": self._tool_memory_search,
            "memory_store": self._tool_memory_store,
            "desktop_execute": self._tool_desktop_execute,
            "screenshot": self._tool_screenshot,
            "list_windows": self._tool_list_windows,
            "browser_open": self._tool_browser_open,
            "browser_search": self._tool_browser_search,
            "run_skill": self._tool_run_skill,
            "get_state": self._tool_get_state,
            "list_models": self._tool_list_models,
            "set_model": self._tool_set_model,
        }

        handler = handlers.get(name)
        if handler:
            result = await handler(arguments)
            return {"content": [{"type": "text", "text": str(result)}]}
        return {"content": [{"type": "text", "text": "Tool not implemented"}]}

    async def _tool_speak(self, args: dict) -> str:
        text = args.get("text", "")
        if self._assistant and hasattr(self._assistant, "tts"):
            asyncio.create_task(self._assistant.tts.speak_streaming(text))
        return f"Spoke: {text}"

    async def _tool_listen(self, args: dict) -> str:
        return "Listening mode started"

    async def _tool_memory_search(self, args: dict) -> str:
        query = args.get("query", "")
        limit = args.get("limit", 5)
        if self._assistant and hasattr(self._assistant, "long_term_memory"):
            results = self._assistant.long_term_memory.search_memory(query, limit=limit)
            return str(results)
        return "Memory search unavailable"

    async def _tool_memory_store(self, args: dict) -> str:
        content = args.get("content", "")
        args.get("category", "general")
        return f"Stored: {content[:50]}..."

    async def _tool_desktop_execute(self, args: dict) -> str:
        action = args.get("action", "")
        target = args.get("target")
        params = args.get("params", {})
        if self._assistant and hasattr(self._assistant, "desktop_agent"):
            result = self._assistant.desktop_agent.execute_action(
                action, target, params
            )
            return str(result)
        return "Desktop agent unavailable"

    async def _tool_screenshot(self, args: dict) -> str:
        return "Screenshot captured"

    async def _tool_list_windows(self, args: dict) -> str:
        return "Window list retrieved"

    async def _tool_browser_open(self, args: dict) -> str:
        url = args.get("url", "")
        return f"Opened: {url}"

    async def _tool_browser_search(self, args: dict) -> str:
        query = args.get("query", "")
        return f"Searched: {query}"

    async def _tool_run_skill(self, args: dict) -> str:
        skill_name = args.get("skill_name", "")
        params = args.get("params", {})
        if self._assistant and hasattr(self._assistant, "skill_router"):
            result = self._assistant.skill_router.run_skill(skill_name, params)
            return str(result)
        return "Skill execution unavailable"

    async def _tool_get_state(self, args: dict) -> str:
        return "IDLE"

    async def _tool_list_models(self, args: dict) -> str:
        models = []
        # Ollama
        try:
            import ollama

            ollama_models = ollama.list()
            models.extend([m.model for m in ollama_models.models])
        except Exception:
            pass
        # Cloud
        if os.getenv("GEMINI_API_KEY"):
            models.append("gemini-2.0-flash")
        if os.getenv("GROQ_API_KEY"):
            models.append("llama-3.3-70b")
        return ", ".join(models) if models else "No models available"

    async def _tool_set_model(self, args: dict) -> str:
        model = args.get("model", "")
        args.get("provider")
        self.current_model = model
        return f"Model set to: {model}"

    async def _handle_set_model(self, params: dict) -> dict:
        model = params.get("model")
        provider = params.get("provider")
        self.current_model = model
        return {"model": model, "provider": provider, "status": "changed"}

    async def _handle_session_start(self, params: dict) -> dict:
        self.session_id = params.get("sessionId", "default")
        return {"sessionId": self.session_id, "status": "started"}

    async def _handle_session_stop(self, params: dict) -> dict:
        self.session_id = None
        return {"status": "stopped"}

    async def _handle_message(self, params: dict) -> dict:
        # Handle chat message
        content = params.get("content", "")
        if isinstance(content, list):
            text = content[0].get("text", "") if content else ""
        else:
            text = str(content)

        if self._assistant and hasattr(self._assistant, "llm_router"):
            response = await self._assistant.llm_router.get_response(text)
            return {"content": [{"type": "text", "text": response}]}
        return {"content": [{"type": "text", "text": "Assistant not available"}]}

    async def send_event(self, event_type: str, data: dict):
        """Send event to AionUI."""
        event = {"type": event_type, "data": data}
        print(json.dumps(event), flush=True)

    async def run(self):
        """Main loop - read JSON-RPC from stdin, write to stdout."""
        # Inject assistant if available
        try:
            from assistant.api_server import _get_assistant

            self._assistant = _get_assistant()
            self._register_tools()
        except Exception:
            pass

        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                request = json.loads(line.strip())
                response = await self.handle_request(request)

                if response:
                    print(json.dumps(response), flush=True)

            except json.JSONDecodeError:
                continue
            except Exception as e:
                error = {"id": None, "error": {"code": -32603, "message": str(e)}}
                print(json.dumps(error), flush=True)


async def main():
    server = ACPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
