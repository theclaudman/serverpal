from __future__ import annotations

import argparse
import json
import os
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "Server_fastapi_1c-main" / "Server_fastapi_1c-main"
AI_DIR = ROOT / "server_ai-main" / "server_ai-main"
DIGEST_DIR = ROOT / "server_digest_ai-main" / "server_digest_ai-main"


def _read_root_env() -> dict[str, str]:
    env_path = ROOT / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _dashboard_db_path() -> Path:
    env = _read_root_env()
    configured = os.environ.get("DASHBOARD_DB_PATH") or env.get("DASHBOARD_DB_PATH") or "users.db"
    path = Path(configured)
    return path if path.is_absolute() else DASHBOARD_DIR / path


def _target_for_archive_path(archive_path: str) -> Path | None:
    path = Path(archive_path)
    parts = path.parts
    if archive_path == "dashboard/users.db":
        return _dashboard_db_path()
    if parts[:2] == ("dashboard", "logs"):
        return DASHBOARD_DIR / "logs" / Path(*parts[2:])
    if parts[:2] == ("ai-bridge", "logs"):
        return AI_DIR / "logs" / Path(*parts[2:])
    if parts[:2] == ("ai-bridge", "data"):
        return AI_DIR / "data" / Path(*parts[2:])
    if parts[:2] == ("digest-api", "logs"):
        return DIGEST_DIR / "logs" / Path(*parts[2:])
    if parts[:2] == ("digest-api", "data"):
        return DIGEST_DIR / "data" / Path(*parts[2:])
    if archive_path == "root/.env":
        return ROOT / ".env"
    return None


def restore_backup(archive_path: Path, yes: bool = False) -> list[Path]:
    if not yes:
        raise RuntimeError("Restore is destructive. Re-run with --yes to confirm.")

    restored: list[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        if "manifest.json" not in names:
            raise RuntimeError("Archive does not contain manifest.json")

        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        entries = [
            entry
            for entry in manifest.get("entries", [])
            if entry.get("status") == "backed_up" and entry.get("archive_path")
        ]

        for entry in entries:
            archive_name = entry["archive_path"]
            target = _target_for_archive_path(archive_name)
            if target is None:
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(archive_name) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            restored.append(target)

    return restored


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a local ServerPal backup archive.")
    parser.add_argument("archive", type=Path, help="Backup archive created by scripts/backup.py.")
    parser.add_argument("--yes", action="store_true", help="Confirm overwriting local files.")
    args = parser.parse_args()

    restored = restore_backup(args.archive, yes=args.yes)
    print(f"Restored {len(restored)} files from {args.archive}")
    for path in restored:
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
