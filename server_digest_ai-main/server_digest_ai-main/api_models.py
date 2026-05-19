"""
api_models.py — Pydantic-модели запросов и ответов Digest API

Контракт между digest-сервисом и дашбордом.
Менять осторожно — дашборд зависит от этих схем.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Запросы
# ---------------------------------------------------------------------------

class Credentials(BaseModel):
    """Параметры подключения к 1С."""
    base_url: str = Field(..., description="URL OData 1С, например https://example.com/base/odata/standard.odata")
    login: str
    password: str


class DigestRequest(BaseModel):
    """POST /api/digest — сгенерировать дайджест."""
    credentials: Credentials
    date: Optional[str] = Field(
        None,
        description="Дата в формате YYYY-MM-DD. По умолчанию — вчера."
    )
    provider: str = Field(
        "lmstudio",
        description="LLM-провайдер: lmstudio | openai"
    )
    system_prompt: str = Field(
        "",
        description="Системный промпт из БД дашборда. Если пусто — берётся из файла."
    )


class AskRequest(BaseModel):
    """POST /api/ask — вопрос по данным последнего дайджеста."""
    credentials: Credentials
    question: str = Field(..., description="Вопрос пользователя")
    provider: str = Field(
        "lmstudio",
        description="LLM-провайдер: lmstudio | openai"
    )
    system_prompt: str = Field(
        "",
        description="Системный промпт из БД дашборда. Если пусто — берётся из файла."
    )


# ---------------------------------------------------------------------------
# Ответы
# ---------------------------------------------------------------------------

class DigestResponse(BaseModel):
    """Успешный ответ POST /api/digest."""
    status: str = "ok"
    digest: str
    date: str
    generated_at: str
    provider: str
    anonymized: bool


class AskResponse(BaseModel):
    """Успешный ответ POST /api/ask."""
    status: str = "ok"
    answer: str
    question: str
    context_date: str
    context_age_minutes: int
    provider: str


class ErrorResponse(BaseModel):
    """Ответ при ошибке."""
    status: str = "error"
    error: str = Field(..., description="Код ошибки: connection_failed | llm_unavailable | no_context | invalid_date")
    message: str = Field(..., description="Человекочитаемое описание")


class ProviderInfo(BaseModel):
    """Один LLM-провайдер."""
    id: str
    name: str
    available: bool
    anonymize: bool


class ProvidersResponse(BaseModel):
    """GET /api/providers."""
    providers: list[ProviderInfo]


class HealthResponse(BaseModel):
    """GET /health."""
    status: str = "ok"
    version: str = "0.1.0"
