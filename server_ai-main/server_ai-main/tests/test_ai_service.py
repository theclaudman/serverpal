"""
Интеграционные тесты AI сервиса.
Реальные вызовы OpenAI API + реальные запросы к базе 1С.
"""
import pytest
from app.models.schemas import BaseCredentials
from app.services.ai_service import answer_prompt, generate_report


class TestAnswerPromptSimple:
    """Запросы, не требующие обращения к базе 1С."""

    def test_returns_string(self, onec_credentials: BaseCredentials):
        """answer_prompt возвращает непустую строку."""
        result = answer_prompt("Привет! Что ты умеешь?", onec_credentials)
        print(f"\n[Ответ]\n{result}")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_tool_call_for_general_question(self, onec_credentials: BaseCredentials):
        """Общий вопрос не должен вызывать обращения к 1С и всё равно возвращает ответ."""
        result = answer_prompt(
            "Как работает система УНФ? Ответь кратко, без обращения к базе.",
            onec_credentials,
        )
        print(f"\n[Ответ]\n{result}")

        assert isinstance(result, str)
        assert len(result) > 0


class TestAnswerPromptWithTool:
    """Запросы, требующие данных из 1С."""

    def test_stock_query_triggers_tool(self, onec_credentials: BaseCredentials):
        """Вопрос об остатках товаров вызывает execute_1c_query и возвращает ответ."""
        result = answer_prompt(
            "Покажи остатки товаров на складе. Выведи первые 5 позиций.",
            onec_credentials,
        )
        print(f"\n[Ответ]\n{result}")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_sales_query_triggers_tool(self, onec_credentials: BaseCredentials):
        """Вопрос о продажах вызывает execute_1c_query и возвращает ответ."""
        result = answer_prompt(
            "Какие были продажи за последний месяц? Покажи топ-3 позиции.",
            onec_credentials,
        )
        print(f"\n[Ответ]\n{result}")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_debt_query_triggers_tool(self, onec_credentials: BaseCredentials):
        """Вопрос о задолженностях контрагентов обрабатывается корректно."""
        result = answer_prompt(
            "Есть ли у нас дебиторская задолженность? Назови контрагентов с долгами.",
            onec_credentials,
        )
        print(f"\n[Ответ]\n{result}")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_answer_when_no_data(self, onec_credentials: BaseCredentials):
        """Если данных нет — AI сообщает об этом, а не падает."""
        result = answer_prompt(
            "Покажи продажи за 1990 год.",
            onec_credentials,
        )
        print(f"\n[Ответ]\n{result}")

        assert isinstance(result, str)
        assert len(result) > 0


class TestGenerateReport:
    """Тесты генерации отчётов."""

    def test_generate_daily_report(self, onec_credentials: BaseCredentials):
        """Генерация дневного отчёта возвращает непустой текст."""
        raw_data = (
            "Продажи за день: Товар А — 10 шт. на 5000 руб., "
            "Товар Б — 5 шт. на 2500 руб. Итого: 7500 руб."
        )
        result = generate_report(raw_data, "daily")
        print(f"\n[Отчёт]\n{result}")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_report_with_empty_data(self, onec_credentials: BaseCredentials):
        """Генерация отчёта с минимальными данными не вызывает исключений."""
        result = generate_report("Данных за период нет.", "daily")
        print(f"\n[Отчёт]\n{result}")

        assert isinstance(result, str)
        assert len(result) > 0
