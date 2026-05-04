# services/ai_client.py

import json
import urllib.request

from config import AI_SERVICE_URL


def chat(prompt: str, login: str, password: str, onec_ip: str) -> str:
    """Отправляет сообщение в AI-сервис и возвращает текст ответа."""
    if not AI_SERVICE_URL:
        raise RuntimeError("AI_SERVICE_URL не задан в config.py")

    url = f"{AI_SERVICE_URL.rstrip('/')}/chat/"
    payload = json.dumps(
        {
            "credentials": {
                "login": login,
                "password": password,
                "ip": onec_ip,
            },
            "prompt": prompt,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")

    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))

    return data["answer"]
