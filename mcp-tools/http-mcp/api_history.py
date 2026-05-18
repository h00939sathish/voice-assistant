"""
API History — SQLite log of HTTP requests made via the HTTP MCP.
Auto-prunes to keep last 500 entries.
"""

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "api_history.db"
MAX_HISTORY = 500


class ApiHistory:
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
            CREATE TABLE IF NOT EXISTS api_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                method      TEXT NOT NULL,
                url         TEXT NOT NULL,
                status      INTEGER,
                elapsed_ms  INTEGER,
                note        TEXT DEFAULT '',
                ok          INTEGER DEFAULT 0,
                requested_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_api_url ON api_requests(url);
            CREATE INDEX IF NOT EXISTS idx_api_time ON api_requests(requested_at);
        """)
        self._get_conn().commit()

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def log(
        self,
        method: str,
        url: str,
        status: int = 0,
        elapsed_ms: int = 0,
        ok: bool = False,
        note: str = "",
    ) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO api_requests (method, url, status, elapsed_ms, ok, note, requested_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (method.upper(), url, status, elapsed_ms, int(ok), note, self._now()),
        )
        conn.commit()
        row_id = cur.lastrowid
        # Auto-prune if over limit
        self._prune()
        return row_id

    def _prune(self):
        conn = self._get_conn()
        count = conn.execute("SELECT COUNT(*) FROM api_requests").fetchone()[0]
        if count > MAX_HISTORY:
            conn.execute(
                "DELETE FROM api_requests WHERE id IN "
                "(SELECT id FROM api_requests ORDER BY requested_at ASC LIMIT ?)",
                (count - MAX_HISTORY,),
            )
            conn.commit()

    def get_history(
        self, limit: int = 20, url_filter: str | None = None
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        if url_filter:
            rows = conn.execute(
                "SELECT * FROM api_requests WHERE url LIKE ? ORDER BY requested_at DESC LIMIT ?",
                (f"%{url_filter}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM api_requests ORDER BY requested_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
