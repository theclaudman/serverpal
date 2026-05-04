"""
Единый запуск всех сервисов ServerPal.
Использование: python run_all.py
Остановка: Ctrl+C — остановит все три сервиса.
"""

import subprocess
import sys
import os
import signal
import time

SERVICES = [
    {
        "name": "Digest API (8002)",
        "cwd": "server_digest_ai-main/server_digest_ai-main",
        "cmd": [sys.executable, "server.py"],
    },
    {
        "name": "AI Bridge (8001)",
        "cwd": "server_ai-main/server_ai-main",
        "cmd": [sys.executable, "-m", "uvicorn", "app.main:app",
                "--host", "0.0.0.0", "--port", "8001"],
    },
    {
        "name": "Dashboard (8000)",
        "cwd": "Server_fastapi_1c-main/Server_fastapi_1c-main",
        "cmd": [sys.executable, "main.py"],
    },
]

processes = []


def start_all():
    print("=" * 50)
    print("  ServerPal — запуск всех сервисов")
    print("=" * 50)

    for svc in SERVICES:
        cwd = os.path.join(os.path.dirname(__file__), svc["cwd"])

        if not os.path.exists(cwd):
            print(f"  ✗ {svc['name']} — папка не найдена: {cwd}")
            continue

        proc = subprocess.Popen(
            svc["cmd"],
            cwd=cwd,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        processes.append((svc["name"], proc))
        print(f"  ✓ {svc['name']} запущен (PID {proc.pid})")

    print("=" * 50)
    print("  Все сервисы запущены. Ctrl+C для остановки.")
    print("=" * 50)


def stop_all():
    print("\n\nОстановка сервисов...")
    for name, proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=5)
            print(f"  ✓ {name} остановлен")
        except Exception:
            proc.kill()
            print(f"  ✗ {name} убит принудительно")


if __name__ == "__main__":
    try:
        start_all()
        # Ждём пока все процессы работают
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"\n  ✗ {name} упал с кодом {proc.returncode}")
            time.sleep(2)
    except KeyboardInterrupt:
        stop_all()