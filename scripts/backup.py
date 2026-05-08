from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import datetime
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


def _iter_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return [item for item in path.rglob("*") if item.is_file()]
    return []


def _backup_sources(include_env: bool) -> list[tuple[Path, str]]:
    sources = [
        (_dashboard_db_path(), "dashboard/users.db"),
        (DASHBOARD_DIR / "logs", "dashboard/logs"),
        (AI_DIR / "logs", "ai-bridge/logs"),
        (AI_DIR / "data", "ai-bridge/data"),
        (DIGEST_DIR / "logs", "digest-api/logs"),
        (DIGEST_DIR / "data", "digest-api/data"),
    ]
    if include_env:
        sources.append((ROOT / ".env", "root/.env"))
    return sources


def create_backup(output_dir: Path, include_env: bool = False, label: str = "") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    archive_path = output_dir / f"serverpal-backup-{timestamp}{suffix}.zip"

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "include_env": include_env,
        "entries": [],
    }

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, archive_root in _backup_sources(include_env):
            files = _iter_files(source)
            if not files:
                manifest["entries"].append(
                    {
                        "archive_root": archive_root,
                        "source": str(source),
                        "status": "missing",
                    }
                )
                continue

            source_base = source if source.is_dir() else source.parent
            for file_path in files:
                relative = file_path.relative_to(source_base)
                archive_name = Path(archive_root) / relative if source.is_dir() else Path(archive_root)
                archive.write(file_path, archive_name.as_posix())
                manifest["entries"].append(
                    {
                        "archive_path": archive_name.as_posix(),
                        "source": str(file_path),
                        "bytes": file_path.stat().st_size,
                        "status": "backed_up",
                    }
                )

        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a local ServerPal backup archive.")
    parser.add_argument("--output", type=Path, default=ROOT / "backups", help="Backup output directory.")
    parser.add_argument("--include-env", action="store_true", help="Include root .env in the archive.")
    parser.add_argument("--label", default="", help="Optional suffix for the archive filename.")
    args = parser.parse_args()

    archive_path = create_backup(args.output, include_env=args.include_env, label=args.label)
    print(f"Backup created: {archive_path}")
    if args.include_env:
        print("Warning: archive includes .env secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
