import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import random

import pytest

from assistant.conversation_memory import ConversationMemory


@pytest.mark.asyncio
async def test_memory_race_condition():
    """
    Stress test memory with concurrent reads/writes to trigger race conditions.
    """
    memory = ConversationMemory()
    memory.clear()  # Ensure clean slate

    async def writer(id):
        for i in range(10):
            memory.add("user", f"Message {id}-{i}")
            # Simulate IO delay
            await asyncio.sleep(random.uniform(0.001, 0.01))

    async def reader():
        for _i in range(10):
            pass  # Just access
            _ = memory.get_recent()
            await asyncio.sleep(random.uniform(0.001, 0.01))

    # Run multiple writers and readers
    tasks = [writer(1), writer(2), reader(), reader()]
    await asyncio.gather(*tasks)

    # Check consistency
    history = memory.get_recent(n=100)
    # We expect 20 messages. If race updates occurred (e.g. JSON file corruption), this might fail or crash.
    print(f"History length: {len(history)}")
    assert len(history) == 20


if __name__ == "__main__":
    asyncio.run(test_memory_race_condition())
