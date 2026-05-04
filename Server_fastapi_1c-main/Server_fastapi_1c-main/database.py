import sqlite3
import bcrypt
from pathlib import Path
from cryptography.fernet import Fernet
from config import settings

DB_PATH = Path("users.db")


def _fernet() -> Fernet:
    """Инициализирует Fernet из ключа в конфиге."""
    if not settings.encryption_key:
        raise RuntimeError("ENCRYPTION_KEY не задан в .env")
    return Fernet(settings.encryption_key.encode())


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT    UNIQUE NOT NULL,
                password_hash   TEXT    NOT NULL,
                onec_password   TEXT    NOT NULL DEFAULT '',
                onec_base_url   TEXT    NOT NULL DEFAULT ''
            )
        """)

        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]

        # Миграция: старая схема с полем password → новая с password_hash + onec_password
        if "password" in columns and "password_hash" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE users ADD COLUMN onec_password TEXT NOT NULL DEFAULT ''")

            # Мигрируем существующих пользователей
            rows = conn.execute("SELECT id, password FROM users").fetchall()
            f = _fernet()
            for row in rows:
                pw = row["password"]
                hashed = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
                encrypted = f.encrypt(pw.encode()).decode()
                conn.execute(
                    "UPDATE users SET password_hash = ?, onec_password = ? WHERE id = ?",
                    (hashed, encrypted, row["id"]),
                )

            # Удаляем старую колонку
            conn.execute("ALTER TABLE users DROP COLUMN password")


def get_user(username: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, password_hash, onec_password, onec_base_url FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    return dict(row)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Проверяет пароль против bcrypt-хэша."""
    return bcrypt.checkpw(plain_password.encode(), password_hash.encode())


def decrypt_onec_password(encrypted_password: str) -> str:
    """Расшифровывает пароль 1С для отправки в Basic Auth."""
    return _fernet().decrypt(encrypted_password.encode()).decode()


def username_exists(username: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row is not None


def create_user(username: str, password: str, onec_base_url: str) -> None:
    """Сохраняет пользователя: пароль хэшируется + шифруется."""
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    encrypted = _fernet().encrypt(password.encode()).decode()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, onec_password, onec_base_url) VALUES (?, ?, ?, ?)",
            (username, hashed, encrypted, onec_base_url),
        )