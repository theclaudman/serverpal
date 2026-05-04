# database.py

import sqlite3
from pathlib import Path

DB_PATH = Path("users.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password      TEXT    NOT NULL,
                onec_base_url TEXT    NOT NULL DEFAULT ''
            )
        """)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]

        # Миграция: добавляем новое объединённое поле
        if "onec_base_url" not in columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN onec_base_url TEXT NOT NULL DEFAULT ''"
            )
            columns.append("onec_base_url")

        # Миграция: заполняем onec_base_url из старых полей и удаляем их
        if "server_ip" in columns and "onec_publication" in columns:
            conn.execute("""
                UPDATE users
                SET onec_base_url = 'http://' || server_ip || '/' || onec_publication
                WHERE onec_base_url = ''
            """)
            conn.execute("ALTER TABLE users DROP COLUMN server_ip")
            conn.execute("ALTER TABLE users DROP COLUMN onec_publication")


def get_user(username: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, password, onec_base_url FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def username_exists(username: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row is not None


def create_user(username: str, password: str, onec_base_url: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (username, password, onec_base_url) VALUES (?, ?, ?)",
            (username, password, onec_base_url),
        )
