"""Jarvis companion MCP server for AionUi desktop pet integration."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP


JARVIS_DASHBOARD_URL = os.getenv("JARVIS_DASHBOARD_URL", "http://127.0.0.1:5050")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
JARVIS_MAIN_PATH = Path(os.getenv("JARVIS_MAIN_PATH", PROJECT_ROOT / "main.py"))
AUTOSTART_WAIT_SECONDS = float(os.getenv("JARVIS_AUTOSTART_WAIT_SECONDS", "20"))

mcp = FastMCP("jarvis-companion")


def _autostart_enabled() -> bool:
    value = os.getenv("JARVIS_COMPANION_AUTOSTART", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _start_jarvis_background() -> int:
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "jarvis-companion-autostart.log"
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )

    log_handle = log_path.open("ab")
    try:
        process = subprocess.Popen(
            [sys.executable, str(JARVIS_MAIN_PATH)],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        return process.pid
    finally:
        log_handle.close()


def _wait_for_dashboard() -> bool:
    deadline = time.monotonic() + AUTOSTART_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _dashboard_is_ready():
            return True
        time.sleep(0.5)
    return False


def _dashboard_is_ready() -> bool:
    url = f"{JARVIS_DASHBOARD_URL.rstrip('/')}/api/companion/state"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=2):
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return False


def _request_json(method: str, endpoint: str, autostart: bool = True) -> dict:
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
        if autostart and _autostart_enabled():
            try:
                pid = _start_jarvis_background()
            except Exception as start_error:
                return {
                    "accepted": False,
                    "reason": "jarvis_autostart_failed",
                    "error": str(start_error),
                }

            if _wait_for_dashboard():
                result = _request_json(method, endpoint, autostart=False)
                result.setdefault("autostarted", True)
                result.setdefault("jarvis_pid", pid)
                return result

            return {
                "accepted": False,
                "reason": "jarvis_dashboard_unavailable",
                "error": str(exc.reason),
                "autostarted": True,
                "jarvis_pid": pid,
            }

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
