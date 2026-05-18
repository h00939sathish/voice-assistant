"""
Planner Database — SQLite schema and operations for goals, tasks, and execution log.
Stores task graphs with dependency tracking and state transitions.
"""

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Default DB location: alongside memory.db
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "planner.db"


class PlannerDB:
    """SQLite database layer for the Planner MCP."""

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
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS goals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','active','completed','failed')),
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id     INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
                title       TEXT NOT NULL,
                description TEXT DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','running','completed','failed','skipped')),
                depends_on  TEXT DEFAULT '[]',
                order_index INTEGER DEFAULT 0,
                result      TEXT DEFAULT '',
                error       TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS execution_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id     INTEGER NOT NULL,
                task_id     INTEGER,
                action      TEXT NOT NULL,
                details     TEXT DEFAULT '',
                timestamp   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_log_goal ON execution_log(goal_id);
        """)
        conn.commit()

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    # ── Goals ────────────────────────────────────────────────────────────

    def create_goal(self, title: str, description: str = "") -> int:
        conn = self._get_conn()
        now = self._now()
        cur = conn.execute(
            "INSERT INTO goals (title, description, status, created_at, updated_at) VALUES (?,?,?,?,?)",
            (title, description, "pending", now, now),
        )
        goal_id = cur.lastrowid
        self._log(goal_id, None, "goal_created", f"Title: {title}")
        conn.commit()
        return goal_id

    def get_goal(self, goal_id: int) -> dict[str, Any] | None:
        row = (
            self._get_conn()
            .execute("SELECT * FROM goals WHERE id=?", (goal_id,))
            .fetchone()
        )
        return dict(row) if row else None

    def list_goals(self, status_filter: str | None = None) -> list[dict[str, Any]]:
        conn = self._get_conn()
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status=? ORDER BY id DESC", (status_filter,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM goals ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def update_goal_status(self, goal_id: int, status: str):
        now = self._now()
        self._get_conn().execute(
            "UPDATE goals SET status=?, updated_at=? WHERE id=?", (status, now, goal_id)
        )
        self._log(goal_id, None, "goal_status_changed", status)
        self._get_conn().commit()

    # ── Tasks ────────────────────────────────────────────────────────────

    def add_tasks(self, goal_id: int, tasks: list[dict[str, Any]]) -> list[int]:
        conn = self._get_conn()
        now = self._now()
        task_ids = []
        for i, t in enumerate(tasks):
            depends = json.dumps(t.get("depends_on", []))
            cur = conn.execute(
                "INSERT INTO tasks (goal_id, title, description, depends_on, order_index, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    goal_id,
                    t["title"],
                    t.get("description", ""),
                    depends,
                    t.get("order_index", i),
                    now,
                    now,
                ),
            )
            task_ids.append(cur.lastrowid)
        # Activate goal if it was pending
        conn.execute(
            "UPDATE goals SET status='active', updated_at=? WHERE id=? AND status='pending'",
            (now, goal_id),
        )
        self._log(goal_id, None, "tasks_added", f"{len(tasks)} tasks")
        conn.commit()
        return task_ids

    def get_tasks(self, goal_id: int) -> list[dict[str, Any]]:
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM tasks WHERE goal_id=? ORDER BY order_index", (goal_id,)
            )
            .fetchall()
        )
        result = []
        for r in rows:
            d = dict(r)
            d["depends_on"] = json.loads(d["depends_on"]) if d["depends_on"] else []
            result.append(d)
        return result

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        row = (
            self._get_conn()
            .execute("SELECT * FROM tasks WHERE id=?", (task_id,))
            .fetchone()
        )
        if row:
            d = dict(row)
            d["depends_on"] = json.loads(d["depends_on"]) if d["depends_on"] else []
            return d
        return None

    def update_task_status(
        self, task_id: int, status: str, result: str = "", error: str = ""
    ):
        now = self._now()
        self._get_conn().execute(
            "UPDATE tasks SET status=?, result=?, error=?, updated_at=? WHERE id=?",
            (status, result, error, now, task_id),
        )
        task = self.get_task(task_id)
        if task:
            self._log(task["goal_id"], task_id, f"task_{status}", result or error)
        self._get_conn().commit()

    def get_next_task(self, goal_id: int) -> dict[str, Any] | None:
        """Get next runnable task: pending, all dependencies completed."""
        tasks = self.get_tasks(goal_id)
        completed_ids = {t["id"] for t in tasks if t["status"] == "completed"}

        for t in tasks:
            if t["status"] != "pending":
                continue
            deps = t["depends_on"]
            if all(dep_id in completed_ids for dep_id in deps):
                return t
        return None

    def cancel_pending_tasks(self, goal_id: int) -> int:
        """Cancel all pending tasks for a goal. Returns count cancelled."""
        now = self._now()
        cur = self._get_conn().execute(
            "UPDATE tasks SET status='skipped', error='Cancelled by replan', updated_at=? "
            "WHERE goal_id=? AND status='pending'",
            (now, goal_id),
        )
        self._get_conn().commit()
        return cur.rowcount

    def skip_dependents(self, goal_id: int, failed_task_id: int):
        """Skip all tasks that transitively depend on a failed task."""
        tasks = self.get_tasks(goal_id)
        failed_ids = {failed_task_id}
        changed = True
        while changed:
            changed = False
            for t in tasks:
                if t["status"] == "pending" and t["id"] not in failed_ids:
                    if any(dep in failed_ids for dep in t["depends_on"]):
                        self.update_task_status(
                            t["id"],
                            "skipped",
                            error=f"Dependency {failed_task_id} failed",
                        )
                        failed_ids.add(t["id"])
                        changed = True

    # ── Execution Log ────────────────────────────────────────────────────

    def _log(self, goal_id: int, task_id: int | None, action: str, details: str = ""):
        self._get_conn().execute(
            "INSERT INTO execution_log (goal_id, task_id, action, details, timestamp) VALUES (?,?,?,?,?)",
            (goal_id, task_id, action, details, self._now()),
        )

    def get_log(self, goal_id: int, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM execution_log WHERE goal_id=? ORDER BY id DESC LIMIT ?",
                (goal_id, limit),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    # ── Lifecycle ────────────────────────────────────────────────────────

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
