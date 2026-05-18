from unittest.mock import AsyncMock

import pytest

from assistant.skill_router import SkillRouter
from assistant.tool_runner import ToolResult, ToolStatus


@pytest.mark.asyncio
async def test_direct_skill_uses_injected_tool_runner():
    tool_runner = AsyncMock()
    tool_runner.execute = AsyncMock(
        return_value=ToolResult(
            status=ToolStatus.OK,
            summary="The time is 10:30.",
            data="The time is 10:30.",
            tool_name="time",
            args={"command": "what time is it", "tool_name": "what time is it"},
        )
    )
    router = SkillRouter(tool_runner=tool_runner)

    result = await router._execute_skill("time", "what time is it", {"source": "test"})

    assert result == "The time is 10:30."
    tool_runner.execute.assert_awaited_once_with(
        "time",
        {"command": "what time is it", "tool_name": "what time is it"},
        user_intent="what time is it",
        context={"source": "test"},
    )


@pytest.mark.asyncio
async def test_direct_skill_confirmation_denial_returns_tool_message():
    tool_runner = AsyncMock()
    tool_runner.execute = AsyncMock(
        return_value=ToolResult(
            status=ToolStatus.REQUIRES_CONFIRMATION,
            summary="Action 'system' was denied.",
            tool_name="system",
            args={"command": "shutdown computer", "tool_name": "shutdown computer"},
        )
    )
    router = SkillRouter(tool_runner=tool_runner)

    result = await router._execute_skill("system", "shutdown computer", {})

    assert result == "Action 'system' was denied."
