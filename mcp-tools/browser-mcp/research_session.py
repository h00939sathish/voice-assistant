"""
Research Session Store — SQLite-backed sessions for tracking web research findings.
"""

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "research.db"


class ResearchSessionStore:
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
            CREATE TABLE IF NOT EXISTS research_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic       TEXT NOT NULL,
                notes       TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_findings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  INTEGER NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
                url         TEXT NOT NULL DEFAULT '',
                title       TEXT DEFAULT '',
                snippet     TEXT DEFAULT '',
                note        TEXT DEFAULT '',
                added_at    TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_findings_session ON research_findings(session_id);
        """)
        self._get_conn().commit()

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def start_session(self, topic: str, notes: str = "") -> int:
        conn = self._get_conn()
        now = self._now()
        cur = conn.execute(
            "INSERT INTO research_sessions (topic, notes, created_at, updated_at) VALUES (?,?,?,?)",
            (topic, notes, now, now),
        )
        conn.commit()
        return cur.lastrowid

    def add_finding(
        self,
        session_id: int,
        url: str = "",
        title: str = "",
        snippet: str = "",
        note: str = "",
    ) -> int:
        conn = self._get_conn()
        now = self._now()
        cur = conn.execute(
            "INSERT INTO research_findings (session_id, url, title, snippet, note, added_at) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, url, title, snippet, note, now),
        )
        conn.execute(
            "UPDATE research_sessions SET updated_at=? WHERE id=?", (now, session_id)
        )
        conn.commit()
        return cur.lastrowid

    def get_session(self, session_id: int) -> dict[str, Any] | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM research_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not row:
            return None
        s = dict(row)
        findings = conn.execute(
            "SELECT * FROM research_findings WHERE session_id=? ORDER BY added_at",
            (session_id,),
        ).fetchall()
        s["findings"] = [dict(f) for f in findings]
        s["finding_count"] = len(s["findings"])
        return s

    def list_sessions(self) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT s.*, COUNT(f.id) as finding_count FROM research_sessions s "
            "LEFT JOIN research_findings f ON s.id=f.session_id "
            "GROUP BY s.id ORDER BY s.updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def summarise_session(self, session_id: int) -> str:
        session = self.get_session(session_id)
        if not session:
            return f"Session {session_id} not found."
        lines = [
            f"# Research: {session['topic']}",
            f"Session ID: {session_id}",
            f"Findings: {session['finding_count']}",
            "",
        ]
        for i, f in enumerate(session["findings"], 1):
            lines.append(f"{i}. {f.get('title') or f.get('url', 'No URL')}")
            if f.get("snippet"):
                lines.append(f"   > {f['snippet'][:200]}")
            if f.get("note"):
                lines.append(f"   📝 {f['note']}")
            if f.get("url"):
                lines.append(f"   🔗 {f['url']}")
            lines.append("")
        return "\n".join(lines)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
