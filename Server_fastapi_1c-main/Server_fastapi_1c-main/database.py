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

def get_templates(prompt_id: str) -> list[dict]:
    """Возвращает все шаблоны для промпта."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, prompt_id, name, content, created_at FROM prompt_templates WHERE prompt_id = ? ORDER BY created_at DESC",
            (prompt_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_template(prompt_id: str, name: str, content: str) -> int:
    """Создаёт новый шаблон. Возвращает id."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO prompt_templates (prompt_id, name, content) VALUES (?, ?, ?)",
            (prompt_id, name, content),
        )
    return cursor.lastrowid


def delete_template(template_id: int) -> None:
    """Удаляет шаблон."""
    with get_connection() as conn:
        conn.execute("DELETE FROM prompt_templates WHERE id = ?", (template_id,))
        
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_all_prompts() -> list[dict]:
    """Возвращает все промпты."""
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name, content, updated_at FROM prompts ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def get_prompt(prompt_id: str) -> dict | None:
    """Возвращает один промпт по id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, content, updated_at FROM prompts WHERE id = ?",
            (prompt_id,),
        ).fetchone()
    return dict(row) if row else None


def update_prompt(prompt_id: str, content: str) -> None:
    """Обновляет текст промпта."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE prompts SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (content, prompt_id),
        )



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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_templates (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id   TEXT NOT NULL,
                name        TEXT NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        default_prompts = [
            ("chat", "Чат-ассистент", ""),
            ("digest", "Дайджест", ""),
            ("ask", "Вопрос по данным", ""),
        ]
        for pid, name, content in default_prompts:
            conn.execute(
                "INSERT OR IGNORE INTO prompts (id, name, content) VALUES (?, ?, ?)",
                (pid, name, content),
            )


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