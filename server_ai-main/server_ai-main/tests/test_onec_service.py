"""
Интеграционные тесты прямых запросов к базе 1С (без AI).
Проверяют связь и базовое поведение onec_service.execute_query.
"""
import pytest
from app.models.schemas import BaseCredentials
from app.services.onec_service import execute_query


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
    """Неверные учётные данные вызывают RuntimeError."""
    bad_creds = BaseCredentials(
        ip="localhost/unf_dashboard",
        login="НеверныйПользователь",
        password="НеверныйПароль",
    )
    with pytest.raises(RuntimeError):
        execute_query(bad_creds, "ВЫБРАТЬ 1")


def test_execute_query_bad_host():
    """Недоступный хост вызывает RuntimeError."""
    bad_creds = BaseCredentials(
        ip="192.0.2.1/nonexistent",  # TEST-NET, гарантированно недоступен
        login="Администратор",
        password="",
    )
    with pytest.raises(RuntimeError, match="Не удалось подключиться"):
        execute_query(bad_creds, "ВЫБРАТЬ 1")
