"""
core/memory.py — SQLite persistent memory for JARVIS

Tables: conversations, preferences, learned_patterns,
        app_usage, file_cache, knowledge_base
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from utils.helpers import get_config
from utils.logger import get_logger

log = get_logger("memory")


class Memory:
    """
    Persistent SQLite memory store for JARVIS.

    Handles conversation history, user preferences, app usage
    statistics, file indexing, and a general knowledge base.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize the memory database.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to config value or 'data/jarvis_memory.db'.
        """
        config = get_config()
        if db_path is None:
            db_path = config.get("system", {}).get("memory_db", "data/jarvis_memory.db")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        log.info("Memory initialized at %s", self.db_path)

    # ─── Schema ───────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        """Create tables if they do not exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                timestamp   REAL NOT NULL,
                session_id  TEXT
            );

            CREATE TABLE IF NOT EXISTS preferences (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS learned_patterns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger     TEXT NOT NULL,
                response    TEXT NOT NULL,
                confidence  REAL DEFAULT 1.0,
                hits        INTEGER DEFAULT 1,
                last_seen   REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_usage (
                name        TEXT PRIMARY KEY,
                path        TEXT,
                launch_count INTEGER DEFAULT 1,
                last_used   REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS file_cache (
                path        TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                extension   TEXT,
                size_bytes  INTEGER,
                modified_at REAL,
                indexed_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_base (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic       TEXT NOT NULL,
                content     TEXT NOT NULL,
                source      TEXT,
                created_at  REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_conv_ts ON conversations(timestamp);
            CREATE INDEX IF NOT EXISTS idx_conv_role ON conversations(role);
            CREATE INDEX IF NOT EXISTS idx_file_name ON file_cache(name);
            CREATE INDEX IF NOT EXISTS idx_file_ext ON file_cache(extension);
            CREATE INDEX IF NOT EXISTS idx_kb_topic ON knowledge_base(topic);
        """)
        self._conn.commit()

    # ─── Conversations ────────────────────────────────────────────────────

    def add_message(
        self,
        role: str,
        content: str,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Persist a conversation message.

        Args:
            role: 'user' or 'assistant'.
            content: Message text.
            session_id: Optional session identifier.
        """
        self._conn.execute(
            "INSERT INTO conversations (role, content, timestamp, session_id) VALUES (?,?,?,?)",
            (role, content, time.time(), session_id),
        )
        self._conn.commit()

    def get_recent_messages(
        self,
        limit: int = 20,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Retrieve recent conversation messages.

        Args:
            limit: Maximum number of messages to return.
            session_id: Filter by session (optional).

        Returns:
            List of dicts with keys: role, content, timestamp.
        """
        if session_id:
            rows = self._conn.execute(
                "SELECT role, content, timestamp FROM conversations "
                "WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT role, content, timestamp FROM conversations "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def search_conversations(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search conversation history for messages containing *query*.

        Args:
            query: Search string.
            limit: Max results.

        Returns:
            List of matching conversation records.
        """
        rows = self._conn.execute(
            "SELECT role, content, timestamp FROM conversations "
            "WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_old_conversations(self, days: int = 30) -> int:
        """
        Delete conversations older than *days*.

        Args:
            days: Age threshold.

        Returns:
            Number of rows deleted.
        """
        cutoff = time.time() - days * 86400
        cur = self._conn.execute(
            "DELETE FROM conversations WHERE timestamp < ?", (cutoff,)
        )
        self._conn.commit()
        deleted = cur.rowcount
        log.info("Cleared %d old conversation entries", deleted)
        return deleted

    # ─── Preferences ──────────────────────────────────────────────────────

    def set_preference(self, key: str, value: Any) -> None:
        """
        Store a user preference.

        Args:
            key: Preference key.
            value: Any JSON-serialisable value.
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES (?,?,?)",
            (key, json.dumps(value), time.time()),
        )
        self._conn.commit()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a user preference.

        Args:
            key: Preference key.
            default: Value if key not found.

        Returns:
            Stored value or *default*.
        """
        row = self._conn.execute(
            "SELECT value FROM preferences WHERE key=?", (key,)
        ).fetchone()
        if row:
            return json.loads(row["value"])
        return default

    def all_preferences(self) -> dict:
        """Return all preferences as a dict."""
        rows = self._conn.execute("SELECT key, value FROM preferences").fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    # ─── Learned Patterns ─────────────────────────────────────────────────

    def learn_pattern(self, trigger: str, response: str) -> None:
        """
        Record a command/response pattern for future use.

        Args:
            trigger: User input that triggered the action.
            response: The response or action taken.
        """
        existing = self._conn.execute(
            "SELECT id, hits FROM learned_patterns WHERE trigger=?", (trigger,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE learned_patterns SET hits=hits+1, last_seen=? WHERE id=?",
                (time.time(), existing["id"]),
            )
        else:
            self._conn.execute(
                "INSERT INTO learned_patterns (trigger, response, last_seen) VALUES (?,?,?)",
                (trigger, response, time.time()),
            )
        self._conn.commit()

    def find_pattern(self, trigger: str) -> Optional[str]:
        """
        Look up a learned pattern for the given trigger.

        Args:
            trigger: User input.

        Returns:
            Best matching response or None.
        """
        rows = self._conn.execute(
            "SELECT response FROM learned_patterns "
            "WHERE trigger LIKE ? ORDER BY hits DESC LIMIT 1",
            (f"%{trigger}%",),
        ).fetchall()
        return rows[0]["response"] if rows else None

    # ─── App Usage ────────────────────────────────────────────────────────

    def record_app_launch(self, name: str, path: str = "") -> None:
        """
        Record that an application was launched.

        Args:
            name: Application name.
            path: Executable path (optional).
        """
        existing = self._conn.execute(
            "SELECT name FROM app_usage WHERE name=?", (name,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE app_usage SET launch_count=launch_count+1, last_used=?, path=? WHERE name=?",
                (time.time(), path or "", name),
            )
        else:
            self._conn.execute(
                "INSERT INTO app_usage (name, path, last_used) VALUES (?,?,?)",
                (name, path, time.time()),
            )
        self._conn.commit()

    def get_top_apps(self, limit: int = 10) -> list[dict]:
        """
        Return the most-frequently-launched applications.

        Args:
            limit: Max number of results.

        Returns:
            List of dicts with name, path, launch_count, last_used.
        """
        rows = self._conn.execute(
            "SELECT name, path, launch_count, last_used FROM app_usage "
            "ORDER BY launch_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── File Cache ───────────────────────────────────────────────────────

    def index_file(
        self,
        path: str,
        name: str,
        extension: str,
        size_bytes: int,
        modified_at: float,
    ) -> None:
        """
        Add or update a file entry in the index.

        Args:
            path: Absolute file path.
            name: File name.
            extension: File extension (e.g. '.pdf').
            size_bytes: File size.
            modified_at: File modification timestamp.
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO file_cache "
            "(path, name, extension, size_bytes, modified_at, indexed_at) "
            "VALUES (?,?,?,?,?,?)",
            (path, name, extension, size_bytes, modified_at, time.time()),
        )
        self._conn.commit()

    def search_files(
        self,
        query: str,
        extension: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Search the file index.

        Args:
            query: Name substring to search for.
            extension: Optional extension filter (e.g. '.pdf').
            limit: Max results.

        Returns:
            List of file records.
        """
        if extension:
            rows = self._conn.execute(
                "SELECT path, name, extension, size_bytes, modified_at FROM file_cache "
                "WHERE name LIKE ? AND extension=? LIMIT ?",
                (f"%{query}%", extension, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT path, name, extension, size_bytes, modified_at FROM file_cache "
                "WHERE name LIKE ? LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── Knowledge Base ───────────────────────────────────────────────────

    def store_knowledge(self, topic: str, content: str, source: str = "") -> None:
        """
        Store a fact in the knowledge base.

        Args:
            topic: Topical tag / category.
            content: The knowledge content.
            source: Where the information came from.
        """
        self._conn.execute(
            "INSERT INTO knowledge_base (topic, content, source, created_at) VALUES (?,?,?,?)",
            (topic, content, source, time.time()),
        )
        self._conn.commit()

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """
        Search the knowledge base for relevant entries.

        Args:
            query: Search terms.
            limit: Max results.

        Returns:
            List of knowledge records.
        """
        rows = self._conn.execute(
            "SELECT topic, content, source, created_at FROM knowledge_base "
            "WHERE topic LIKE ? OR content LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Cleanup ──────────────────────────────────────────────────────────

    def vacuum(self) -> None:
        """Run SQLite VACUUM to reclaim disk space."""
        self._conn.execute("VACUUM")
        self._conn.commit()
        log.info("Memory database vacuumed.")

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
