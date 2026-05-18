"""
MCP Skill - Bridge to Model Context Protocol Servers
"""

import asyncio
import contextlib
import logging
import os
import sys
from typing import Any

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from assistant.skills_registry import skill
from config import MCP_SERVERS
from skills.base_skill import BaseSkill

# Import MCP SDK
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    HAS_MCP = True
except ImportError:
    HAS_MCP = False

logger = logging.getLogger(__name__)


@skill(
    name="mcp",
    keywords=["mcp"],
    description="Executes tools from Model Context Protocol (MCP) servers.",
    priority=1,
)
class MCPSkill(BaseSkill):
    """
    Connects to local MCP servers, maintains persistent connections,
    and exposes their tools to the LLM native tool array.
    """

    _server_sessions: dict[str, dict[str, Any]] = {}
    _server_schemas: list[dict[str, Any]] = []
    _lock = asyncio.Lock()

    def __init__(self):
        super().__init__()

    @classmethod
    def _rebuild_schema_cache_locked(cls) -> None:
        schemas: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in cls._server_sessions.values():
            for schema in entry.get("schemas", []):
                tool_name = schema.get("function", {}).get("name", "")
                if tool_name and tool_name not in seen:
                    schemas.append(schema)
                    seen.add(tool_name)
        cls._server_schemas = schemas

    @classmethod
    async def _run_server_lifecycle(cls, server_name: str, config: dict[str, Any]):
        """
        Runs in the background indefinitely, holding the AnyIO AsyncExitStack
        in a single continuous task scope to prevent cancel_scope errors.
        """
        command = config.get("command")
        args = config.get("args", [])
        env = config.get("env", None)

        try:
            async with contextlib.AsyncExitStack() as stack:
                server_params = StdioServerParameters(
                    command=command, args=args, env=env
                )
                read, write = await stack.enter_async_context(
                    stdio_client(server_params)
                )

                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()

                tools_result = await session.list_tools()
                tools = tools_result.tools

                schemas = []
                for tool in tools:
                    prefixed_name = f"mcp__{server_name}__{tool.name}"
                    schemas.append(
                        {
                            "type": "function",
                            "function": {
                                "name": prefixed_name,
                                "description": f"[{server_name}] {tool.description}",
                                "parameters": tool.inputSchema,
                            },
                        }
                    )

                async with cls._lock:
                    entry = cls._server_sessions.setdefault(server_name, {})
                    entry.update(
                        {
                            "session": session,
                            "tools": tools,
                            "schemas": schemas,
                            "state": "healthy",
                            "error": None,
                        }
                    )
                    cls._rebuild_schema_cache_locked()

                logger.info(
                    f"Connected to MCP server '{server_name}' ({len(tools)} tools)"
                )

                try:
                    while True:
                        await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    async with cls._lock:
                        entry = cls._server_sessions.get(server_name)
                        if entry is not None:
                            entry.update(
                                {
                                    "session": None,
                                    "tools": [],
                                    "schemas": [],
                                    "state": "closed",
                                    "error": None,
                                }
                            )
                            cls._rebuild_schema_cache_locked()
                    logger.info(f"MCP server '{server_name}' shutting down...")
                    raise
        except Exception as e:
            async with cls._lock:
                entry = cls._server_sessions.setdefault(server_name, {})
                entry.update(
                    {
                        "session": None,
                        "tools": [],
                        "schemas": [],
                        "state": "failed",
                        "error": str(e),
                    }
                )
                cls._rebuild_schema_cache_locked()
            logger.error(f"Failed to connect to MCP server '{server_name}': {e}")

    @classmethod
    async def _wait_for_server_ready(
        cls, server_name: str, timeout: float = 5.0
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            async with cls._lock:
                state = cls._server_sessions.get(server_name, {}).get("state")
                if state in {"healthy", "failed", "closed"}:
                    return
            await asyncio.sleep(0.05)

    async def _ensure_servers(self):
        """Spawn or refresh background tasks for all configured MCP servers."""
        if not HAS_MCP:
            return

        async with self._lock:
            for server_name, config in MCP_SERVERS.items():
                entry = MCPSkill._server_sessions.get(server_name)
                task = entry.get("task") if entry else None
                state = entry.get("state") if entry else None
                should_start = (
                    entry is None
                    or task is None
                    or task.done()
                    or state in {"failed", "closed"}
                )
                if not should_start:
                    continue

                logger.info(f"Initializing MCP connection for '{server_name}'...")
                task = asyncio.create_task(
                    self._run_server_lifecycle(server_name, config)
                )
                MCPSkill._server_sessions[server_name] = {
                    "task": task,
                    "session": None,
                    "tools": [],
                    "schemas": [],
                    "state": "starting",
                    "error": None,
                }
            MCPSkill._rebuild_schema_cache_locked()

    async def get_mcp_tools(self) -> list[dict[str, Any]]:
        """Return all MCP tools formatted as OpenAI schemas."""
        await self._ensure_servers()
        await asyncio.gather(
            *(self._wait_for_server_ready(server_name) for server_name in MCP_SERVERS),
            return_exceptions=True,
        )
        return list(MCPSkill._server_schemas)

    async def handle_tool_call(
        self, args: dict[str, Any], context: dict[str, Any] = None
    ) -> Any:
        """
        Handle dispatch from the LLM Router.
        args should contain '_mcp_server' and '_mcp_tool' which we parse.
        """
        await self._ensure_servers()

        call_args = dict(args or {})
        server_name = call_args.pop("_mcp_server", None)
        tool_name = call_args.pop("_mcp_tool", None)

        if not server_name or not tool_name:
            return "Error: Unknown MCP server or tool routing."

        if server_name not in MCP_SERVERS:
            return f"Error: MCP server '{server_name}' is not configured."

        await self._wait_for_server_ready(server_name)

        async with MCPSkill._lock:
            entry = MCPSkill._server_sessions.get(server_name)
            if not entry:
                return f"Error: MCP server '{server_name}' is not connected."

            session = entry.get("session")
            state = entry.get("state")
            error = entry.get("error")

        if state != "healthy" or session is None:
            detail = error or state or "unknown state"
            return f"Error: MCP server '{server_name}' is unavailable ({detail})."

        try:
            logger.info(f"Executing MCP tool: {server_name}.{tool_name}({call_args})")
            result = await session.call_tool(tool_name, call_args)

            response_text = ""
            for content in result.content:
                if hasattr(content, "text"):
                    response_text += content.text
                elif isinstance(content, dict) and "text" in content:
                    response_text += content["text"]

            if not response_text:
                response_text = "Tool executed successfully (no text output)."

            return response_text
        except Exception as e:
            logger.error(f"MCP Tool Execution Error [{server_name}.{tool_name}]: {e}")
            return f"Error executing tool: {e}"

    async def handle(self, text: str, context: dict[str, Any] = None) -> str:
        """Fallback natural language handler if user hits the keyword directly."""
        return "I am an MCP bridge. Please use me via native tool calls, not natural language."

    @classmethod
    async def cleanup_all(cls):
        """Gracefully close all persistent MCP server connections to avoid AnyIO shutdown errors."""
        async with cls._lock:
            tasks = []
            for server_name, data in cls._server_sessions.items():
                try:
                    logger.info(f"Closing MCP connection to {server_name}...")
                    task = data.get("task")
                    if task and not task.done():
                        task.cancel()
                        tasks.append(task)
                except Exception as e:
                    logger.error(f"Error closing MCP {server_name}: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        async with cls._lock:
            cls._server_sessions.clear()
            cls._server_schemas.clear()
