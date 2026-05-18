"""
HTTP / API MCP Server — General-purpose REST client for the LLM.
Call any external API with full control over method, headers, auth, and body.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_history import ApiHistory
from http_client import http_request as _http_request
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("HttpApi")
history = ApiHistory()

# In-memory named auth headers: {"home_assistant": "Bearer <token>", ...}
_auth_store: dict = {}


def _inject_auth(headers: dict, auth_name: str) -> dict:
    if auth_name and auth_name in _auth_store:
        headers = dict(headers)
        headers["Authorization"] = _auth_store[auth_name]
    return headers


@mcp.tool()
def http_request(
    method: str,
    url: str,
    headers: str = "{}",
    params: str = "{}",
    body: str = "",
    auth_name: str = "",
    timeout: int = 15,
) -> str:
    """Make a full HTTP request with complete control over method, headers, body, and auth.

    Supports GET, POST, PUT, PATCH, DELETE, HEAD. JSON response bodies are
    auto-parsed. Use set_auth_header first to store named tokens for reuse.

    Args:
        method: HTTP method (GET, POST, PUT, PATCH, DELETE, HEAD)
        url: Full URL including scheme (https://...)
        headers: JSON object of additional headers, e.g. '{"X-Custom": "value"}'
        params: JSON object of query parameters, e.g. '{"page": "1", "limit": "10"}'
        body: Request body — JSON object string or plain text
        auth_name: Name of a stored auth header (from set_auth_header), e.g. 'home_assistant'
        timeout: Request timeout in seconds (default 15)
    """
    try:
        hdrs = json.loads(headers) if headers else {}
        prms = json.loads(params) if params else {}
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in headers or params: {e}"})

    # Inject named auth if provided
    hdrs = _inject_auth(hdrs, auth_name)

    # Parse body — try JSON first, fall back to plain text
    body_data = None
    if body:
        try:
            body_data = json.loads(body)
        except json.JSONDecodeError:
            body_data = body

    result = _http_request(
        method, url, headers=hdrs, params=prms, body=body_data, timeout=timeout
    )

    # Log to history
    history.log(
        method,
        url,
        status=result.get("status", 0),
        elapsed_ms=result.get("elapsed_ms", 0),
        ok=result.get("ok", False),
    )

    # Strip verbose headers from response to save tokens
    result.pop("headers", None)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_json(url: str, params: str = "{}", auth_name: str = "") -> str:
    """Convenience tool: GET a URL and parse the JSON response.

    Shorthand for http_request(GET, url) when you just need JSON data.
    Automatically sets Accept: application/json.

    Args:
        url: URL to GET
        params: JSON object of query parameters, e.g. '{"q": "bitcoin"}'
        auth_name: Name of a stored auth header (from set_auth_header)
    """
    try:
        prms = json.loads(params) if params else {}
    except json.JSONDecodeError:
        prms = {}

    hdrs = _inject_auth({"Accept": "application/json"}, auth_name)
    result = _http_request("GET", url, headers=hdrs, params=prms)
    history.log(
        "GET",
        url,
        status=result.get("status", 0),
        elapsed_ms=result.get("elapsed_ms", 0),
        ok=result.get("ok", False),
    )
    result.pop("headers", None)
    return json.dumps(result, indent=2)


@mcp.tool()
def post_json(url: str, body: str = "{}", auth_name: str = "") -> str:
    """Convenience tool: POST a JSON body to a URL and parse the response.

    Automatically sets Content-Type: application/json.

    Args:
        url: URL to POST to
        body: JSON body to send, e.g. '{"event": "task_done", "data": "..."}'
        auth_name: Name of a stored auth header (from set_auth_header)
    """
    try:
        body_data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        body_data = body

    hdrs = _inject_auth({"Content-Type": "application/json"}, auth_name)
    result = _http_request("POST", url, headers=hdrs, body=body_data)
    history.log(
        "POST",
        url,
        status=result.get("status", 0),
        elapsed_ms=result.get("elapsed_ms", 0),
        ok=result.get("ok", False),
    )
    result.pop("headers", None)
    return json.dumps(result, indent=2)


@mcp.tool()
def set_auth_header(name: str, value: str) -> str:
    """Store a named auth header for reuse in subsequent API calls.

    Saves the Authorization header value in memory for this session.
    Reference it by name in http_request, get_json, or post_json via
    the auth_name parameter.

        Examples:
        set_auth_header("home_assistant", "Bearer YOUR_TOKEN_HERE")
        set_auth_header("github", "token YOUR_GITHUB_TOKEN")
        set_auth_header("basic", "Basic YOUR_BASE64_CREDENTIALS")

    Args:
        name: Friendly name for the auth token (e.g. 'home_assistant', 'github')
        value: Full Authorization header value (e.g. 'Bearer <token>')
    """
    _auth_store[name] = value
    return json.dumps(
        {
            "name": name,
            "stored": True,
            "stored_names": list(_auth_store.keys()),
        },
        indent=2,
    )


@mcp.tool()
def get_request_history(limit: int = 10, url_filter: str = "") -> str:
    """View recent API requests made through this MCP.

    Returns a log of recent calls with method, URL, status, and timing.
    Optionally filter by URL substring.

    Args:
        limit: Number of recent requests to return (default 10, max 50)
        url_filter: Optional URL substring to filter by (e.g. 'httpbin' or 'api.github')
    """
    limit = min(max(1, limit), 50)
    entries = history.get_history(limit=limit, url_filter=url_filter or None)
    return json.dumps(
        {
            "total_returned": len(entries),
            "url_filter": url_filter or None,
            "requests": entries,
        },
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
