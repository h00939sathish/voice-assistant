from unittest.mock import AsyncMock

import pytest

from assistant.skill_router import SkillRouter
from assistant.skills_registry import SkillsRegistry


@pytest.fixture
def loaded_router():
    router = SkillRouter()
    router.load_skills()
    return router


def test_match_skill_prefers_specific_keyword_over_generic_match(loaded_router):
    matched = SkillsRegistry.match_skill("what is my cpu usage")
    assert matched is not None
    assert matched.name == "system_monitor"


@pytest.mark.asyncio
async def test_registry_queries_route_directly(loaded_router):
    loaded_router._execute_skill = AsyncMock(return_value="ok")

    result = await loaded_router.route("what time is it", {})

    assert result == "ok"


@pytest.mark.asyncio
async def test_reminder_queries_route_directly(loaded_router):
    loaded_router._execute_skill = AsyncMock(return_value="ok")

    result = await loaded_router.route("list reminders", {})

    assert result == "ok"
    loaded_router._execute_skill.assert_awaited_once_with(
        "reminder", "list reminders", {}
    )


@pytest.mark.asyncio
async def test_browser_queries_route_directly(loaded_router):
    loaded_router._execute_skill = AsyncMock(return_value="ok")

    result = await loaded_router.route("open website https://example.com", {})

    assert result == "ok"
    loaded_router._execute_skill.assert_awaited_once_with(
        "browser",
        "open website https://example.com",
        {},
    )
