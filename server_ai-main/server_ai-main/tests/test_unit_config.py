from app.core.config import settings
from app.models.schemas import BaseCredentials, ChatRequest
import pytest
from fastapi import HTTPException

from app.core.auth import verify_service_key
from app.core.config import settings
from app.services.onec_service import _build_url, validate_readonly_query


def test_settings_load_defaults_or_env():
    assert settings.openai_base_url
    assert settings.openai_model


def test_build_url_adds_http_and_path():
    assert _build_url("127.0.0.1/unf", "/hs/ai/query") == "http://127.0.0.1/unf/hs/ai/query"


def test_chat_request_defaults_system_prompt():
    request = ChatRequest(
        credentials=BaseCredentials(login="user", password="pass", ip="127.0.0.1/unf"),
        prompt="hello",
    )

    assert request.system_prompt == ""


def test_validate_readonly_query_allows_select():
    validate_readonly_query("ВЫБРАТЬ ПЕРВЫЕ 1 Наименование ИЗ Справочник.Номенклатура")
    validate_readonly_query("SELECT name FROM catalog")


def test_validate_readonly_query_rejects_mutation():
    with pytest.raises(ValueError):
        validate_readonly_query("УДАЛИТЬ ИЗ Справочник.Номенклатура")

    with pytest.raises(ValueError):
        validate_readonly_query("UPDATE catalog SET name = 'x'")

    with pytest.raises(ValueError):
        validate_readonly_query("SELECT name FROM catalog; DROP TABLE catalog")

    with pytest.raises(ValueError):
        validate_readonly_query("ВЫБРАТЬ Наименование ИЗ Справочник.Номенклатура ОБНОВИТЬ catalog")


def test_verify_service_key_rejects_invalid_key():
    with pytest.raises(HTTPException):
        verify_service_key("bad-key")


def test_verify_service_key_accepts_configured_key():
    assert verify_service_key(settings.service_api_key) is None
