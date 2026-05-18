"""
Browser / Research MCP Server — Lightweight web research pipeline.
Search, fetch, extract, and track research sessions. No API keys needed.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from research_session import ResearchSessionStore
from researcher import (
    extract_links as _extract_links,
)
from researcher import (
    fetch_page as _fetch_page,
)
from researcher import (
    search_web as _search_web,
)

mcp = FastMCP("BrowserResearch")
store = ResearchSessionStore()


@mcp.tool()
def research_web(query: str, max_results: int = 5) -> str:
    """Search the web and return structured results with titles, URLs, and snippets.

    Uses DuckDuckGo (no API key required). Returns the top results for a query.
    For deeper research, combine with fetch_page to read the full content.

    Args:
        query: Search query (e.g. "Python asyncio best practices")
        max_results: Number of results to return (default 5, max 10)
    """
    max_results = min(max(1, max_results), 10)
    results = _search_web(query, max_results=max_results)
    return json.dumps(
        {
            "query": query,
            "count": len(results),
            "results": results,
        },
        indent=2,
    )


@mcp.tool()
def fetch_page(url: str, max_chars: int = 6000) -> str:
    """Fetch a webpage and extract clean readable text (strips ads, nav, scripts).

    Uses urllib — no browser needed. Returns the main body text suitable for
    reading or summarising. Great for reading documentation, articles, or
    following up on search results.

    Args:
        url: URL to fetch (e.g. "https://docs.python.org/3/library/asyncio.html")
        max_chars: Max characters to return (default 6000)
    """
    max_chars = min(max(500, max_chars), 20000)
    result = _fetch_page(url, max_chars=max_chars)
    return json.dumps(result, indent=2)


@mcp.tool()
def extract_links(url: str, max_links: int = 20) -> str:
    """Extract all hyperlinks from a webpage.

    Useful for discovering related pages, finding documentation sections,
    or mapping a website's structure.

    Args:
        url: URL to extract links from
        max_links: Maximum number of links to return (default 20)
    """
    max_links = min(max(1, max_links), 100)
    result = _extract_links(url, max_links=max_links)
    return json.dumps(result, indent=2)


@mcp.tool()
def start_research_session(topic: str, notes: str = "") -> str:
    """Start a tracked research session for a topic.

    Creates a persistent session that you can add findings to as you
    research. Use get_research_session later to retrieve all findings.

    Args:
        topic: The research topic (e.g. "Home network security audit")
        notes: Optional initial notes or research goal
    """
    session_id = store.start_session(topic, notes)
    return json.dumps(
        {
            "session_id": session_id,
            "topic": topic,
            "notes": notes,
            "started": True,
        },
        indent=2,
    )


@mcp.tool()
def add_research_finding(
    session_id: int, url: str = "", title: str = "", snippet: str = "", note: str = ""
) -> str:
    """Add a finding to a research session.

    Call this each time you find a relevant page or fact. The finding is
    saved persistently and included in the session summary.

    Args:
        session_id: ID returned by start_research_session
        url: URL of the source (optional)
        title: Title or name of the source
        snippet: Relevant excerpt or key fact
        note: Your annotation or interpretation of this finding
    """
    finding_id = store.add_finding(session_id, url, title, snippet, note)
    return json.dumps(
        {
            "finding_id": finding_id,
            "session_id": session_id,
            "saved": True,
        },
        indent=2,
    )


@mcp.tool()
def get_research_session(session_id: int) -> str:
    """Retrieve all findings from a research session with a formatted summary.

    Returns the full session: topic, all findings with URLs, snippets and
    notes, and a formatted markdown summary.

    Args:
        session_id: Session ID to retrieve
    """
    session = store.get_session(session_id)
    if not session:
        return json.dumps({"error": f"Session {session_id} not found"})
    summary = store.summarise_session(session_id)
    return json.dumps(
        {
            "session_id": session_id,
            "topic": session["topic"],
            "finding_count": session["finding_count"],
            "findings": session["findings"],
            "summary": summary,
        },
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
