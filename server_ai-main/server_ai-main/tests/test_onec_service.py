"""
Интеграционные тесты прямых запросов к базе 1С (без AI).
Проверяют связь и базовое поведение onec_service.execute_query.
"""
import pytest
from app.models.schemas import BaseCredentials
from app.services.onec_service import execute_query

pytestmark = pytest.mark.integration


def test_execute_query_success(onec_credentials: BaseCredentials):
    """Простой SELECT-запрос возвращает непустой результат."""
    query = "ВЫБРАТЬ ПЕРВЫЕ 5 Наименование ИЗ Справочник.Номенклатура"
    result = execute_query(onec_credentials, query)
    print(f"\n[Результат]\n{result}")

    assert result is not None, "Ответ не должен быть None"
    assert isinstance(result, (dict, list)), f"Ожидался dict или list, получено: {type(result)}"


def test_execute_query_returns_counterparties(onec_credentials: BaseCredentials):
    """Запрос контрагентов возвращает список."""
    query = "ВЫБРАТЬ ПЕРВЫЕ 5 Наименование ИЗ Справочник.Контрагенты"
    result = execute_query(onec_credentials, query)
    print(f"\n[Результат]\n{result}")

    assert result is not None


def test_execute_query_bad_credentials():
    """Неверные учётные данные возвращают структурированную ошибку."""
    bad_creds = BaseCredentials(
        ip="127.0.0.1/unf_dashboard",
        login="НеверныйПользователь",
        password="НеверныйПароль",
    )
    result = execute_query(bad_creds, "ВЫБРАТЬ 1")

    assert result["status"] == "error"
    assert result["type"] in {"http_error", "connection_error"}


def test_execute_query_bad_host():
    """Недоступный хост возвращает структурированную ошибку."""
    bad_creds = BaseCredentials(
        ip="192.0.2.1/nonexistent",  # TEST-NET, гарантированно недоступен
        login="Администратор",
        password="",
    )
    result = execute_query(bad_creds, "ВЫБРАТЬ 1")

    assert result["status"] == "error"
    assert result["type"] == "connection_error"
