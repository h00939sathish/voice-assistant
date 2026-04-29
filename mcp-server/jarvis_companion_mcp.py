"""Jarvis companion MCP server for AionUi desktop pet integration."""

import json
import os
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP


JARVIS_DASHBOARD_URL = os.getenv("JARVIS_DASHBOARD_URL", "http://127.0.0.1:5050")

mcp = FastMCP("jarvis-companion")


def _request_json(method: str, endpoint: str) -> dict:
    url = f"{JARVIS_DASHBOARD_URL.rstrip('/')}{endpoint}"
    request = urllib.request.Request(
        url,
        data=b"{}" if method == "POST" else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        body = json.loads(payload) if payload else {}
        body.setdefault("status_code", exc.code)
        return body
    except urllib.error.URLError as exc:
        return {
            "accepted": False,
            "reason": "jarvis_dashboard_unavailable",
            "error": str(exc.reason),
        }


@mcp.tool()
def jarvis_click_to_talk() -> str:
    """Wake Jarvis through the AionUi pet click-to-talk flow."""
    result = _request_json("POST", "/api/companion/wake")
    return json.dumps(result, indent=2)


@mcp.tool()
def jarvis_companion_state() -> str:
    """Read Jarvis state for AionUi desktop pet animation mapping."""
    result = _request_json("GET", "/api/companion/state")
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()
