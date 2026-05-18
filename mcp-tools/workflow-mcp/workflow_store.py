"""
Workflow Store — SQLite-backed library of named, reusable multi-step automation workflows.
"""

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "workflows.db"


class WorkflowStore:
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
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self):
        self._get_conn().executescript("""
            CREATE TABLE IF NOT EXISTS workflows (
                name         TEXT PRIMARY KEY,
                description  TEXT DEFAULT '',
                tags         TEXT DEFAULT '[]',
                use_count    INTEGER DEFAULT 0,
                last_run_at  TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workflow_steps (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_name TEXT NOT NULL REFERENCES workflows(name) ON DELETE CASCADE,
                order_index  INTEGER NOT NULL,
                tool         TEXT NOT NULL,
                server       TEXT NOT NULL DEFAULT 'native',
                args_template TEXT NOT NULL DEFAULT '{}',
                description  TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_steps_workflow ON workflow_steps(workflow_name, order_index);
        """)
        self._get_conn().commit()

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    # ── Workflows ─────────────────────────────────────────────────────────

    def save_workflow(
        self,
        name: str,
        description: str,
        steps: list[dict[str, Any]],
        tags: list[str] | None = None,
    ) -> bool:
        """Upsert workflow by name. Returns True if new, False if updated."""
        conn = self._get_conn()
        now = self._now()
        tags_json = json.dumps(tags or [])
        existing = conn.execute(
            "SELECT name FROM workflows WHERE name=?", (name,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE workflows SET description=?, tags=?, updated_at=? WHERE name=?",
                (description, tags_json, now, name),
            )
            # Replace all steps
            conn.execute("DELETE FROM workflow_steps WHERE workflow_name=?", (name,))
        else:
            conn.execute(
                "INSERT INTO workflows (name, description, tags, created_at, updated_at) VALUES (?,?,?,?,?)",
                (name, description, tags_json, now, now),
            )

        for i, step in enumerate(steps):
            conn.execute(
                "INSERT INTO workflow_steps (workflow_name, order_index, tool, server, args_template, description) "
                "VALUES (?,?,?,?,?,?)",
                (
                    name,
                    step.get("order_index", i),
                    step["tool"],
                    step.get("server", "native"),
                    json.dumps(step.get("args", {})),
                    step.get("description", ""),
                ),
            )

        conn.commit()
        return not bool(existing)

    def get_workflow(self, name: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM workflows WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        w = dict(row)
        w["tags"] = json.loads(w["tags"]) if w["tags"] else []
        steps = conn.execute(
            "SELECT * FROM workflow_steps WHERE workflow_name=? ORDER BY order_index",
            (name,),
        ).fetchall()
        w["steps"] = [
            {
                "order_index": s["order_index"],
                "tool": s["tool"],
                "server": s["server"],
                "args": json.loads(s["args_template"]) if s["args_template"] else {},
                "description": s["description"],
            }
            for s in steps
        ]
        return w

    def list_workflows(self, tag: str | None = None) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM workflows ORDER BY use_count DESC, updated_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            w = dict(row)
            w["tags"] = json.loads(w["tags"]) if w["tags"] else []
            step_count = conn.execute(
                "SELECT COUNT(*) FROM workflow_steps WHERE workflow_name=?",
                (row["name"],),
            ).fetchone()[0]
            w["step_count"] = step_count
            if tag and tag not in w["tags"]:
                continue
            result.append(w)
        return result

    def delete_workflow(self, name: str) -> bool:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM workflows WHERE name=?", (name,))
        conn.commit()
        return cur.rowcount > 0

    def record_run(self, name: str):
        self._get_conn().execute(
            "UPDATE workflows SET use_count=use_count+1, last_run_at=? WHERE name=?",
            (self._now(), name),
        )
        self._get_conn().commit()

    def render_workflow(self, name: str, inputs: dict[str, Any]) -> list[dict] | None:
        """Return steps with {{input.key}} placeholders resolved from inputs dict."""
        wf = self.get_workflow(name)
        if not wf:
            return None
        rendered = []
        for step in wf["steps"]:
            args_str = json.dumps(step["args"])
            for key, val in inputs.items():
                args_str = args_str.replace(f"{{{{input.{key}}}}}", str(val))
            rendered.append(
                {
                    "order_index": step["order_index"],
                    "tool": step["tool"],
                    "server": step["server"],
                    "args": json.loads(args_str),
                    "description": step["description"],
                }
            )
        return rendered

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
