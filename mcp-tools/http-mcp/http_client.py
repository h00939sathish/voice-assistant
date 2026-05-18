"""
HTTP Client — General-purpose REST client using stdlib urllib.
Supports all HTTP methods, custom headers, query params, JSON/text bodies.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = 15
MAX_RESPONSE_BODY = 16384  # 16KB


def http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    body: Any | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Make an HTTP request and return a structured response dict."""
    method = method.upper()

    # Append query params
    if params:
        encoded = urllib.parse.urlencode(params)
        url = f"{url}{'&' if '?' in url else '?'}{encoded}"

    # Prepare body
    body_bytes = None
    req_headers = {
        "User-Agent": "BuddyMCP/1.0 (HTTP-API-MCP)",
        "Accept": "application/json, text/plain, */*",
    }
    if headers:
        req_headers.update(headers)

    if body is not None:
        if isinstance(body, (dict, list)):
            body_bytes = json.dumps(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            body_bytes = body.encode("utf-8")
            req_headers.setdefault("Content-Type", "text/plain")
        else:
            body_bytes = bytes(body)

    req = urllib.request.Request(
        url, data=body_bytes, headers=req_headers, method=method
    )

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            raw = resp.read(MAX_RESPONSE_BODY)
            resp_headers = dict(resp.headers)
            content_type = resp.headers.get("Content-Type", "")
            charset = _extract_charset(content_type) or "utf-8"
            body_text = raw.decode(charset, errors="replace")

            # Auto-parse JSON response
            parsed = None
            if "application/json" in content_type:
                try:
                    parsed = json.loads(body_text)
                except json.JSONDecodeError:
                    pass

            return {
                "status": resp.status,
                "ok": 200 <= resp.status < 300,
                "url": url,
                "method": method,
                "elapsed_ms": elapsed_ms,
                "headers": resp_headers,
                "body": body_text,
                "json": parsed,
                "truncated": len(raw) >= MAX_RESPONSE_BODY,
            }

    except urllib.error.HTTPError as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        body_text = ""
        try:
            body_text = e.read(4096).decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "status": e.code,
            "ok": False,
            "url": url,
            "method": method,
            "elapsed_ms": elapsed_ms,
            "error": f"HTTP {e.code}: {e.reason}",
            "body": body_text,
        }

    except urllib.error.URLError as e:
        return {
            "status": 0,
            "ok": False,
            "url": url,
            "method": method,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "error": f"URL error: {e.reason}",
            "body": "",
        }

    except Exception as e:
        return {
            "status": 0,
            "ok": False,
            "url": url,
            "method": method,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "error": str(e),
            "body": "",
        }


def _extract_charset(content_type: str) -> str | None:
    m = re.search(r"charset=([^\s;]+)", content_type)
    return m.group(1).strip() if m else None
