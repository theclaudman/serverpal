from pydantic import BaseModel
from typing import Any


# --- Идентификация базы ---

class BaseCredentials(BaseModel):
    """Учётные данные базы 1С — передаются в каждом запросе."""
    login: str
    password: str
    ip: str


# --- Отчёты ---

class ReportRequest(BaseModel):
    """Запрос с сырыми данными из 1С для формирования отчёта."""
    credentials: BaseCredentials
    data: Any  # сырые данные из 1С (структура уточняется)


class ReportResponse(BaseModel):
    """Ответ с готовым отчётом от AI."""
    base_id: str
    report_type: str   # daily | weekly | monthly | quarterly
    report_date: str   # YYYY-MM-DD
    content: str
    saved_path: str


# --- Чат / произвольный промпт ---

class ChatRequest(BaseModel):
    """Произвольный текстовый запрос клиента к AI."""
    credentials: BaseCredentials
    prompt: str


class ChatResponse(BaseModel):
    """Ответ AI на произвольный запрос."""
    base_id: str
    answer: str


# --- Запрос к базе 1С ---

class OnecQueryRequest(BaseModel):
    """Запрос на языке запросов 1С к целевой базе."""
    credentials: BaseCredentials
    query_text: str  # тело запроса на языке 1С


class OnecQueryResponse(BaseModel):
    """Ответ базы 1С на выполненный запрос."""
    base_id: str
    result: Any


# --- Реестр баз ---

class BaseInfo(BaseModel):
    """Информация о зарегистрированной базе 1С."""
    base_id: str       # уникальный идентификатор (генерируется из ip+login)
    login: str
    ip: str
    display_name: str = ""
