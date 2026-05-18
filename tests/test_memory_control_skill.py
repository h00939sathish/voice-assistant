import re
import time

import pytest

from skills.memory_control_skill import MemoryControlSkill


@pytest.mark.asyncio
async def test_memory_control_store_search_delete_roundtrip():
    skill = MemoryControlSkill()
    marker = f"pytest-memory-marker-{int(time.time())}"

    save_resp = await skill.handle(f"remember that {marker}", {})
    save_match = re.search(r"memory #(\d+)", save_resp.lower())
    assert save_match, save_resp
    memory_id = int(save_match.group(1))

    search_resp = await skill.handle(f"search memory {marker}", {})
    assert marker in search_resp

    delete_req = await skill.handle(f"forget memory {memory_id}", {})
    token_match = re.search(
        rf"confirm delete memory {memory_id} (\d{{4}})", delete_req.lower()
    )
    assert token_match, delete_req
    token = token_match.group(1)

    confirm_resp = await skill.handle(f"confirm delete memory {memory_id} {token}", {})
    assert "deleted memory" in confirm_resp.lower()


@pytest.mark.asyncio
async def test_memory_control_correction_and_forget_query_flow():
    skill = MemoryControlSkill()
    marker_old = f"favorite color is red {int(time.time())}"
    marker_new = marker_old.replace("red", "blue")

    save_resp = await skill.handle(f"remember that {marker_old}", {})
    assert "saved memory" in save_resp.lower()

    correct_resp = await skill.handle(
        f"remember this instead {marker_new} instead of {marker_old}",
        {},
    )
    assert "updated memory" in correct_resp.lower()

    search_new = await skill.handle(f"search memory {marker_new}", {})
    assert marker_new in search_new

    forget_resp = await skill.handle(f"forget this {marker_new}", {})
    assert "forgot " in forget_resp.lower()

    search_after_forget = await skill.handle(f"search memory {marker_new}", {})
    assert "couldn't find" in search_after_forget.lower()
