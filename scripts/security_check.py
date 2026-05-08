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
print("ok")
''',
    )

    print("\nsecurity check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
