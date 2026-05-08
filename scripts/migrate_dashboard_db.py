from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "Server_fastapi_1c-main" / "Server_fastapi_1c-main"


def main() -> int:
    sys.path.insert(0, str(DASHBOARD_DIR))
    os.chdir(DASHBOARD_DIR)

    from database import DB_PATH, _fernet  # noqa: PLC0415
    from migrations import run_migrations  # noqa: PLC0415

    applied = run_migrations(DB_PATH, _fernet)
    if applied:
        print("Applied dashboard DB migrations:")
        for version in applied:
            print(f"  - {version}")
    else:
        print("Dashboard DB migrations are already up to date.")
    print(f"Database: {DB_PATH.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
