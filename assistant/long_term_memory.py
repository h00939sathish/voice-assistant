"""
Long-Term Memory System - Persistent semantic memory with vector search

Provides:
- Vector storage for memories using sqlite-vec
- Semantic search through memories (not just keyword)
- Contextual recall based on current conversation
- Memory confidence scoring
- User corrections support
- Entity relationship graph (Knowledge Graph)

Memory types:
- Personal facts ("I work at Microsoft", "My wife's name is Sarah")
- Preferences ("I like jazz music", "Prefer Celsius")
- Habits ("Usually wake up at 7am", "Check email first thing")
- Context ("Working on Python project", "Planning trip to Japan")
- Relationships ("Boss is John", "Dog is named Max")
"""
import sqlite3
import json
import hashlib
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import re

# Import config if available
try:
    from config import MEMORY_DB_PATH, ENABLE_EMBEDDINGS
except ImportError:
    MEMORY_DB_PATH = "data/memory.db"
    ENABLE_EMBEDDINGS = False  # Default to off to save RAM

@dataclass
class Memory:
    """Represents a single memory entry"""
    id: Optional[int]
    content: str
    category: str
    confidence: float
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    access_count: int
    last_accessed: Optional[datetime]
    source: Optional[str] = None


class LongTermMemory:
    """
    Persistent long-term memory with semantic search capabilities.
    Uses sqlite-vec for vector storage and similarity search.
    """

    # Schema version — bump when migration is needed
    SCHEMA_VERSION = 2

    # Categories with write policies
    #   profile:    Store once, update on correction. Newer wins with confidence decay.
    #   preference: Upsert by topic key. Explicit override replaces.
    #   task:       Session-scoped, auto-expire after 7d. Append-only.
    #   factual:    Store with source attribution. Multiple sources increase confidence.
    #   session:    In-memory only, never persisted. (handled outside DB)
    #   rejected:   Soft-delete target + store rejection reason. Prevents re-learning.
    #   personal:   (legacy alias for profile) Personal facts about the user
    #   habit:      (legacy alias for preference) Regular behaviors and routines
    #   context:    (legacy alias for task) Current activities and projects
    #   relationship: People, pets, and relationships
    #   goal:       Goals, plans, and aspirations
    #   event:      Important past events
    #   correction: User corrections to previous memories
    CATEGORIES = {
        "general": "Generic memory entries retained for backward compatibility",
        "profile": "Personal facts about the user (name, age, location, work)",
        "preference": "User preferences and likes/dislikes",
        "task": "Session-scoped task context (auto-expires after 7 days)",
        "factual": "Facts with source attribution",
        "rejected": "Memories the user explicitly rejected or corrected away",
        "personal": "[legacy → profile] Personal facts about the user",
        "habit": "[legacy → preference] Regular behaviors and routines",
        "context": "[legacy → task] Current activities and projects",
        "relationship": "People, pets, and relationships",
        "goal": "Goals, plans, and aspirations",
        "event": "Important past events",
        "correction": "User corrections to previous memories",
    }

    # v1 → v2 category remapping
    _CATEGORY_MIGRATION_MAP = {
        "personal": "profile",
        "habit": "preference",
        "context": "task",
    }

    def __init__(self, storage_path: Optional[Path] = None, db_path: Optional[Path] = None):
        if db_path is not None:
            storage_path = db_path
        if storage_path is None:
            base_dir = Path(__file__).parent.parent
            storage_path = base_dir / MEMORY_DB_PATH

        self.db_path = Path(storage_path)
        self._lock = threading.Lock()
        self._vec = None

        if not self.db_path.parent.exists():
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"   [!] Could not create data directory: {e}")

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-safe DB connection with vec extension loaded"""
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-4096")

        try:
            conn.enable_load_extension(True)
            for ext_name in ["vec0", "vec", "libvec", "sqlite_vec"]:
                try:
                    conn.load_extension(ext_name)
                    self._vec = True
                    break
                except Exception:
                    continue
        except Exception:
            pass

        return conn

    def _init_db(self):
        """Initialize database schema with vector support"""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS memories (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            content TEXT NOT NULL,
                            category TEXT DEFAULT 'general',
                            confidence REAL DEFAULT 1.0,
                            source TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            access_count INTEGER DEFAULT 0,
                            last_accessed DATETIME,
                            embedding_id INTEGER
                        )
                    """)

                    if self._vec:
                        try:
                            cursor.execute("""
                                CREATE VIRTUAL TABLE IF NOT EXISTS memory_embeddings USING vec0(
                                    embedding float[384]
                                )
                            """)
                        except Exception:
                            self._vec = False

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS memory_keywords (
                            memory_id INTEGER,
                            keyword TEXT,
                            PRIMARY KEY (memory_id, keyword),
                            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
                        )
                    """)

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS memory_corrections (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            memory_id INTEGER,
                            correction TEXT NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
                        )
                    """)

                    # Entity relationships table (Knowledge Graph)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS entity_relationships (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            subject TEXT NOT NULL,
                            predicate TEXT NOT NULL,
                            object TEXT NOT NULL,
                            confidence REAL DEFAULT 1.0,
                            source_memory_id INTEGER,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (source_memory_id) REFERENCES memories(id) ON DELETE SET NULL
                        )
                    """)

                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_category ON memories(category)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_confidence ON memories(confidence)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_accessed ON memories(last_accessed)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords ON memory_keywords(keyword)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_subject ON entity_relationships(subject)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_object ON entity_relationships(object)")

                    # Schema version tracking
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS schema_version (
                            version INTEGER PRIMARY KEY,
                            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    conn.commit()

                    # Run migrations
                    self._run_migrations(conn)
            except Exception as e:
                print(f"   [!] Long-term Memory DB Init Error: {e}")

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding vector for text. Disabled by default to save ~400MB RAM."""
        if not ENABLE_EMBEDDINGS:
            return None

        try:
            from sentence_transformers import SentenceTransformer
            if not hasattr(self, '_embedding_model'):
                print("   🔄 Loading embedding model (all-MiniLM-L6-v2)...")
                self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            return self._embedding_model.encode(text).tolist()
        except ImportError:
            pass
        except Exception as e:
            print(f"   [!] SentenceTransformers error: {e}")

        try:
            import ollama
            response = ollama.embeddings(model='all-minilm', prompt=text)
            if 'embedding' in response:
                return response['embedding']
        except Exception:
            pass

        return self._simple_hash_embedding(text)

    def _simple_hash_embedding(self, text: str, dim: int = 384) -> List[float]:
        """Simple hashing-based embedding for fallback"""
        text = text.lower().strip()
        words = re.findall(r'\b\w+\b', text)
        vector = [0.0] * dim
        for word in words:
            hash_val = int(hashlib.md5(word.encode()).hexdigest(), 16)
            idx = hash_val % dim
            vector[idx] += 1.0

        magnitude = sum(x**2 for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        return vector

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for indexing"""
        words = re.findall(r'\b\w+\b', text.lower())
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                      'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                      'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                      'through', 'during', 'before', 'after', 'above', 'below',
                      'between', 'under', 'and', 'but', 'or', 'yet', 'so', 'if',
                      'because', 'although', 'though', 'while', 'where', 'when',
                      'that', 'which', 'who', 'whom', 'whose', 'what', 'this',
                      'these', 'those', 'i', 'me', 'my', 'myself', 'we', 'our',
                      'you', 'your', 'he', 'him', 'his', 'she', 'her', 'it',
                      'its', 'they', 'them', 'their', 'am', 'it'}
        return [w for w in words if w not in stop_words and len(w) > 2]

    def _canonical_category(self, category: Optional[str], default: str = "profile") -> str:
        """Normalize legacy or unknown categories to the canonical schema."""
        normalized = (category or default).strip().lower()
        normalized = self._CATEGORY_MIGRATION_MAP.get(normalized, normalized)
        if normalized not in self.CATEGORIES:
            return default
        return normalized

    def _normalize_memory_key(self, content: str) -> str:
        """Normalize memory text for exact-match deduplication."""
        return re.sub(r"\s+", " ", content.strip().lower())

    def _source_priority(self, source: Optional[str]) -> int:
        """Rank user-explicit memories ahead of inferred memories."""
        source_name = (source or "").strip().lower()
        if source_name in {"user_explicit", "manual_user"}:
            return 0
        if source_name == "user_correction":
            return 1
        return 2

    def _is_expired_task_memory(self, memory: Memory) -> bool:
        """Treat task memories older than 7 days as expired."""
        if memory.category != "task":
            return False
        if not memory.created_at:
            return False
        return memory.created_at < (datetime.now() - timedelta(days=7))

    def _is_visible_memory(self, memory: Memory, include_rejected: bool = False) -> bool:
        """Return whether a memory should be surfaced to retrieval/prompting."""
        category = self._canonical_category(memory.category, default="profile")
        if category == "rejected" and not include_rejected:
            return False
        if self._is_expired_task_memory(memory):
            return False
        return True

    def _reject_memory(self, conn: sqlite3.Connection, memory_id: int, reason: str) -> None:
        """Mark a memory as rejected and record why."""
        conn.execute(
            """UPDATE memories SET category = 'rejected', confidence = 0.0, updated_at = ?
               WHERE id = ?""",
            (datetime.now(), memory_id),
        )
        conn.execute(
            "INSERT INTO memory_corrections (memory_id, correction) VALUES (?, ?)",
            (memory_id, reason),
        )

    def store(self, content: str, category: str = "general", confidence: float = 1.0,
              source: str = None) -> int:
        """Store a new memory. Returns Memory ID."""
        normalized_content = content.strip()
        if not normalized_content:
            return -1
        canonical_category = self._canonical_category(category)
        normalized_key = self._normalize_memory_key(normalized_content)

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    # De-duplicate exact same memory in the same category.
                    cursor.execute(
                        """SELECT id, confidence, source FROM memories
                           WHERE category = ? AND LOWER(TRIM(content)) = ?
                           ORDER BY updated_at DESC LIMIT 1""",
                        (canonical_category, normalized_key),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        existing_id, existing_conf, existing_source = existing
                        merged_conf = max(float(existing_conf or 0.0), float(confidence))
                        preferred_source = source
                        if self._source_priority(existing_source) < self._source_priority(source):
                            preferred_source = existing_source
                        cursor.execute(
                            """UPDATE memories
                               SET confidence = ?, source = ?, updated_at = ?
                               WHERE id = ?""",
                            (merged_conf, preferred_source, datetime.now(), existing_id),
                        )
                        conn.commit()
                        return int(existing_id)

                    cursor.execute(
                        """INSERT INTO memories (content, category, confidence, source, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (normalized_content, canonical_category, confidence, source, datetime.now())
                    )
                    memory_id = int(cursor.lastrowid)

                    keywords = self._extract_keywords(normalized_content)
                    for keyword in keywords:
                        cursor.execute(
                            "INSERT OR IGNORE INTO memory_keywords (memory_id, keyword) VALUES (?, ?)",
                            (memory_id, keyword)
                        )

                    if self._vec:
                        try:
                            embedding = self._generate_embedding(normalized_content)
                            if embedding:
                                cursor.execute(
                                    "INSERT INTO memory_embeddings (rowid, embedding) VALUES (?, ?)",
                                    (memory_id, json.dumps(embedding))
                                )
                                cursor.execute(
                                    "UPDATE memories SET embedding_id = ? WHERE id = ?",
                                    (memory_id, memory_id)
                                )
                        except Exception as e:
                            print(f"   [!] Failed to store embedding: {e}")

                    conn.commit()
                    return memory_id
            except Exception as e:
                print(f"   [!] Failed to store memory: {e}")
                return -1

    def search(self, query: str, category: str = None, limit: int = 5,
               min_confidence: float = 0.5, include_rejected: bool = False) -> List[Memory]:
        """Search memories by semantic similarity to query."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                canonical_category = self._canonical_category(category, default="profile") if category else None
                memories = []

                if self._vec:
                    try:
                        query_embedding = self._generate_embedding(query)
                        if query_embedding:
                            cursor.execute(
                                """SELECT rowid, distance
                                   FROM memory_embeddings
                                   WHERE embedding MATCH ?
                                   ORDER BY distance
                                   LIMIT ?""",
                                (json.dumps(query_embedding), limit * 2)
                            )
                            vec_results = cursor.fetchall()
                            for row in vec_results:
                                mem_cursor = conn.execute(
                                    """SELECT * FROM memories
                                       WHERE id = ? AND confidence >= ?""",
                                    (row['rowid'], min_confidence)
                                )
                                mem_row = mem_cursor.fetchone()
                                if mem_row:
                                    mem = self._row_to_memory(mem_row)
                                    if canonical_category and mem.category != canonical_category:
                                        continue
                                    if not self._is_visible_memory(mem, include_rejected=include_rejected):
                                        continue
                                    memories.append(mem)
                    except Exception:
                        pass

                if len(memories) < limit:
                    keywords = self._extract_keywords(query)
                    if keywords:
                        placeholders = ','.join('?' for _ in keywords)
                        query_sql = f"""
                            SELECT m.*, COUNT(k.keyword) as match_count
                            FROM memories m
                            JOIN memory_keywords k ON m.id = k.memory_id
                            WHERE k.keyword IN ({placeholders})
                            AND m.confidence >= ?
                        """
                        params = keywords + [min_confidence]
                        if not include_rejected:
                            query_sql += " AND m.category != 'rejected'"
                        query_sql += " AND (m.category != 'task' OR datetime(m.created_at) >= datetime('now', '-7 days'))"
                        if canonical_category:
                            query_sql += " AND m.category = ?"
                            params.append(canonical_category)
                        query_sql += """
                            GROUP BY m.id
                            ORDER BY match_count DESC, m.access_count DESC
                            LIMIT ?
                        """
                        params.append(limit)
                        cursor.execute(query_sql, params)
                        for row in cursor.fetchall():
                            mem = self._row_to_memory(row)
                            if not self._is_visible_memory(mem, include_rejected=include_rejected):
                                continue
                            if mem.id not in [m.id for m in memories]:
                                memories.append(mem)

                for mem in memories[:limit]:
                    self._update_access_count(mem.id)
                return memories[:limit]

        except Exception as e:
            print(f"   [!] Memory search error: {e}")
            return []

    def recall_context(self, current_conversation: str, limit: int = 3) -> List[str]:
        """Recall relevant memories based on current conversation context."""
        memories = self.search(current_conversation, limit=limit)
        return [m.content for m in memories if m.confidence >= 0.7]

    def get_all_by_category(self, category: str) -> List[Memory]:
        """Get all memories of a specific category"""
        try:
            canonical_category = self._canonical_category(category)
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """SELECT * FROM memories
                       WHERE category = ?
                       ORDER BY confidence DESC, updated_at DESC""",
                    (canonical_category,)
                )
                return [
                    mem for mem in (self._row_to_memory(row) for row in cursor.fetchall())
                    if self._is_visible_memory(mem, include_rejected=(canonical_category == "rejected"))
                ]
        except Exception as e:
            print(f"   [!] Failed to get memories by category: {e}")
            return []

    def get_recent(self, limit: int = 10, min_confidence: float = 0.0,
                   category: Optional[str] = None, include_rejected: bool = False) -> List[Memory]:
        """Get most recent memories, optionally filtered by category/confidence."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                canonical_category = self._canonical_category(category, default="profile") if category else None
                if canonical_category:
                    cursor = conn.execute(
                        """SELECT * FROM memories
                           WHERE confidence >= ? AND category = ?
                           ORDER BY datetime(created_at) DESC
                           LIMIT ?""",
                        (min_confidence, canonical_category, limit)
                    )
                else:
                    cursor = conn.execute(
                        """SELECT * FROM memories
                           WHERE confidence >= ?
                           AND (? OR category != 'rejected')
                           AND (category != 'task' OR datetime(created_at) >= datetime('now', '-7 days'))
                           ORDER BY datetime(created_at) DESC
                           LIMIT ?""",
                        (min_confidence, 1 if include_rejected else 0, limit)
                    )
                return [
                    mem for mem in (self._row_to_memory(row) for row in cursor.fetchall())
                    if self._is_visible_memory(mem, include_rejected=include_rejected)
                ]
        except Exception as e:
            print(f"   [!] Failed to get recent memories: {e}")
            return []

    def get_facts_for_prompt(self) -> str:
        """Get formatted facts string for system prompt injection"""
        def collect(categories: List[str], min_confidence: float, limit: int) -> List[Memory]:
            items: List[Memory] = []
            seen: set = set()
            merged: List[Memory] = []
            for cat in categories:
                merged.extend(self.get_all_by_category(cat))
            merged.sort(
                key=lambda m: (
                    self._source_priority(getattr(m, "source", None)),
                    -(m.confidence or 0.0),
                    m.updated_at or m.created_at or datetime.min,
                ),
                reverse=False,
            )
            for mem in merged:
                if not self._is_visible_memory(mem):
                    continue
                if mem.confidence < min_confidence:
                    continue
                key = self._normalize_memory_key(mem.content)
                if key in seen:
                    continue
                seen.add(key)
                items.append(mem)
                if len(items) >= limit:
                    return items
            return items

        facts = []
        personal = collect(["profile"], 0.8, 5)
        facts.extend([f"Personal: {m.content}" for m in personal])
        preferences = collect(["preference"], 0.8, 5)
        facts.extend([f"Preference: {m.content}" for m in preferences])
        relationships = collect(["relationship"], 0.8, 5)
        facts.extend([f"Relationship: {m.content}" for m in relationships])
        if facts:
            return "\n".join(facts)
        return ""

    # ==================== Knowledge Graph ====================

    def store_relationship(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        source_memory_id: Optional[int] = None,
    ) -> int:
        """Store an entity relationship in the knowledge graph."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    # Deduplicate: update confidence if relationship already exists
                    cursor.execute(
                        """SELECT id, confidence FROM entity_relationships
                           WHERE LOWER(subject) = LOWER(?) AND LOWER(predicate) = LOWER(?)
                           AND LOWER(object) = LOWER(?)""",
                        (subject, predicate, obj),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        new_conf = max(existing[1], confidence)
                        cursor.execute(
                            "UPDATE entity_relationships SET confidence = ? WHERE id = ?",
                            (new_conf, existing[0]),
                        )
                        conn.commit()
                        return existing[0]

                    cursor.execute(
                        """INSERT INTO entity_relationships
                           (subject, predicate, object, confidence, source_memory_id, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (subject, predicate, obj, confidence, source_memory_id, datetime.now()),
                    )
                    conn.commit()
                    return cursor.lastrowid
            except Exception as e:
                print(f"   [!] Failed to store relationship: {e}")
                return -1

    def query_relationships(self, entity: str, limit: int = 10) -> List[dict]:
        """Find all relationships involving an entity (as subject or object)."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """SELECT subject, predicate, object, confidence
                       FROM entity_relationships
                       WHERE LOWER(subject) = LOWER(?) OR LOWER(object) = LOWER(?)
                       ORDER BY confidence DESC
                       LIMIT ?""",
                    (entity, entity, limit),
                )
                return [
                    {
                        "subject": row["subject"],
                        "predicate": row["predicate"],
                        "object": row["object"],
                        "confidence": row["confidence"],
                    }
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            print(f"   [!] Failed to query relationships: {e}")
            return []

    def get_relationship_context(self, query: str) -> str:
        """Get formatted relationship context for LLM prompt injection."""
        keywords = self._extract_keywords(query)
        if not keywords:
            return ""

        all_rels: List[dict] = []
        seen_ids: set = set()

        for kw in keywords[:5]:
            rels = self.query_relationships(kw, limit=5)
            for r in rels:
                rel_id = (r["subject"].lower(), r["predicate"].lower(), r["object"].lower())
                if rel_id not in seen_ids:
                    seen_ids.add(rel_id)
                    all_rels.append(r)

        if not all_rels:
            return ""

        lines = [f"- {r['subject']} {r['predicate']} {r['object']}" for r in all_rels[:10]]
        return "\n".join(lines)

    # ==================== Corrections & Updates ====================

    def correct_memory(self, memory_id: int, correction: str):
        """Record a user correction for a memory."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute(
                        "UPDATE memories SET confidence = confidence * 0.5, updated_at = ? WHERE id = ?",
                        (datetime.now(), memory_id)
                    )
                    conn.execute(
                        "INSERT INTO memory_corrections (memory_id, correction) VALUES (?, ?)",
                        (memory_id, correction)
                    )
                    conn.commit()
                    print("   [+] Memory corrected")
            except Exception as e:
                print(f"   [!] Failed to correct memory: {e}")

    # ==================== High-Level Correction Flows ====================

    def remember_this(self, content: str, category: str = "profile") -> int:
        """Explicitly store a fact the user asked to remember."""
        canonical_category = self._canonical_category(category, default="profile")
        return self.store(content, category=canonical_category, confidence=1.0, source="user_explicit")

    def forget_this(self, query: str) -> int:
        """Soft-delete memories matching query. Moves them to 'rejected' category."""
        matches = self.search(query, limit=10, min_confidence=0.0, include_rejected=False)
        rejected_count = 0
        for mem in matches:
            if mem.id is None:
                continue
            with self._lock:
                try:
                    with self._get_connection() as conn:
                        self._reject_memory(conn, mem.id, f"User requested forget: {query}")
                        conn.commit()
                        rejected_count += 1
                except Exception as e:
                    print(f"   [!] Failed to reject memory {mem.id}: {e}")
        if rejected_count:
            print(f"   [+] Rejected {rejected_count} memories matching '{query}'")
        return rejected_count

    def correct_this(self, query: str, correction: str) -> bool:
        """Find the best matching memory and apply a correction."""
        matches = self.search(query, limit=1, min_confidence=0.0, include_rejected=False)
        if not matches or matches[0].id is None:
            # No match found — store the correction as a new fact
            self.store(correction, category="profile", confidence=0.95, source="user_correction")
            return True
        mem = matches[0]
        canonical_category = self._canonical_category(mem.category, default="profile")
        with self._lock:
            try:
                with self._get_connection() as conn:
                    self._reject_memory(conn, mem.id, f"User correction: {correction}")
                    conn.commit()
            except Exception as e:
                print(f"   [!] Failed to reject corrected memory {mem.id}: {e}")
        self.store(correction, category=canonical_category, confidence=1.0, source="user_correction")
        return True

    def always_do(self, pattern: str, action: Optional[str] = None) -> int:
        """Store a preference with high confidence (e.g., 'always use Celsius')."""
        if action is None:
            content = pattern.strip()
            if not content:
                return -1
            return self.store(content, category="preference", confidence=1.0, source="user_explicit")

        normalized_pattern = pattern.strip()
        normalized_action = action.strip()
        if not normalized_pattern or not normalized_action:
            return -1
        content = f"Always: when '{normalized_pattern}' -> {normalized_action}"

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """SELECT id FROM memories
                           WHERE category = 'preference'
                           AND LOWER(content) LIKE LOWER(?)
                           ORDER BY updated_at DESC LIMIT 1""",
                        (f"%when '{normalized_pattern}'%",),
                    )
                    row = cursor.fetchone()
                    if row:
                        pref_id = int(row[0])
                        cursor.execute(
                            """UPDATE memories
                               SET content = ?, confidence = 1.0, source = ?, updated_at = ?
                               WHERE id = ?""",
                            (content, "user_explicit", datetime.now(), pref_id),
                        )
                        conn.commit()
                        return pref_id
            except Exception as e:
                print(f"   [!] Failed to upsert preference: {e}")

        return self.store(content, category="preference", confidence=1.0, source="user_explicit")

    # ==================== Schema Migration ====================

    def _run_migrations(self, conn: sqlite3.Connection):
        """Apply pending schema migrations."""
        cursor = conn.cursor()
        self._ensure_memories_columns(conn)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        current = row[0] if row and row[0] else 0

        if current < 2:
            self._migrate_v1_to_v2(conn)
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (2, datetime.now())
            )
            conn.commit()
            print("   [+] Memory schema migrated to v2")

    def _ensure_memories_columns(self, conn: sqlite3.Connection):
        """Add missing columns for legacy v1 tables created before schema v2."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(memories)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        column_migrations = [
            ("updated_at", "DATETIME"),
            ("last_accessed", "DATETIME"),
            ("access_count", "INTEGER DEFAULT 0"),
            ("embedding_id", "INTEGER"),
            ("source", "TEXT"),
        ]

        for column_name, column_def in column_migrations:
            if column_name not in existing_columns:
                conn.execute(f"ALTER TABLE memories ADD COLUMN {column_name} {column_def}")

        conn.execute(
            "UPDATE memories SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )

    def _migrate_v1_to_v2(self, conn: sqlite3.Connection):
        """Remap legacy categories to new category names. Non-destructive."""
        for old_cat, new_cat in self._CATEGORY_MIGRATION_MAP.items():
            conn.execute(
                "UPDATE memories SET category = ? WHERE category = ?",
                (new_cat, old_cat)
            )
        # Ensure rejected memories with confidence 0 are categorized
        conn.execute(
            "UPDATE memories SET category = 'rejected' WHERE confidence <= 0.0 AND category != 'rejected'"
        )
        conn.commit()

    def update_confidence(self, memory_id: int, new_confidence: float):
        """Update memory confidence score"""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute(
                        "UPDATE memories SET confidence = ?, updated_at = ? WHERE id = ?",
                        (max(0.0, min(1.0, new_confidence)), datetime.now(), memory_id)
                    )
                    conn.commit()
            except Exception as e:
                print(f"   [!] Failed to update memory confidence: {e}")

    def get_by_id(self, memory_id: int) -> Optional[Memory]:
        """Get a memory by ID."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
                row = cursor.fetchone()
                return self._row_to_memory(row) if row else None
        except Exception as e:
            print(f"   [!] Failed to get memory by id: {e}")
            return None

    def delete(self, memory_id: int):
        """Delete a memory by ID"""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                    conn.commit()
            except Exception as e:
                print(f"   [!] Failed to delete memory: {e}")

    def _update_access_count(self, memory_id: int):
        """Increment access count for a memory"""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """UPDATE memories
                       SET access_count = access_count + 1, last_accessed = ?
                       WHERE id = ?""",
                    (datetime.now(), memory_id)
                )
                conn.commit()
        except Exception:
            pass

    def _row_to_memory(self, row) -> Memory:
        """Convert database row to Memory object"""
        def get_val(key, default=None):
            try:
                return row[key]
            except (KeyError, IndexError):
                return default

        def parse_dt(value):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                normalized = value.replace(" ", "T")
                try:
                    return datetime.fromisoformat(normalized)
                except ValueError:
                    return None
            return None

        return Memory(
            id=get_val('id'),
            content=get_val('content'),
            category=get_val('category'),
            confidence=get_val('confidence'),
            created_at=parse_dt(get_val('created_at')),
            updated_at=parse_dt(get_val('updated_at')),
            access_count=get_val('access_count', 0),
            last_accessed=parse_dt(get_val('last_accessed')),
            source=get_val('source')
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM memories")
                total = cursor.fetchone()[0]
                cursor.execute("SELECT category, COUNT(*) FROM memories GROUP BY category")
                by_category = dict(cursor.fetchall())
                cursor.execute("SELECT AVG(confidence) FROM memories")
                avg_confidence = cursor.fetchone()[0] or 0.0
                return {
                    "total_memories": total,
                    "by_category": by_category,
                    "average_confidence": round(avg_confidence, 2)
                }
        except Exception as e:
            print(f"   [!] Failed to get memory stats: {e}")
            return {}

    def clear(self):
        """Clear all long-term memories"""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM memories")
                    conn.execute("DELETE FROM memory_keywords")
                    conn.execute("DELETE FROM memory_corrections")
                    try:
                        conn.execute("DELETE FROM entity_relationships")
                    except Exception:
                        pass
                    if self._vec:
                        try:
                            conn.execute("DELETE FROM memory_embeddings")
                        except Exception:
                            pass
                    conn.commit()
                print("   [X] Long-term memory cleared")
            except Exception as e:
                print(f"   [!] Failed to clear memory: {e}")
