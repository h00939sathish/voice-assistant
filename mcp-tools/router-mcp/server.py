"""
Tool Router MCP Server — Exposes tool discovery and routing via Model Context Protocol.
Helps the LLM choose the right tool for a given query, reducing hallucinations.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from router_engine import RouterEngine

mcp = FastMCP("ToolRouter")
engine = RouterEngine()
engine.seed_defaults()


@mcp.tool()
def get_tools_for_query(query: str, top_k: int = 12) -> str:
    """Get the most relevant tools for a user query.

    Given a natural language query, returns only the top-N most relevant
    tools ranked by keyword and category relevance. Use this before deciding
    which tool to call — it narrows the field to prevent wrong tool selection.

    Args:
        query: The user's request in natural language
        top_k: Maximum number of tools to return (default 12, max 30)
    """
    top_k = min(max(1, top_k), 30)
    result = engine.get_tools_for_query(query, top_k=top_k)
    return json.dumps(result, indent=2)


@mcp.tool()
def search_tools(query: str, top_k: int = 12) -> str:
    """Alias for get_tools_for_query with MCP-friendly naming."""
    return get_tools_for_query(query=query, top_k=top_k)


@mcp.tool()
def register_tool(
    name: str,
    description: str,
    server: str = "native",
    category: str = "general",
    keywords: str = "[]",
) -> str:
    """Register a new tool in the router catalogue.

    Use this when a new MCP server or skill is added so the router
    can include it in future query routing.

    Args:
        name: Unique tool name (e.g. 'execute_command')
        description: What the tool does
        server: Server name (e.g. 'native', 'mcp__planner', 'mcp__desktop_commander')
        category: One of: planning, filesystem, system, media, web, time, shell, general
        keywords: JSON array of keyword strings, e.g. '["run", "execute", "bash"]'
    """
    try:
        kw_list = json.loads(keywords) if isinstance(keywords, str) else keywords
    except json.JSONDecodeError:
        kw_list = []
    result = engine.register_tool(name, description, server, category, kw_list)
    return json.dumps(result, indent=2)


@mcp.tool()
def list_catalogue(category: str = "") -> str:
    """List all tools registered in the router catalogue.

    Optionally filter by category. Categories: planning, filesystem,
    system, media, web, time, shell, general.

    Args:
        category: Optional category filter. Leave empty to list all tools.
    """
    result = engine.list_catalogue(category if category else None)
    return json.dumps(result, indent=2)


@mcp.tool()
def record_tool_use(tool_name: str) -> str:
    """Tell the router that a tool was successfully used.

    This increases the tool's recency score so it ranks higher in
    future queries during this session.

    Args:
        tool_name: Name of the tool that was used
    """
    result = engine.record_tool_use(tool_name)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()
