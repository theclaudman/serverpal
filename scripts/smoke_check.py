"""Start all ServerPal services and verify health endpoints.

This script is intentionally small and dependency-free. It is a local smoke
check, not a business-logic test suite.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SERVICES = [
    {
        "name": "Digest API",
        "cwd": ROOT / "server_digest_ai-main" / "server_digest_ai-main",
        "cmd": [sys.executable, "server.py"],
    },
    {
        "name": "AI Bridge",
        "cwd": ROOT / "server_ai-main" / "server_ai-main",
        "cmd": [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8001",
        ],
    },
    {
        "name": "Dashboard",
        "cwd": ROOT / "Server_fastapi_1c-main" / "Server_fastapi_1c-main",
        "cmd": [sys.executable, "main.py"],
    },
]

HEALTH_URLS = [
    "http://127.0.0.1:8001/health",
    "http://127.0.0.1:8002/health",
    "http://127.0.0.1:9001/health",
]


def fetch_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_health(url: str, deadline: float) -> dict:
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return fetch_json(url, timeout=3)
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not become healthy: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    log_dir = ROOT / ".smoke-logs" / uuid.uuid4().hex
    log_dir.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[str, subprocess.Popen]] = []

    try:
        print(f"logs: {log_dir}")
        for service in SERVICES:
            stdout = (log_dir / f"{service['name'].lower().replace(' ', '-')}.out.log").open("w", encoding="utf-8")
            stderr = (log_dir / f"{service['name'].lower().replace(' ', '-')}.err.log").open("w", encoding="utf-8")
            proc = subprocess.Popen(
                service["cmd"],
                cwd=service["cwd"],
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
            processes.append((service["name"], proc))
            print(f"started {service['name']} pid={proc.pid}")

        deadline = time.monotonic() + args.timeout
        for url in HEALTH_URLS:
            payload = wait_for_health(url, deadline)
            print(f"ok {url}: {json.dumps(payload, ensure_ascii=False)}")

        dashboard = fetch_json("http://127.0.0.1:9001/health", timeout=5)
        services = dashboard.get("services", {})
        if services.get("ai_bridge") is not True or services.get("digest_api") is not True:
            raise RuntimeError(f"dashboard dependencies are not healthy: {dashboard}")

        print("smoke check passed")
        return 0
    except Exception as exc:
        print(f"smoke check failed: {exc}", file=sys.stderr)
        return 1
    finally:
        for name, proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            print(f"stopped {name}")


if __name__ == "__main__":
    raise SystemExit(main())
