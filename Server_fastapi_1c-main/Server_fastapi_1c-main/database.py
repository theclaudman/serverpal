import sqlite3
import bcrypt
import json
from pathlib import Path
from cryptography.fernet import Fernet
from config import settings
from migrations import run_migrations

DB_PATH = Path(settings.dashboard_db_path)


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
    run_migrations(DB_PATH, _fernet)


def get_user(username: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT username, password_hash, onec_password, onec_base_url,
                   price_type_retail, price_type_wholesale,
                   digest_provider, digest_model
            FROM users
            WHERE username = ?
            """,
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


def create_user(
    username: str,
    password: str,
    onec_base_url: str,
    price_type_retail: str = "",
    price_type_wholesale: str = "",
) -> None:
    """Сохраняет пользователя: пароль хэшируется + шифруется."""
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    encrypted = _fernet().encrypt(password.encode()).decode()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                username, password_hash, onec_password, onec_base_url,
                price_type_retail, price_type_wholesale
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, hashed, encrypted, onec_base_url, price_type_retail, price_type_wholesale),
        )


def update_user_price_types(username: str, price_type_retail: str, price_type_wholesale: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET price_type_retail = ?, price_type_wholesale = ?
            WHERE username = ?
            """,
            (price_type_retail, price_type_wholesale, username),
        )


def update_user_digest_settings(username: str, digest_provider: str, digest_model: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET digest_provider = ?, digest_model = ?
            WHERE username = ?
            """,
            (digest_provider, digest_model, username),
        )


def clear_digest_history(username: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM digest_messages WHERE username = ?", (username,))


def add_digest_message(
    username: str,
    role: str,
    content: str,
    digest_date: str = "",
    provider: str = "",
    meta: dict | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO digest_messages (
                username, role, content, digest_date, provider, meta_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                role,
                content,
                digest_date or "",
                provider or "",
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )


def get_digest_history(username: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, digest_date, provider, meta_json, created_at
            FROM digest_messages
            WHERE username = ?
            ORDER BY created_at ASC, id ASC
            """,
            (username,),
        ).fetchall()

    messages = []
    for row in rows:
        item = dict(row)
        try:
            item["meta"] = json.loads(item.pop("meta_json") or "{}")
        except json.JSONDecodeError:
            item["meta"] = {}
        messages.append(item)
    return messages
