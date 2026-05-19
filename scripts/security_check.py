from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_python(name: str, cwd: Path, code: str) -> None:
    print(f"\n== {name} ==")
    result = subprocess.run([sys.executable, "-c", code], cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    run_python(
        "ai bridge auth routes",
        ROOT / "server_ai-main" / "server_ai-main",
        r'''
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
credentials = {"login": "user", "password": "pass", "ip": "127.0.0.1/unf"}

assert client.get("/health").status_code == 200
assert client.post("/chat/", json={"credentials": credentials, "prompt": "hi"}).status_code == 403
assert client.post("/query/", json={"credentials": credentials, "query_text": "SELECT 1"}).status_code == 403
assert client.post("/report/daily", json={"credentials": credentials, "data": {}}).status_code == 403
assert client.post("/report/weekly", json={"credentials": credentials, "data": {}}).status_code == 403
print("ok")
''',
    )

    run_python(
        "digest auth routes",
        ROOT / "server_digest_ai-main" / "server_digest_ai-main",
        r'''
from fastapi.testclient import TestClient
import server

client = TestClient(server.app)
credentials = {"base_url": "http://127.0.0.1/unf/odata/standard.odata", "login": "user", "password": "pass"}

assert client.get("/health").status_code == 200
assert client.get("/api/providers").status_code == 403
assert client.post("/api/digest", json={"credentials": credentials, "provider": "lmstudio"}).status_code == 403
assert client.post("/api/ask", json={"credentials": credentials, "question": "hi", "provider": "lmstudio"}).status_code == 403
print("ok")
''',
    )

    run_python(
        "dashboard registration guard",
        ROOT / "Server_fastapi_1c-main" / "Server_fastapi_1c-main",
        r'''
from fastapi.testclient import TestClient
import main

main.settings.registration_enabled = False
main.settings.registration_token = ""

client = TestClient(main.app, follow_redirects=False)

login_html = client.get("/login").text
assert "/register" not in login_html

response = client.get("/register")
assert response.status_code == 302
assert response.headers["location"] == "/login"

response = client.post("/register", data={"onec_base_url": "http://127.0.0.1/unf", "username": "user", "password": "pass"})
assert response.status_code == 403
assert client.get("/admin/developer").status_code == 302
assert client.get("/api/admin/overview").status_code == 401

main.settings.admin_usernames = "devadmin"
main.settings.admin_password = "strong-admin-password"
assert client.post("/admin/login", data={"username": "devadmin", "password": "wrong"}).status_code == 401
response = client.post("/admin/login", data={"username": "devadmin", "password": "strong-admin-password"})
assert response.status_code == 302
assert response.headers["location"] == "/admin/developer"
assert client.get("/admin/developer").status_code == 200
assert client.get("/api/admin/overview").status_code == 200
print("ok")
''',
    )

    run_python(
        "dashboard db migrations",
        ROOT / "Server_fastapi_1c-main" / "Server_fastapi_1c-main",
        r'''
import sqlite3
import uuid
from pathlib import Path

import bcrypt
from cryptography.fernet import Fernet

from migrations import run_migrations

tmpdir = Path(r''' + repr(str(ROOT)) + r''') / ".smoke-logs" / f"security-db-{uuid.uuid4().hex}"
tmpdir.mkdir(parents=True, exist_ok=False)
db_path = tmpdir / "users.db"
fernet = Fernet(Fernet.generate_key())
fernet_factory = lambda: fernet

applied = run_migrations(db_path, fernet_factory)
assert applied == [
    "001_initial_dashboard_schema",
    "002_user_price_types",
    "003_digest_history",
    "004_digest_model_settings",
    "005_chat_history",
]

with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    prompt_ids = {row["id"] for row in conn.execute("SELECT id FROM prompts").fetchall()}
    assert {"chat", "digest", "ask"} <= prompt_ids
    versions = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    assert {
        "001_initial_dashboard_schema",
        "002_user_price_types",
        "003_digest_history",
        "004_digest_model_settings",
        "005_chat_history",
    } <= versions
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert {"price_type_retail", "price_type_wholesale", "digest_provider", "digest_model"} <= user_columns
    chat_columns = {row[1] for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
    assert {"username", "role", "content", "channel", "meta_json", "created_at"} <= chat_columns

assert run_migrations(db_path, fernet_factory) == []

old_db_path = Path(tmpdir) / "old-users.db"
with sqlite3.connect(old_db_path) as conn:
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)")
    conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("legacy", "secret"))

applied = run_migrations(old_db_path, fernet_factory)
assert applied == [
    "001_initial_dashboard_schema",
    "002_user_price_types",
    "003_digest_history",
    "004_digest_model_settings",
    "005_chat_history",
]

with sqlite3.connect(old_db_path) as conn:
    conn.row_factory = sqlite3.Row
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert "password" not in columns
    assert {"password_hash", "onec_password", "onec_base_url"} <= columns
    row = conn.execute("SELECT username, password_hash, onec_password FROM users WHERE username = ?", ("legacy",)).fetchone()
    assert bcrypt.checkpw(b"secret", row["password_hash"].encode())
    assert fernet.decrypt(row["onec_password"].encode()).decode() == "secret"

print("ok")
''',
    )

    print("\nsecurity check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
