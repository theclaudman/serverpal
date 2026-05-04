"""
digest_client.py — HTTP-клиент к Digest-сервису (порт 8002)

Три функции:
  get_providers()       — список LLM-провайдеров
  generate_digest(...)  — сгенерировать дайджест
  ask_question(...)     — задать вопрос по данным дайджеста

Все функции возвращают dict.
При ошибке: {"status": "error", "message": "..."}
"""

import json
import urllib.request
import urllib.error

from config import DIGEST_SERVICE_URL


# Таймаут для генерации дайджеста / вопроса (LLM думает долго)
_TIMEOUT_LONG = 300

# Таймаут для лёгких запросов (health, providers)
_TIMEOUT_SHORT = 10


def _post(path: str, body: dict, timeout: int = _TIMEOUT_LONG) -> dict:
    """POST JSON к digest-сервису, возвращает dict."""
    url = f"{DIGEST_SERVICE_URL}{path}"
    data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return {
                "status": "error",
                "message": err_body.get("message", str(e)),
            }
        except Exception:
            return {"status": "error", "message": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError:
        return {
            "status": "error",
            "message": (
                "Сервис дайджеста недоступен. "
                f"Убедитесь что он запущен: {DIGEST_SERVICE_URL}"
            ),
        }
    except TimeoutError:
        return {
            "status": "error",
            "message": "Превышено время ожидания. Попробуйте ещё раз.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _get(path: str, timeout: int = _TIMEOUT_SHORT) -> dict:
    """GET к digest-сервису, возвращает dict."""
    url = f"{DIGEST_SERVICE_URL}{path}"
    req = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
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

def get_providers() -> dict:
    """
    GET /api/providers — список LLM-провайдеров.
    Возвращает {"providers": [...]} или {"status": "error", ...}.
    """
    return _get("/api/providers")


def generate_digest(
    login: str,
    password: str,
    onec_base_url: str,
    date: str = None,
    provider: str = "lmstudio",
) -> dict:
    """
    POST /api/digest — сгенерировать дайджест.

    Параметры login, password, onec_base_url берутся из сессии дашборда.
    onec_base_url приходит как "http://localhost/Eu/" — нужно достроить путь OData.

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
    }

    if date:
        body["date"] = date

    return _post("/api/digest", body)


def ask_question(
    login: str,
    password: str,
    onec_base_url: str,
    question: str,
    provider: str = "lmstudio",
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
    }

    return _post("/api/ask", body)


def _build_odata_url(onec_base_url: str) -> str:
    """
    Достраивает OData-путь из base_url дашборда.

    Вход:  "http://localhost/Eu/"  или  "http://localhost/Eu"
    Выход: "http://localhost/Eu/odata/standard.odata"

    Если URL уже содержит /odata/ — возвращает как есть.
    """
    url = onec_base_url.rstrip("/")

    if "/odata/standard.odata" in url:
        return url

    return f"{url}/odata/standard.odata"
