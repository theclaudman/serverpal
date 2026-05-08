from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(name: str, cmd: list[str], cwd: Path = ROOT) -> None:
    print(f"\n== {name} ==")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    run(
        "py_compile",
        [
            sys.executable,
            "-m",
            "py_compile",
            "run_all.py",
            "Server_fastapi_1c-main/Server_fastapi_1c-main/main.py",
            "Server_fastapi_1c-main/Server_fastapi_1c-main/config.py",
            "Server_fastapi_1c-main/Server_fastapi_1c-main/database.py",
            "Server_fastapi_1c-main/Server_fastapi_1c-main/migrations.py",
            "server_ai-main/server_ai-main/app/api/routes/chat.py",
            "server_ai-main/server_ai-main/app/core/config.py",
            "server_ai-main/server_ai-main/app/services/ai_service.py",
            "server_digest_ai-main/server_digest_ai-main/server.py",
            "server_digest_ai-main/server_digest_ai-main/lm_client.py",
            "scripts/smoke_check.py",
            "scripts/security_check.py",
            "scripts/migrate_dashboard_db.py",
        ],
    )
    run(
        "pytest default",
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT / "server_ai-main" / "server_ai-main",
    )
    run("security_check", [sys.executable, "scripts/security_check.py"])
    run("smoke_check", [sys.executable, "scripts/smoke_check.py", "--timeout", "30"])
    print("\ndev check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
