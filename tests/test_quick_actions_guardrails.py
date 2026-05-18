import re

import pytest

from skills.quick_actions_skill import QuickActionsSkill


@pytest.mark.asyncio
async def test_shutdown_needs_token_confirmation(monkeypatch):
    skill = QuickActionsSkill()

    initial = await skill.handle("shutdown", {})
    match = re.search(r"confirm shutdown (\d{4})", initial.lower())
    assert match, initial
    token = match.group(1)

    monkeypatch.setattr(skill, "_shutdown_computer", lambda: "shutdown scheduled")
    confirmed = await skill.handle(f"confirm shutdown {token}", {})
    assert confirmed == "shutdown scheduled"


@pytest.mark.asyncio
async def test_restart_rejects_wrong_token():
    skill = QuickActionsSkill()

    initial = await skill.handle("restart computer", {})
    match = re.search(r"confirm restart (\d{4})", initial.lower())
    assert match, initial

    wrong = "0000" if match.group(1) != "0000" else "9999"
    response = await skill.handle(f"confirm restart {wrong}", {})
    assert "mismatch" in response.lower()
