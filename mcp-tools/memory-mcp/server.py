"""
Vector Memory MCP Server — Exposes Buddy's LongTermMemory as LLM-callable tools.
Wraps the existing assistant/long_term_memory.LongTermMemory class.
Uses the same data/memory.db — no migration needed.
"""

import json
import os
import sys

# Add project root so we can import the existing LongTermMemory
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)

import importlib.util

# Import LongTermMemory directly (bypasses assistant/__init__.py which pulls numpy/PyAudio)
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_ltm_spec = importlib.util.spec_from_file_location(
    "long_term_memory", os.path.join(PROJECT_ROOT, "assistant", "long_term_memory.py")
)
_ltm_mod = importlib.util.module_from_spec(_ltm_spec)
_ltm_spec.loader.exec_module(_ltm_mod)
LongTermMemory = _ltm_mod.LongTermMemory

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("VectorMemory")
memory = LongTermMemory()

VALID_CATEGORIES = [
    "personal",
    "preference",
    "habit",
    "context",
    "relationship",
    "goal",
    "event",
    "correction",
]


@mcp.tool()
def store_memory(
    content: str, category: str = "general", confidence: float = 1.0
) -> str:
    """Store a new memory about the user persistently across all sessions.

    Use this whenever the user shares a fact, preference, habit, goal, or
    relationship that should be remembered in future conversations.

    Args:
        content: The fact or memory to store (e.g. "User prefers dark mode")
        category: One of: personal, preference, habit, context, relationship, goal, event, correction
        confidence: Confidence score 0.0–1.0 (default 1.0 for explicit user statements)
    """
    if category not in VALID_CATEGORIES and category != "general":
        category = "general"
    confidence = max(0.0, min(1.0, confidence))

    memory_id = memory.store(
        content, category=category, confidence=confidence, source="llm_tool"
    )
    return json.dumps(
        {
            "memory_id": memory_id,
            "stored": memory_id > 0,
            "content": content,
            "category": category,
            "confidence": confidence,
        },
        indent=2,
    )


@mcp.tool()
def search_memory(
    query: str, category: str = "", limit: int = 5, min_confidence: float = 0.5
) -> str:
    """Search long-term memory for facts relevant to a query.

    Uses keyword matching (and vector similarity if sqlite-vec is available).
    Returns memories ranked by relevance and access frequency.

    Args:
        query: Natural language search query
        category: Optional category filter (personal, preference, habit, etc.)
        limit: Max number of memories to return (default 5)
        min_confidence: Minimum confidence threshold 0.0–1.0 (default 0.5)
    """
    cat = category if category in VALID_CATEGORIES else None
    limit = min(max(1, limit), 20)
    min_confidence = max(0.0, min(1.0, min_confidence))

    results = memory.search(
        query, category=cat, limit=limit, min_confidence=min_confidence
    )
    return json.dumps(
        {
            "query": query,
            "count": len(results),
            "memories": [
                {
                    "id": m.id,
                    "content": m.content,
                    "category": m.category,
                    "confidence": m.confidence,
                    "access_count": m.access_count,
                }
                for m in results
            ],
        },
        indent=2,
    )


@mcp.tool()
def recall_context(conversation: str, limit: int = 3) -> str:
    """Recall memories relevant to the current conversation context.

    Searches for high-confidence memories (≥0.7) that are semantically
    related to the ongoing conversation. Use this at the start of a session
    or when context seems relevant.

    Args:
        conversation: Recent conversation text or current topic
        limit: Max memories to recall (default 3)
    """
    limit = min(max(1, limit), 10)
    recalled = memory.recall_context(conversation, limit=limit)
    return json.dumps(
        {
            "conversation_snippet": conversation[:100] + "..."
            if len(conversation) > 100
            else conversation,
            "recalled": len(recalled),
            "memories": recalled,
        },
        indent=2,
    )


@mcp.tool()
def get_facts_for_prompt() -> str:
    """Get a formatted string of high-confidence user facts for prompt injection.

    Returns personal facts, preferences, relationships, and habits suitable
    for adding to a system prompt to personalise responses.
    """
    facts_str = memory.get_facts_for_prompt()
    lines = [l for l in facts_str.split("\n") if l.strip()] if facts_str else []
    return json.dumps(
        {
            "facts_count": len(lines),
            "facts": lines,
            "prompt_block": facts_str or "(no stored facts yet)",
        },
        indent=2,
    )


@mcp.tool()
def correct_memory(memory_id: int, correction: str) -> str:
    """Correct or override an existing memory.

    Halves the confidence of the original memory and stores the correction
    as a new 'correction' category entry. Use when the user says something
    like "actually, that's wrong — I meant..."

    Args:
        memory_id: ID of the memory to correct (from search_memory results)
        correction: The corrected version of the fact
    """
    memory.correct_memory(memory_id, correction)
    # Store the correction as a new high-confidence memory
    new_id = memory.store(
        correction, category="correction", confidence=1.0, source="user_correction"
    )
    return json.dumps(
        {
            "original_id": memory_id,
            "original_confidence_halved": True,
            "correction_stored": new_id > 0,
            "new_memory_id": new_id,
        },
        indent=2,
    )


@mcp.tool()
def get_memory_stats() -> str:
    """Get statistics about the long-term memory database.

    Returns total memory count, breakdown by category, and average confidence.
    """
    stats = memory.get_stats()
    return json.dumps(stats, indent=2)


@mcp.tool()
def clear_memories(confirm: bool = False) -> str:
    """Clear ALL long-term memories. This is irreversible.

    You MUST pass confirm=True to actually clear. Without it, this is a no-op.
    Only use when the user explicitly requests to wipe their memory.

    Args:
        confirm: Must be True to actually clear memories
    """
    if not confirm:
        return json.dumps(
            {
                "cleared": False,
                "reason": "Safety guard: pass confirm=True to actually clear all memories",
            },
            indent=2,
        )

    memory.clear()
    return json.dumps(
        {"cleared": True, "message": "All long-term memories deleted"}, indent=2
    )


if __name__ == "__main__":
    mcp.run()
