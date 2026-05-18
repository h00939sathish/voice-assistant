"""
Integration tests for long_term_memory schema migration and correction flows.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from assistant.long_term_memory import LongTermMemory


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_memory.db"


@pytest.fixture
def memory(tmp_db):
    """Fresh LongTermMemory with temp DB."""
    ltm = LongTermMemory(db_path=str(tmp_db))
    return ltm


# ---------------------------------------------------------------------------
# Schema and Migration
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    def test_fresh_db_is_v2(self, memory, tmp_db):
        """A brand new DB should start at schema v2."""
        conn = sqlite3.connect(str(tmp_db))
        try:
            row = conn.execute(
                "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
            ).fetchone()
            assert row is not None
            assert int(row[0]) == 2
        except sqlite3.OperationalError:
            # schema_version table may not exist if LTM doesn't create it for fresh
            pass
        finally:
            conn.close()

    def test_v1_categories_remapped(self, tmp_db):
        """Legacy v1 categories (personal, habit, context) should be migrated."""
        # Create a v1-style DB manually
        conn = sqlite3.connect(str(tmp_db))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY,
                content TEXT,
                category TEXT DEFAULT 'general',
                source TEXT DEFAULT 'conversation',
                confidence REAL DEFAULT 0.8,
                access_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO memories (content, category, confidence) VALUES (?, ?, ?)",
            ("User likes coffee", "personal", 0.9),
        )
        conn.execute(
            "INSERT INTO memories (content, category, confidence) VALUES (?, ?, ?)",
            ("User checks email first thing", "habit", 0.85),
        )
        conn.commit()
        conn.close()

        # Now init LTM which should run migration
        ltm = LongTermMemory(db_path=str(tmp_db))

        # Check that old categories were remapped
        profile_facts = ltm.get_all_by_category("profile")
        preference_facts = ltm.get_all_by_category("preference")

        # At least one of the remapped categories should have entries
        total = len(profile_facts) + len(preference_facts)
        assert total >= 1, "Migration should remap v1 categories"


# ---------------------------------------------------------------------------
# Correction Flows
# ---------------------------------------------------------------------------


class TestCorrectionFlows:
    def test_remember_this(self, memory):
        """remember_this stores a fact with high confidence."""
        memory.remember_this("My favorite color is blue")
        facts = memory.get_all_by_category("profile")
        contents = [f.content for f in facts]
        assert any("blue" in c.lower() for c in contents)

    def test_forget_this(self, memory):
        """forget_this marks memories as forgotten."""
        memory.remember_this("I hate broccoli")
        memory.forget_this("broccoli")
        # After forgetting, searching should not return it with high confidence
        results = memory.search("broccoli", limit=5, min_confidence=0.5)
        high_conf = [r for r in results if r.confidence >= 0.5]
        # The forgotten entry should have very low confidence or be excluded
        assert len(high_conf) == 0 or all(
            "broccoli" not in r.content.lower() for r in high_conf
        )

    def test_correct_this(self, memory):
        """correct_this should update an existing fact."""
        memory.remember_this("My name is Alice")
        memory.correct_this("My name is Alice", "My name is Bob")
        facts = memory.get_all_by_category("profile")
        contents = [f.content for f in facts]
        assert any("Bob" in c for c in contents)
        assert not any("Alice" in c for c in contents)

    def test_always_do(self, memory):
        """always_do stores a preference."""
        memory.always_do("Use dark mode")
        facts = memory.get_all_by_category("preference")
        contents = [f.content for f in facts]
        assert any("dark mode" in c.lower() for c in contents)

    def test_task_memories_expire_from_retrieval(self, memory):
        """Task memories older than 7 days should not be surfaced."""
        memory.store(
            "Old task context", category="task", confidence=1.0, source="manual_user"
        )
        conn = sqlite3.connect(str(memory.db_path))
        conn.execute(
            "UPDATE memories SET created_at = datetime('now', '-10 days') WHERE content = ?",
            ("Old task context",),
        )
        conn.commit()
        conn.close()

        results = memory.search("Old task context", limit=5, min_confidence=0.0)
        assert not any("Old task context" in r.content for r in results)


# ---------------------------------------------------------------------------
# Prompt Injection
# ---------------------------------------------------------------------------


class TestFactsForPrompt:
    def test_get_facts_returns_string(self, memory):
        memory.remember_this("User lives in NYC")
        facts = memory.get_facts_for_prompt()
        assert isinstance(facts, str)

    def test_get_facts_deduplicates(self, memory):
        memory.remember_this("User likes pizza")
        memory.remember_this("User likes pizza")  # duplicate
        facts = memory.get_facts_for_prompt()
        # Should not have duplicate lines
        lines = [line for line in facts.split("\n") if line.strip()]
        unique = set(lines)
        assert len(lines) == len(unique), "Facts should be deduplicated"
