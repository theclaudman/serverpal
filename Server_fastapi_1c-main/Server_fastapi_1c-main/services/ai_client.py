# services/ai_client.py

"""
HTTP-клиент к AI Bridge (порт 8001).

Async (httpx). Передаёт system_prompt из БД дашборда —
если пусто, AI Bridge использует свой файл prompts/chat.txt.
"""

import httpx

from config import AI_SERVICE_URL

# Таймаут — LLM может думать долго (function calling до 5 итераций)
_TIMEOUT = 120


async def chat(
    prompt: str,
    login: str,
    password: str,
    onec_ip: str,
    system_prompt: str = "",
) -> str:
    """Отправляет сообщение в AI-сервис и возвращает текст ответа."""
    if not AI_SERVICE_URL:
        raise RuntimeError("AI_SERVICE_URL не задан в config.py")

    url = f"{AI_SERVICE_URL.rstrip('/')}/chat/"
    payload = {
        "credentials": {
            "login": login,
            "password": password,
            "ip": onec_ip,
        },
        "prompt": prompt,
        "system_prompt": system_prompt,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

    return data["answer"]
