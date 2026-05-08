import http.client
import urllib.request
import urllib.parse
import urllib.error
import json
import base64
import hashlib
import re
from app.models.schemas import BaseCredentials


def _build_url(ip: str, path: str = "/") -> str:
    """Формирует URL до эндпоинта 1С."""
    # Ожидаемый формат: http://<ip>/ваш_путь_к_сервису_1с
    if not ip.startswith("http"):
        ip = f"http://{ip}"
    return f"{ip.rstrip('/')}{path}"


def _basic_auth_header(login: str, password: str) -> str:
    """Формирует заголовок Basic Auth."""
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return f"Basic {token}"


_FORBIDDEN_QUERY_PATTERNS = [
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bEXEC\b",
    r"\bMERGE\b",
    r"\bУДАЛИТЬ\b",
    r"\bОБНОВИТЬ\b",
    r"\bВСТАВИТЬ\b",
    r"\bИЗМЕНИТЬ\b",
    r"\bСОЗДАТЬ\b",
    r"\bВЫПОЛНИТЬ\b",
]


def query_fingerprint(query_text: str) -> str:
    return hashlib.sha256(query_text.encode("utf-8")).hexdigest()[:12]


def validate_readonly_query(query_text: str) -> None:
    normalized = query_text.strip()
    upper = normalized.upper()
    if not upper.startswith(("ВЫБРАТЬ", "SELECT")):
        raise ValueError("Разрешены только read-only запросы, начинающиеся с ВЫБРАТЬ или SELECT")

    for pattern in _FORBIDDEN_QUERY_PATTERNS:
        if re.search(pattern, upper):
            raise ValueError("Запрос содержит запрещённую операцию")


# def execute_query(credentials: BaseCredentials, query_text: str) -> dict:
#     print(query_text)
#     """
#     Отправляет запрос на языке 1С к целевой базе.
#     Ожидает JSON-ответ от эндпоинта 1С.
#
#     Тело запроса: {"query": "<текст запроса 1С>"}
#     """
#     url = _build_url(credentials.ip, path="/hs/ai/query")  # путь уточнить под реальный эндпоинт 1С
#     payload = json.dumps({"query": query_text}).encode("utf-8")
#
#     req = urllib.request.Request(
#         url=url,
#         data=payload,
#         method="POST",
#         headers={
#             "Content-Type": "application/json",
#             "Authorization": _basic_auth_header(credentials.login, credentials.password),
#         },
#     )
#
#     try:
#         with urllib.request.urlopen(req, timeout=30) as response:
#             raw = response.read().decode("utf-8")
#             return json.loads(raw)
#     except urllib.error.HTTPError as e:
#         raise RuntimeError(f"1С вернула HTTP {e.code}: {e.reason}")
#     except urllib.error.URLError as e:
#         raise RuntimeError(f"Не удалось подключиться к базе 1С: {e.reason}")
#     except (http.client.RemoteDisconnected, ConnectionError) as e:
#         raise RuntimeError(f"Не удалось подключиться к базе 1С: {e}")

def execute_query(credentials: BaseCredentials, query_text: str) -> dict:
    validate_readonly_query(query_text)

    url = _build_url(credentials.ip, path="/hs/ai/query")
    payload = json.dumps({"query": query_text}).encode("utf-8")

    req = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": _basic_auth_header(credentials.login, credentials.password),
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    except urllib.error.HTTPError as e:
        # 👇 ВАЖНО: читаем тело ответа
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            error_body = ""

        return {
            "status": "error",
            "type": "http_error",
            "code": e.code,
            "reason": e.reason,
            "details": error_body,  # 👈 вот здесь будет текст ошибки 1С
            "query_id": query_fingerprint(query_text),
        }

    except urllib.error.URLError as e:
        return {
            "status": "error",
            "type": "connection_error",
            "message": str(e.reason),
            "query_id": query_fingerprint(query_text),
        }

    except (http.client.RemoteDisconnected, ConnectionError) as e:
        return {
            "status": "error",
            "type": "connection_error",
            "message": str(e),
            "query_id": query_fingerprint(query_text),
        }
