"""
Test script for Long-Term Memory System

Tests:
1. Memory storage with categories
2. Semantic search
3. Contextual recall
4. Fact extraction integration
5. Memory stats
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from assistant.long_term_memory import LongTermMemory
from assistant.llm_router import LLMRouter


def test_long_term_memory():
    """Test the LongTermMemory class directly"""
    print("\n" + "=" * 60)
    print("Testing LongTermMemory Core System")
    print("=" * 60)

    ltm = LongTermMemory()

    # Store various memory types
    print("\n--- Storing Memories ---")
    memories = [
        ("User works at Microsoft", "personal", 0.95),
        ("User's wife is named Sarah", "relationship", 1.0),
        ("User prefers dark mode in IDE", "preference", 0.9),
        ("User likes jazz music", "preference", 0.85),
        ("User usually wakes up at 7am", "habit", 0.8),
        ("User is working on a Python project", "context", 0.75),
        ("User plans to visit Japan next year", "goal", 0.9),
    ]

    for content, category, confidence in memories:
        mem_id = ltm.store(content, category, confidence)
        print(f"  Stored: [{category}] {content} (ID: {mem_id})")

    # Check stats
    stats = ltm.get_stats()
    print("\n--- Memory Stats ---")
    print(f"  Total memories: {stats.get('total_memories', 0)}")
    print(f"  By category: {stats.get('by_category', {})}")
    print(f"  Average confidence: {stats.get('average_confidence', 0)}")

    # Test semantic search
    print("\n--- Testing Semantic Search ---")
    test_queries = [
        "Where does the user work?",
        "Who is the user's wife?",
        "What music does the user like?",
        "Tell me about the user's morning routine",
        "What is the user working on?",
    ]

    for query in test_queries:
        print(f"\n  Query: '{query}'")
        results = ltm.search(query, limit=3)
        for mem in results:
            print(f"    -> [{mem.category}] {mem.content}")

    # Test contextual recall
    print("\n--- Testing Contextual Recall ---")
    conversations = [
        "I'm thinking about my career...",
        "I want to plan a vacation",
        "What should I listen to while coding?",
    ]

    for convo in conversations:
        print(f"\n  Context: '{convo}'")
        memories = ltm.recall_context(convo, limit=2)
        for mem in memories:
            print(f"    -> {mem}")

    # Test facts for prompt
    print("\n--- Testing Facts for Prompt ---")
    facts = ltm.get_facts_for_prompt()
    print(f"  Formatted facts:\n{facts}")

    return ltm


async def test_fact_extraction():
    """Test fact extraction from conversations"""
    print("\n" + "=" * 60)
    print("Testing Fact Extraction")
    print("=" * 60)

    router = LLMRouter(prefer_local=False)

    # Clear memory for clean test
    router.memory.clear()
    if router.long_term_memory:
        router.long_term_memory.clear()

    # Simulate conversations
    test_conversations = [
        "My name is John and I work at Google.",
        "I really love drinking espresso in the morning.",
        "My wife Sarah and I have a dog named Max.",
    ]

    for user_msg in test_conversations:
        print(f"  User: {user_msg}")
        response = router.chat(user_msg)
        print(f"  Buddy: {response}")

    # Wait for background extraction
    print("  Waiting for fact extraction (5s)...")
    await asyncio.sleep(5)

    # Check short-term memory facts
    print("\n--- Short-term Facts ---")
    facts = router.memory.get_all_facts()
    for fact in facts:
        print(f"  -> {fact}")

    # Check long-term memory
    if router.long_term_memory:
        print("\n--- Long-term Memory Stats ---")
        stats = router.long_term_memory.get_stats()
        print(f"  Stats: {stats}")

        print("\n--- Searching Long-term Memory ---")
        searches = ["name", "work", "wife", "dog"]
        for query in searches:
            results = router.long_term_memory.search(query, limit=2)
            if results:
                print(f"  '{query}': {results[0].content}")

    # Test memory in prompts
    print("\n--- Testing Memory in Prompts ---")
    messages = router._build_messages("What do you know about me?")
    system_msg = messages[0]["content"]

    if "RELEVANT MEMORIES" in system_msg or "THINGS YOU KNOW" in system_msg:
        print("  [OK] Facts injected into system prompt!")
        # Show relevant part
        if "RELEVANT MEMORIES" in system_msg:
            relevant_part = system_msg.split("RELEVANT MEMORIES")[1].split("\n\n")[0]
            print(f"  Injected: {relevant_part[:200]}...")
    else:
        print("  [FAIL] Facts not injected.")


async def main():
    print("=" * 60)
    print("Long-Term Memory System Tests")
    print("=" * 60)

    try:
        # Test core memory system
        ltm = test_long_term_memory()

        # Test integration with LLM router
        await test_fact_extraction()

        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
