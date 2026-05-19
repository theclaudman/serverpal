from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import bcrypt
from cryptography.fernet import Fernet


DEFAULT_PROMPTS = [
    ("chat", "Чат-ассистент", ""),
    ("digest", "Дайджест", ""),
    ("ask", "Вопрос по данным", ""),
]


FernetFactory = Callable[[], Fernet]
Migration = tuple[str, Callable[[sqlite3.Connection, FernetFactory], None]]


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def _drop_column_if_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> None:
    if column_name in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")


def _migration_001_initial_dashboard_schema(conn: sqlite3.Connection, fernet_factory: FernetFactory) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    UNIQUE NOT NULL,
            password_hash   TEXT    NOT NULL DEFAULT '',
            onec_password   TEXT    NOT NULL DEFAULT '',
            onec_base_url   TEXT    NOT NULL DEFAULT ''
        )
        """
    )

    columns = _table_columns(conn, "users")
    old_password_column_exists = "password" in columns and "password_hash" not in columns

    _ensure_column(conn, "users", "password_hash", "password_hash TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "users", "onec_password", "onec_password TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "users", "onec_base_url", "onec_base_url TEXT NOT NULL DEFAULT ''")

    if old_password_column_exists:
        fernet = fernet_factory()
        rows = conn.execute("SELECT id, password FROM users").fetchall()
        for row in rows:
            password = row["password"]
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            encrypted_password = fernet.encrypt(password.encode()).decode()
            conn.execute(
                "UPDATE users SET password_hash = ?, onec_password = ? WHERE id = ?",
                (password_hash, encrypted_password, row["id"]),
            )

    _drop_column_if_exists(conn, "users", "password")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompts (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            content     TEXT NOT NULL DEFAULT '',
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id   TEXT NOT NULL,
            name        TEXT NOT NULL,
            content     TEXT NOT NULL DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    for prompt_id, name, content in DEFAULT_PROMPTS:
        conn.execute(
            "INSERT OR IGNORE INTO prompts (id, name, content) VALUES (?, ?, ?)",
            (prompt_id, name, content),
        )


def _migration_002_user_price_types(conn: sqlite3.Connection, fernet_factory: FernetFactory) -> None:
    _ensure_column(conn, "users", "price_type_retail", "price_type_retail TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "users", "price_type_wholesale", "price_type_wholesale TEXT NOT NULL DEFAULT ''")


def _migration_003_digest_history(conn: sqlite3.Connection, fernet_factory: FernetFactory) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS digest_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            digest_date TEXT NOT NULL DEFAULT '',
            provider    TEXT NOT NULL DEFAULT '',
            meta_json   TEXT NOT NULL DEFAULT '{}',
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_digest_messages_user_created
        ON digest_messages (username, created_at, id)
        """
    )


def _migration_004_digest_model_settings(conn: sqlite3.Connection, fernet_factory: FernetFactory) -> None:
    _ensure_column(conn, "users", "digest_provider", "digest_provider TEXT NOT NULL DEFAULT 'lmstudio'")
    _ensure_column(conn, "users", "digest_model", "digest_model TEXT NOT NULL DEFAULT ''")


def _migration_005_chat_history(conn: sqlite3.Connection, fernet_factory: FernetFactory) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            channel     TEXT NOT NULL DEFAULT 'chat',
            meta_json   TEXT NOT NULL DEFAULT '{}',
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created
        ON chat_messages (username, created_at, id)
        """
    )


MIGRATIONS: list[Migration] = [
    ("001_initial_dashboard_schema", _migration_001_initial_dashboard_schema),
    ("002_user_price_types", _migration_002_user_price_types),
    ("003_digest_history", _migration_003_digest_history),
    ("004_digest_model_settings", _migration_004_digest_model_settings),
    ("005_chat_history", _migration_005_chat_history),
]


def run_migrations(db_path: Path, fernet_factory: FernetFactory) -> list[str]:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    applied_now: list[str] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     TEXT PRIMARY KEY,
                applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

        for version, migrate in MIGRATIONS:
            if version in applied:
                continue
            migrate(conn, fernet_factory)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            applied_now.append(version)

    return applied_now
