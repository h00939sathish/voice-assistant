"""
Long-Term Memory System - Persistent semantic memory with vector search

Provides:
- Vector storage for memories using sqlite-vec
- Semantic search through memories (not just keyword)
- Contextual recall based on current conversation
- Memory confidence scoring
- User corrections support

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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import re

# Import config if available
try:
    from config import MEMORY_DB_PATH
except ImportError:
    MEMORY_DB_PATH = "data/memory.db"

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


class LongTermMemory:
    """
    Persistent long-term memory with semantic search capabilities.
    Uses sqlite-vec for vector storage and similarity search.
    """

    # Categories for different memory types
    CATEGORIES = {
        "personal": "Personal facts about the user (name, age, location, work)",
        "preference": "User preferences and likes/dislikes",
        "habit": "Regular behaviors and routines",
        "context": "Current activities and projects",
        "relationship": "People, pets, and relationships",
        "goal": "Goals, plans, and aspirations",
        "event": "Important past events",
        "correction": "User corrections to previous memories",
    }

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize long-term memory.

        Args:
            storage_path: Path to DB file. Defaults to MEMORY_DB_PATH from config
        """
        if storage_path is None:
            base_dir = Path(__file__).parent.parent
            storage_path = base_dir / MEMORY_DB_PATH

        self.db_path = Path(storage_path)
        self._lock = threading.Lock()
        self._vec = None  # sqlite-vec extension

        # Ensure directory exists
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

        # Load sqlite-vec extension if available
        try:
            conn.enable_load_extension(True)
            # Try different possible names for sqlite-vec
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

                    # Main memories table
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

                    # Create virtual table for vector search if sqlite-vec is available
                    if self._vec:
                        try:
                            cursor.execute("""
                                CREATE VIRTUAL TABLE IF NOT EXISTS memory_embeddings USING vec0(
                                    embedding float[384]
                                )
                            """)
                        except Exception:
                            self._vec = False

                    # Fallback: simple keyword index if no vector support
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS memory_keywords (
                            memory_id INTEGER,
                            keyword TEXT,
                            PRIMARY KEY (memory_id, keyword),
                            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
                        )
                    """)

                    # Memory corrections table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS memory_corrections (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            memory_id INTEGER,
                            correction TEXT NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
                        )
                    """)

                    # Create indexes
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_category ON memories(category)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_confidence ON memories(confidence)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_accessed ON memories(last_accessed)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords ON memory_keywords(keyword)")

                    conn.commit()
            except Exception as e:
                print(f"   [!] Long-term Memory DB Init Error: {e}")

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for text.
        Priorities:
        1. SentenceTransformers (Fastest, Local)
        2. Ollama (nomic-embed-text or all-minilm)
        3. Fallback Hash (Low quality)
        """
        # 1. Try Sentence Transformers
        try:
            from sentence_transformers import SentenceTransformer
            if not hasattr(self, '_embedding_model'):
                # Load once
                print("   🔄 Loading embedding model (all-MiniLM-L6-v2)...")
                self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            
            return self._embedding_model.encode(text).tolist()
        except ImportError:
            pass # Not installed
        except Exception as e:
            print(f"   [!] SentenceTransformers error: {e}")

        # 2. Try Ollama (if available)
        try:
            import ollama
            # Check for nomic-embed-text or similar
            response = ollama.embeddings(model='all-minilm', prompt=text)
            if 'embedding' in response:
                return response['embedding']
        except Exception:
            pass

        # 3. Fallback: use simple hashing-based pseudo-embedding
        # Not as good but allows basic similarity
        return self._simple_hash_embedding(text)

    def _simple_hash_embedding(self, text: str, dim: int = 384) -> List[float]:
        """Simple hashing-based embedding for fallback"""
        # Normalize text
        text = text.lower().strip()
        words = re.findall(r'\b\w+\b', text)

        # Create simple bag-of-words vector
        vector = [0.0] * dim
        for word in words:
            hash_val = int(hashlib.md5(word.encode()).hexdigest(), 16)
            idx = hash_val % dim
            vector[idx] += 1.0

        # Normalize
        magnitude = sum(x**2 for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]

        return vector

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for indexing"""
        # Simple keyword extraction
        words = re.findall(r'\b\w+\b', text.lower())
        # Filter common stop words
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

    def store(self, content: str, category: str = "general", confidence: float = 1.0,
              source: str = None) -> int:
        """
        Store a new memory.

        Args:
            content: The memory content
            category: Memory category (personal, preference, habit, etc.)
            confidence: Confidence score (0.0-1.0)
            source: Source of the memory (e.g., "extraction", "user_input")

        Returns:
            Memory ID
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Insert memory
                    cursor.execute(
                        """INSERT INTO memories (content, category, confidence, source, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (content, category, confidence, source, datetime.now())
                    )
                    memory_id = cursor.lastrowid

                    # Store keywords for text search
                    keywords = self._extract_keywords(content)
                    for keyword in keywords:
                        cursor.execute(
                            "INSERT OR IGNORE INTO memory_keywords (memory_id, keyword) VALUES (?, ?)",
                            (memory_id, keyword)
                        )

                    # Store vector embedding if available
                    if self._vec:
                        try:
                            embedding = self._generate_embedding(content)
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
               min_confidence: float = 0.5) -> List[Memory]:
        """
        Search memories by semantic similarity to query.

        Args:
            query: Search query
            category: Optional category filter
            limit: Maximum results
            min_confidence: Minimum confidence threshold

        Returns:
            List of Memory objects
        """
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                memories = []

                # Try vector search first if available
                if self._vec:
                    try:
                        query_embedding = self._generate_embedding(query)
                        if query_embedding:
                            # Use sqlite-vec for similarity search
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
                                    if category and mem_row['category'] != category:
                                        continue
                                    memories.append(self._row_to_memory(mem_row))
                    except Exception:
                        pass

                # Fallback: keyword search
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

                        if category:
                            query_sql += " AND m.category = ?"
                            params.append(category)

                        query_sql += """
                            GROUP BY m.id
                            ORDER BY match_count DESC, m.access_count DESC
                            LIMIT ?
                        """
                        params.append(limit)

                        cursor.execute(query_sql, params)

                        for row in cursor.fetchall():
                            mem = self._row_to_memory(row)
                            if mem.id not in [m.id for m in memories]:
                                memories.append(mem)

                # Update access counts
                for mem in memories[:limit]:
                    self._update_access_count(mem.id)

                return memories[:limit]

        except Exception as e:
            print(f"   [!] Memory search error: {e}")
            return []

    def recall_context(self, current_conversation: str, limit: int = 3) -> List[str]:
        """
        Recall relevant memories based on current conversation context.

        Args:
            current_conversation: Current conversation text
            limit: Maximum memories to recall

        Returns:
            List of memory content strings
        """
        memories = self.search(current_conversation, limit=limit)
        return [m.content for m in memories if m.confidence >= 0.7]

    def get_all_by_category(self, category: str) -> List[Memory]:
        """Get all memories of a specific category"""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """SELECT * FROM memories
                       WHERE category = ?
                       ORDER BY confidence DESC, updated_at DESC""",
                    (category,)
                )
                return [self._row_to_memory(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"   [!] Failed to get memories by category: {e}")
            return []

    def get_facts_for_prompt(self) -> str:
        """Get formatted facts string for system prompt injection"""
        facts = []

        # Get high-confidence personal facts
        personal = self.get_all_by_category("personal")
        facts.extend([f"Personal: {m.content}" for m in personal if m.confidence >= 0.8][:5])

        # Get preferences
        preferences = self.get_all_by_category("preference")
        facts.extend([f"Preference: {m.content}" for m in preferences if m.confidence >= 0.8][:5])

        # Get relationships
        relationships = self.get_all_by_category("relationship")
        facts.extend([f"Relationship: {m.content}" for m in relationships if m.confidence >= 0.8][:5])

        # Get habits
        habits = self.get_all_by_category("habit")
        facts.extend([f"Habit: {m.content}" for m in habits if m.confidence >= 0.7][:3])

        if facts:
            return "\n".join(facts)
        return ""

    def correct_memory(self, memory_id: int, correction: str):
        """
        Record a user correction for a memory.
        This reduces confidence of the original and stores the correction.
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    # Reduce confidence of original memory
                    conn.execute(
                        "UPDATE memories SET confidence = confidence * 0.5, updated_at = ? WHERE id = ?",
                        (datetime.now(), memory_id)
                    )

                    # Store correction
                    conn.execute(
                        "INSERT INTO memory_corrections (memory_id, correction) VALUES (?, ?)",
                        (memory_id, correction)
                    )

                    conn.commit()
                    print("   [+] Memory corrected")
            except Exception as e:
                print(f"   [!] Failed to correct memory: {e}")

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
        # Handle sqlite3.Row which doesn't have .get() method
        def get_val(key, default=None):
            try:
                return row[key]
            except (KeyError, IndexError):
                return default

        return Memory(
            id=get_val('id'),
            content=get_val('content'),
            category=get_val('category'),
            confidence=get_val('confidence'),
            created_at=get_val('created_at') if isinstance(get_val('created_at'), datetime) else None,
            updated_at=get_val('updated_at') if isinstance(get_val('updated_at'), datetime) else None,
            access_count=get_val('access_count', 0),
            last_accessed=get_val('last_accessed')
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Total memories
                cursor.execute("SELECT COUNT(*) FROM memories")
                total = cursor.fetchone()[0]

                # By category
                cursor.execute("SELECT category, COUNT(*) FROM memories GROUP BY category")
                by_category = dict(cursor.fetchall())

                # Average confidence
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
                    if self._vec:
                        try:
                            conn.execute("DELETE FROM memory_embeddings")
                        except Exception:
                            pass
                    conn.commit()
                print("   [X] Long-term memory cleared")
            except Exception as e:
                print(f"   [!] Failed to clear memory: {e}")
