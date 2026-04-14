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

        CREATE TABLE IF NOT EXISTS flashcards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mentor TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            difficulty TEXT DEFAULT 'new',
            ease_factor REAL DEFAULT 2.5,
            interval INTEGER DEFAULT 0,
            repetitions INTEGER DEFAULT 0,
            next_review TEXT DEFAULT (datetime('now')),
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_fc_mentor ON flashcards(mentor);
        CREATE INDEX IF NOT EXISTS idx_fc_review ON flashcards(next_review);

        CREATE TABLE IF NOT EXISTS fc_auto_cursor (
            mentor TEXT PRIMARY KEY,
            last_msg_id INTEGER DEFAULT 0,
            last_run TEXT DEFAULT (datetime('now'))
        );
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


# ── Flashcards ──

def add_flashcard(mentor: str, question: str, answer: str) -> int:
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO flashcards (mentor, question, answer) VALUES (?, ?, ?)",
        (mentor, question, answer),
    )
    card_id = cur.lastrowid
    conn.commit()
    conn.close()
    return card_id


def get_flashcards(mentor: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, question, answer, difficulty, ease_factor, interval, repetitions, next_review, created_at "
        "FROM flashcards WHERE mentor = ? ORDER BY created_at DESC",
        (mentor,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_due_flashcards(mentor: str, limit: int = 20) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, question, answer, difficulty, ease_factor, interval, repetitions "
        "FROM flashcards WHERE mentor = ? AND next_review <= datetime('now') "
        "ORDER BY next_review ASC LIMIT ?",
        (mentor, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def review_flashcard(card_id: int, quality: int):
    """SM-2 spaced repetition. quality: 0=again, 1=hard, 2=good, 3=easy."""
    conn = _connect()
    row = conn.execute(
        "SELECT ease_factor, interval, repetitions FROM flashcards WHERE id = ?",
        (card_id,),
    ).fetchone()
    if not row:
        conn.close()
        return

    ef = row["ease_factor"]
    interval = row["interval"]
    reps = row["repetitions"]

    if quality < 1:  # again
        reps = 0
        interval = 0
        difficulty = "again"
    else:
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = round(interval * ef)

        ef = ef + (0.1 - (3 - quality) * (0.08 + (3 - quality) * 0.02))
        ef = max(1.3, ef)
        reps += 1

        if quality == 1:
            difficulty = "hard"
        elif quality == 2:
            difficulty = "good"
        else:
            difficulty = "easy"

    conn.execute(
        "UPDATE flashcards SET ease_factor=?, interval=?, repetitions=?, difficulty=?, "
        "next_review=datetime('now', '+' || ? || ' days') WHERE id=?",
        (ef, interval, reps, difficulty, interval, card_id),
    )
    conn.commit()
    conn.close()


def delete_flashcard(card_id: int):
    conn = _connect()
    conn.execute("DELETE FROM flashcards WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()


def get_flashcard_stats(mentor: str) -> dict:
    conn = _connect()
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM flashcards WHERE mentor = ?", (mentor,)
    ).fetchone()["cnt"]
    due = conn.execute(
        "SELECT COUNT(*) as cnt FROM flashcards WHERE mentor = ? AND next_review <= datetime('now')",
        (mentor,),
    ).fetchone()["cnt"]
    mastered = conn.execute(
        "SELECT COUNT(*) as cnt FROM flashcards WHERE mentor = ? AND repetitions >= 5",
        (mentor,),
    ).fetchone()["cnt"]
    conn.close()
    return {"total": total, "due": due, "mastered": mastered}


# ── Auto Flashcard Cursor ──

def get_fc_cursor(mentor: str) -> int:
    """Get the last message ID processed for auto flashcard generation."""
    conn = _connect()
    row = conn.execute(
        "SELECT last_msg_id FROM fc_auto_cursor WHERE mentor = ?", (mentor,)
    ).fetchone()
    conn.close()
    return row["last_msg_id"] if row else 0


def set_fc_cursor(mentor: str, last_msg_id: int):
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO fc_auto_cursor (mentor, last_msg_id, last_run) "
        "VALUES (?, ?, datetime('now'))",
        (mentor, last_msg_id),
    )
    conn.commit()
    conn.close()


def get_new_messages(mentor: str, since_id: int, limit: int = 40) -> tuple[list[dict], int]:
    """Get messages newer than since_id. Returns (messages, max_id)."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, role, content FROM chat_messages "
        "WHERE mentor = ? AND id > ? ORDER BY id ASC LIMIT ?",
        (mentor, since_id, limit),
    ).fetchall()
    conn.close()
    if not rows:
        return [], since_id
    messages = [{"role": r["role"], "content": r["content"]} for r in rows]
    max_id = rows[-1]["id"]
    return messages, max_id


def get_all_mentors_with_messages() -> list[str]:
    """Return mentor keys that have at least one message."""
    conn = _connect()
    rows = conn.execute(
        "SELECT DISTINCT mentor FROM chat_messages"
    ).fetchall()
    conn.close()
    return [r["mentor"] for r in rows]


# Initialize on import
init_db()
