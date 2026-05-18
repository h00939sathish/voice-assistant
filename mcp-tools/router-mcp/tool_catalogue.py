"""
Tool Catalogue — SQLite-backed registry of all known tools with relevance scoring.
Scores tools against a query using keyword overlap and category matching.
"""

import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "tool_router.db"

# Category → keyword seeds for boosting
CATEGORY_SEEDS: dict[str, list[str]] = {
    "planning": [
        "plan",
        "goal",
        "task",
        "step",
        "audit",
        "schedule",
        "workflow",
        "track",
        "progress",
        "create",
    ],
    "filesystem": [
        "file",
        "folder",
        "directory",
        "read",
        "write",
        "open",
        "save",
        "copy",
        "move",
        "delete",
        "path",
    ],
    "system": [
        "system",
        "process",
        "memory",
        "cpu",
        "battery",
        "monitor",
        "kill",
        "app",
        "window",
        "screen",
    ],
    "media": [
        "play",
        "pause",
        "music",
        "song",
        "spotify",
        "youtube",
        "volume",
        "next",
        "previous",
        "audio",
    ],
    "web": [
        "search",
        "browser",
        "website",
        "url",
        "google",
        "internet",
        "browse",
        "research",
        "scrape",
    ],
    "time": [
        "time",
        "date",
        "reminder",
        "alarm",
        "calendar",
        "schedule",
        "when",
        "clock",
        "event",
    ],
    "shell": [
        "run",
        "command",
        "terminal",
        "bash",
        "execute",
        "shell",
        "script",
        "install",
    ],
    "general": [],
}


class ToolCatalogue:
    """SQLite registry of tools with scoring for query-based retrieval."""

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init_db(self):
        self._get_conn().executescript("""
            CREATE TABLE IF NOT EXISTS tools (
                name         TEXT PRIMARY KEY,
                description  TEXT NOT NULL DEFAULT '',
                server       TEXT NOT NULL DEFAULT 'native',
                category     TEXT NOT NULL DEFAULT 'general',
                keywords     TEXT NOT NULL DEFAULT '[]',
                use_count    INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT,
                schema_json  TEXT NOT NULL DEFAULT '{}',
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tools_category ON tools(category);
        """)
        self._get_conn().commit()

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    # ── Registration ──────────────────────────────────────────────────────

    def register_tool(
        self,
        name: str,
        description: str,
        server: str = "native",
        category: str = "general",
        keywords: list[str] | None = None,
        schema: dict | None = None,
    ) -> bool:
        """Upsert a tool into the catalogue. Returns True if new, False if updated."""
        conn = self._get_conn()
        now = self._now()
        kw_json = json.dumps(keywords or [])
        schema_json = json.dumps(schema or {})

        existing = conn.execute(
            "SELECT name FROM tools WHERE name=?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE tools SET description=?, server=?, category=?, keywords=?, schema_json=?, updated_at=? WHERE name=?",
                (description, server, category, kw_json, schema_json, now, name),
            )
            conn.commit()
            return False
        else:
            conn.execute(
                "INSERT INTO tools (name, description, server, category, keywords, schema_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (name, description, server, category, kw_json, schema_json, now, now),
            )
            conn.commit()
            return True

    def bulk_register(self, tools: list[dict[str, Any]]) -> int:
        """Register multiple tools at once. Returns count of new registrations."""
        count = 0
        for t in tools:
            is_new = self.register_tool(
                name=t["name"],
                description=t.get("description", ""),
                server=t.get("server", "native"),
                category=t.get("category", "general"),
                keywords=t.get("keywords", []),
                schema=t.get("schema"),
            )
            if is_new:
                count += 1
        return count

    def record_use(self, tool_name: str):
        """Increment use count and update last_used_at for recency boosting."""
        self._get_conn().execute(
            "UPDATE tools SET use_count = use_count + 1, last_used_at=? WHERE name=?",
            (self._now(), tool_name),
        )
        self._get_conn().commit()

    # ── Retrieval ─────────────────────────────────────────────────────────

    def list_all(self, category: str | None = None) -> list[dict[str, Any]]:
        conn = self._get_conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM tools WHERE category=? ORDER BY use_count DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tools ORDER BY category, use_count DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_tool(self, name: str) -> dict[str, Any] | None:
        row = (
            self._get_conn()
            .execute("SELECT * FROM tools WHERE name=?", (name,))
            .fetchone()
        )
        return self._row_to_dict(row) if row else None

    def count(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM tools").fetchone()[0]

    # ── Scoring ───────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 12) -> list[dict[str, Any]]:
        """Score all tools against query and return top-k ranked results."""
        all_tools = self.list_all()
        if not all_tools:
            return []

        query_words = set(re.findall(r"\w+", query.lower()))
        query_category = self._infer_category(query_words)

        scored = []
        for tool in all_tools:
            score = self._score_tool(tool, query_words, query_category)
            scored.append((score, tool))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Always include at least 1 tool per category for diversity (unless top_k very small)
        result = [t for _, t in scored[:top_k]]
        return result

    def _score_tool(self, tool: dict, query_words: set, query_category: str) -> float:
        score = 0.0

        tool_words = set(
            re.findall(r"\w+", (tool["name"] + " " + tool["description"]).lower())
        )
        kw_words = {
            w.lower() for kw in tool.get("keywords", []) for w in re.findall(r"\w+", kw)
        }
        all_tool_words = tool_words | kw_words

        # 1. Keyword overlap (0–5 pts)
        overlap = len(query_words & all_tool_words)
        score += min(overlap * 1.5, 5.0)

        # 2. Category match bonus (3 pts)
        if tool.get("category") == query_category:
            score += 3.0

        # 3. Name exact match bonus (4 pts)
        tool_name_words = set(re.findall(r"\w+", tool["name"].lower()))
        if query_words & tool_name_words:
            score += 2.0

        # 4. Recency bonus (0–1 pt) based on use_count
        use_count = tool.get("use_count", 0)
        score += min(use_count * 0.1, 1.0)

        return score

    def _infer_category(self, query_words: set) -> str:
        """Infer the most likely category from query words using seed keywords."""
        best_cat = "general"
        best_score = 0
        for cat, seeds in CATEGORY_SEEDS.items():
            if cat == "general":
                continue
            overlap = len(query_words & set(seeds))
            if overlap > best_score:
                best_score = overlap
                best_cat = cat
        return best_cat

    # ── Helpers ───────────────────────────────────────────────────────────

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["keywords"] = json.loads(d["keywords"]) if d.get("keywords") else []
        except Exception:
            d["keywords"] = []
        try:
            d["schema_json"] = (
                json.loads(d["schema_json"]) if d.get("schema_json") else {}
            )
        except Exception:
            d["schema_json"] = {}
        return d

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
