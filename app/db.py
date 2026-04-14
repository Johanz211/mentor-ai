"""SQLite persistence for chat history and file metadata."""

import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mentor.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mentor TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS uploaded_files (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            size INTEGER,
            mentor TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_chat_mentor ON chat_messages(mentor);
        CREATE INDEX IF NOT EXISTS idx_files_mentor ON uploaded_files(mentor);
    """)
    conn.commit()
    conn.close()


# ── Chat Messages ──

def save_message(mentor: str, role: str, content: str):
    conn = _connect()
    conn.execute(
        "INSERT INTO chat_messages (mentor, role, content) VALUES (?, ?, ?)",
        (mentor, role, content),
    )
    conn.commit()
    conn.close()


def get_history(mentor: str, limit: int = 200) -> list[dict]:
    """Get chat history for a mentor. Returns all messages (oldest first)."""
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE mentor = ? ORDER BY id ASC LIMIT ?",
        (mentor, limit),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def get_recent_history(mentor: str, limit: int = 20) -> list[dict]:
    """Get the N most recent messages for LLM context (oldest first within window)."""
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content FROM ("
        "  SELECT id, role, content FROM chat_messages WHERE mentor = ? ORDER BY id DESC LIMIT ?"
        ") sub ORDER BY id ASC",
        (mentor, limit),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def clear_history(mentor: str):
    conn = _connect()
    conn.execute("DELETE FROM chat_messages WHERE mentor = ?", (mentor,))
    conn.commit()
    conn.close()


def get_message_count(mentor: str) -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM chat_messages WHERE mentor = ?", (mentor,)
    ).fetchone()
    conn.close()
    return row["cnt"]


# ── Uploaded Files ──

def save_file_meta(file_id: str, name: str, path: str, size: int, mentor: str):
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO uploaded_files (id, name, path, size, mentor) VALUES (?, ?, ?, ?, ?)",
        (file_id, name, path, size, mentor),
    )
    conn.commit()
    conn.close()


def get_files(mentor: str = "") -> list[dict]:
    conn = _connect()
    if mentor:
        rows = conn.execute(
            "SELECT id, name, path, size, mentor FROM uploaded_files WHERE mentor = ? ORDER BY created_at",
            (mentor,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, path, size, mentor FROM uploaded_files ORDER BY created_at"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_file_meta(file_id: str):
    conn = _connect()
    conn.execute("DELETE FROM uploaded_files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()


# Initialize on import
init_db()
