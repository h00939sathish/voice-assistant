"""
Apps Script Client — HTTP POST wrapper for the Google Bridge Web App.
Reads APPS_SCRIPT_URL and APPS_SCRIPT_SECRET from environment.
The shared secret is sent in the JSON body, not on the URL.
"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "")
APPS_SCRIPT_SECRET = os.environ.get("APPS_SCRIPT_SECRET", "")
TIMEOUT = 20


def is_configured() -> bool:
    return bool(APPS_SCRIPT_URL and APPS_SCRIPT_SECRET)


def _script_id_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) >= 4 and parts[0] == "macros" and parts[1] == "s":
        return parts[2]
    return ""


def _config_error() -> str:
    if not APPS_SCRIPT_URL or not APPS_SCRIPT_SECRET:
        return (
            "APPS_SCRIPT_URL or APPS_SCRIPT_SECRET not set. Deploy google_bridge.gs "
            "as a Web App and add both values to your .env file."
        )

    script_id = _script_id_from_url(APPS_SCRIPT_URL)
    if script_id and APPS_SCRIPT_SECRET == script_id:
        return (
            "APPS_SCRIPT_SECRET matches the Apps Script deployment ID in APPS_SCRIPT_URL. "
            "Set APPS_SCRIPT_SECRET to the BUDDY_SECRET script property instead."
        )

    return ""


def call_bridge(action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST a command to the Apps Script bridge and return the response."""
    config_error = _config_error()
    if config_error:
        return {
            "ok": False,
            "error": config_error,
        }

    payload = json.dumps(
        {
            "action": action,
            "secret": APPS_SCRIPT_SECRET,
            "params": params or {},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        APPS_SCRIPT_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "BuddyMCP/1.0",
        },
        method="POST",
    )

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            elapsed = int((time.perf_counter() - start) * 1000)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                if "Script function not found: doPost" in raw:
                    data = {
                        "ok": False,
                        "error": (
                            "APPS_SCRIPT_URL points to a stale or wrong web app deployment. "
                            "The live endpoint does not expose doPost."
                        ),
                        "raw_response": raw,
                    }
                elif "Script function not found: doGet" in raw:
                    data = {
                        "ok": False,
                        "error": (
                            "APPS_SCRIPT_URL points to a stale or wrong web app deployment. "
                            "The live endpoint does not expose doGet."
                        ),
                        "raw_response": raw,
                    }
                else:
                    data = {"raw_response": raw}
            data["elapsed_ms"] = elapsed
            return data

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(2048).decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "ok": False,
            "error": f"HTTP {e.code}: {e.reason}",
            "body": body,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
        }

    except urllib.error.URLError as e:
        return {
            "ok": False,
            "error": f"Connection error: {e.reason}",
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
        }
