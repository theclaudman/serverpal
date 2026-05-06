"""
digest_client.py — HTTP-клиент к Digest-сервису (порт 8002)

Три функции:
  get_providers()       — список LLM-провайдеров
  generate_digest(...)  — сгенерировать дайджест
  ask_question(...)     — задать вопрос по данным дайджеста

Все функции async (httpx).
Передают system_prompt из БД дашборда — если пусто,
Digest API использует свои файлы prompts/*.txt.

При ошибке: {"status": "error", "message": "..."}
"""

import httpx

from config import DIGEST_SERVICE_URL


# Таймаут для генерации дайджеста / вопроса (LLM думает долго)
_TIMEOUT_LONG = 300

# Таймаут для лёгких запросов (health, providers)
_TIMEOUT_SHORT = 10


async def _post(path: str, body: dict, timeout: int = _TIMEOUT_LONG) -> dict:
    """POST JSON к digest-сервису, возвращает dict."""
    url = f"{DIGEST_SERVICE_URL}{path}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body)
            return resp.json()
    except httpx.TimeoutException:
        return {
            "status": "error",
            "message": "Превышено время ожидания. Попробуйте ещё раз.",
        }
    except httpx.ConnectError:
        return {
            "status": "error",
            "message": (
                "Сервис дайджеста недоступен. "
                f"Убедитесь что он запущен: {DIGEST_SERVICE_URL}"
            ),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _get(path: str, timeout: int = _TIMEOUT_SHORT) -> dict:
    """GET к digest-сервису, возвращает dict."""
    url = f"{DIGEST_SERVICE_URL}{path}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return resp.json()
    except httpx.ConnectError:
        return {
            "status": "error",
            "message": (
                "Сервис дайджеста недоступен. "
                f"Убедитесь что он запущен: {DIGEST_SERVICE_URL}"
            ),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Публичные функции ───────────────────────────────────────────────────────

async def get_providers() -> dict:
    """
    GET /api/providers — список LLM-провайдеров.
    Возвращает {"providers": [...]} или {"status": "error", ...}.
    """
    return await _get("/api/providers")


async def generate_digest(
    login: str,
    password: str,
    onec_base_url: str,
    date: str = None,
    provider: str = "lmstudio",
    system_prompt: str = "",
) -> dict:
    """
    POST /api/digest — сгенерировать дайджест.

    Параметры login, password, onec_base_url берутся из сессии дашборда.
    onec_base_url приходит как "http://127.0.0.1/Eu/" — нужно достроить путь OData.

    Возвращает:
      {"status": "ok", "digest": "...", "date": "...", ...}
      или {"status": "error", "message": "..."}
    """
    base_url = _build_odata_url(onec_base_url)

    body = {
        "credentials": {
            "base_url": base_url,
            "login": login,
            "password": password,
        },
        "provider": provider,
        "system_prompt": system_prompt,
    }

    if date:
        body["date"] = date

    return await _post("/api/digest", body)


async def ask_question(
    login: str,
    password: str,
    onec_base_url: str,
    question: str,
    provider: str = "lmstudio",
    system_prompt: str = "",
) -> dict:
    """
    POST /api/ask — вопрос по данным последнего дайджеста.

    Возвращает:
      {"status": "ok", "answer": "...", "question": "...", ...}
      или {"status": "error", "message": "..."}
    """
    base_url = _build_odata_url(onec_base_url)

    body = {
        "credentials": {
            "base_url": base_url,
            "login": login,
            "password": password,
        },
        "question": question,
        "provider": provider,
        "system_prompt": system_prompt,
    }

    return await _post("/api/ask", body)


def _build_odata_url(onec_base_url: str) -> str:
    """
    Достраивает OData-путь из base_url дашборда.

    Вход:  "http://127.0.0.1/Eu/"  или  "http://127.0.0.1/Eu"
    Выход: "http://127.0.0.1/Eu/odata/standard.odata"

    Если URL уже содержит /odata/ — возвращает как есть.
    """
    url = onec_base_url.rstrip("/")

    if "/odata/standard.odata" in url:
        return url

    return f"{url}/odata/standard.odata"
