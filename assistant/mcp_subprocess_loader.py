"""
MCP Subprocess Loader — manages the lifecycle of out-of-process skill subprocesses.

Usage (internal, via skill_router.py):
    loader = MCPSubprocessLoader(script_path="skills/google_search_skill.py", name="google_search")
    proxy  = MCPSubprocessProxy(loader)

    result = await proxy.handle("search for cats", {})  # same interface as any in-process skill
    proxy.shutdown()                                      # called on LRU eviction
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger("buddy.mcp_loader")

# Per-call timeout — if the subprocess doesn't respond, we raise rather than hang
CALL_TIMEOUT = 10.0


class MCPSubprocessLoader:
    """
    Spawns a skill script as a subprocess and communicates via JSON-lines over stdio.
    Thread-safe: uses asyncio locks for concurrent-safe request serialisation.
    """

    def __init__(self, script_path: str, name: str):
        self.script_path = script_path
        self.name = name
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._req_id = 0
        self._started = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def call(self, text: str, context: dict[str, Any]) -> str:
        """Send a request to the skill subprocess and return the response."""
        async with self._lock:
            await self._ensure_process()

            self._req_id += 1
            req_id = self._req_id
            payload = (
                json.dumps({"id": req_id, "text": text, "context": context}) + "\n"
            )

            try:
                self._process.stdin.write(payload.encode())
                await self._process.stdin.drain()

                response_line = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=CALL_TIMEOUT
                )
            except TimeoutError:
                logger.warning(f"[{self.name}] subprocess timed out — restarting")
                await self._restart()
                return f"Sorry, the {self.name} skill timed out."
            except Exception as e:
                logger.error(f"[{self.name}] subprocess communication error: {e}")
                await self._restart()
                return f"Sorry, the {self.name} skill encountered an error."

            if not response_line:
                logger.warning(
                    f"[{self.name}] empty response — subprocess may have crashed"
                )
                await self._restart()
                return f"Sorry, the {self.name} skill crashed. Please try again."

            try:
                response = json.loads(response_line.decode())
                if "error" in response:
                    logger.warning(f"[{self.name}] skill error: {response['error']}")
                    return f"Skill error: {response['error']}"
                return response.get("result", "")
            except json.JSONDecodeError:
                return f"Malformed response from {self.name} skill."

    def shutdown(self) -> None:
        """Terminate the subprocess. Called on LRU eviction or assistant shutdown."""
        if self._process and self._process.returncode is None:
            try:
                self._process.stdin.close()
                self._process.terminate()
                logger.info(f"[{self.name}] subprocess terminated (LRU eviction)")
            except Exception as e:
                logger.debug(f"[{self.name}] shutdown error (ignored): {e}")
        self._process = None
        self._started = False

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _ensure_process(self) -> None:
        """Spawn subprocess if not running."""
        if self._process and self._process.returncode is None:
            return  # already alive

        await self._spawn()

    async def _spawn(self) -> None:
        """Start the skill subprocess."""
        python = sys.executable
        env = os.environ.copy()

        logger.info(f"[{self.name}] spawning subprocess: {self.script_path}")
        self._process = await asyncio.create_subprocess_exec(
            python,
            self.script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._started = True
        logger.info(f"[{self.name}] subprocess started (PID {self._process.pid})")

    async def _restart(self) -> None:
        """Kill and respawn the subprocess after a failure."""
        self.shutdown()
        await self._spawn()


class MCPSubprocessProxy:
    """
    Thin wrapper that makes an MCPSubprocessLoader look identical to an in-process
    skill from skill_router's perspective: exposes .handle(text, context) and .shutdown().
    """

    def __init__(self, loader: MCPSubprocessLoader):
        self._loader = loader

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        return await self._loader.call(text, context)

    async def handle_tool_call(
        self, args: dict[str, Any], context: dict[str, Any]
    ) -> str:
        return await self._loader.call(str(args), context)

    def shutdown(self) -> None:
        self._loader.shutdown()
