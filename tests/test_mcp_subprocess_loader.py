"""
Tests for MCPSubprocessLoader / MCPSubprocessProxy.

Run:
    cd c:\\Users\\h0093\\Documents\\new
    .\\venv\\Scripts\\activate
    python -m pytest tests/test_mcp_subprocess_loader.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from assistant.mcp_subprocess_loader import MCPSubprocessLoader, MCPSubprocessProxy

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_fake_process(response: dict):
    """Returns a mock asyncio subprocess that replies with the given JSON."""
    proc = MagicMock()
    proc.returncode = None  # alive
    proc.pid = 99999

    response_line = (json.dumps(response) + "\n").encode()

    stdin = MagicMock()
    stdin.write = MagicMock()
    stdin.drain = AsyncMock()
    stdin.close = MagicMock()

    stdout = MagicMock()
    stdout.readline = AsyncMock(return_value=response_line)

    proc.stdin = stdin
    proc.stdout = stdout
    proc.terminate = MagicMock()
    return proc


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestMCPSubprocessLoader:
    @pytest.mark.asyncio
    async def test_call_returns_result(self):
        """Subprocess proxy returns the skill's result."""
        loader = MCPSubprocessLoader("skills/google_search_skill.py", "google_search")
        fake_proc = _make_fake_process({"id": 1, "result": "Found 3 results"})

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake_proc)):
            result = await loader.call("search for Python", {})

        assert result == "Found 3 results"

    @pytest.mark.asyncio
    async def test_call_handles_error_response(self):
        """Subprocess error key returns an error string (no exception)."""
        loader = MCPSubprocessLoader("skills/google_search_skill.py", "google_search")
        fake_proc = _make_fake_process({"id": 1, "error": "API key missing"})

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake_proc)):
            result = await loader.call("search for cats", {})

        assert "Skill error" in result
        assert "API key missing" in result

    @pytest.mark.asyncio
    async def test_call_timeout_returns_graceful_message(self):
        """A timed-out subprocess returns a graceful error, not an exception."""
        loader = MCPSubprocessLoader("skills/google_search_skill.py", "google_search")

        async def hang():
            await asyncio.sleep(999)

        proc = MagicMock()
        proc.returncode = None
        proc.pid = 1
        proc.stdin = MagicMock()
        proc.stdin.write = MagicMock()
        proc.stdin.drain = AsyncMock()
        proc.stdin.close = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.readline = hang  # type: ignore
        proc.terminate = MagicMock()

        import assistant.mcp_subprocess_loader as mod

        original_timeout = mod.CALL_TIMEOUT
        mod.CALL_TIMEOUT = 0.05  # 50ms for test speed

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await loader.call("search for cats", {})

        mod.CALL_TIMEOUT = original_timeout
        assert "timed out" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_shutdown_terminates_process(self):
        """shutdown() calls terminate() on the subprocess."""
        loader = MCPSubprocessLoader("skills/google_search_skill.py", "google_search")
        fake_proc = _make_fake_process({"id": 1, "result": "ok"})

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake_proc)):
            await loader.call("test", {})
            loader.shutdown()

        fake_proc.terminate.assert_called_once()
        assert loader._process is None

    def test_proxy_has_handle_method(self):
        """MCPSubprocessProxy exposes .handle() like any in-process skill."""
        loader = MCPSubprocessLoader("skills/google_search_skill.py", "google_search")
        proxy = MCPSubprocessProxy(loader)
        assert hasattr(proxy, "handle")
        assert hasattr(proxy, "shutdown")


class TestSkillRegistryMCPIsolated:
    def test_mcp_isolated_flag_propagates(self):
        """@skill(mcp_isolated=True) sets metadata correctly."""
        from assistant.skills_registry import SkillsRegistry

        meta = SkillsRegistry.get_skill("google_search")
        if meta:  # only if module was imported
            assert meta.mcp_isolated is True
            assert meta.script_path.endswith("google_search_skill.py")


if __name__ == "__main__":
    asyncio.run(asyncio.sleep(0))  # sanity check event loop
    print("✅ Run with: python -m pytest tests/test_mcp_subprocess_loader.py -v")
