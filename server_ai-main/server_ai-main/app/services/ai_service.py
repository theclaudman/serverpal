"""
ai_service.py — отправка запросов в LLM (Chat Completions API)

Совместим с LM Studio и любым OpenAI-совместимым провайдером.
Поддерживает function calling: LLM может вызвать execute_1c_query,
результат возвращается обратно в LLM для формирования ответа.
"""

import json
import logging
from openai import OpenAI
from app.core.config import settings
from app.models.schemas import BaseCredentials
from pathlib import Path
from app.services.onec_service import execute_query

logger = logging.getLogger(__name__)


def _load_prompt(prompt_file: str) -> str:
    path = Path("prompts") / prompt_file
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


# =========================
# 📊 REPORT GENERATION
# =========================
def generate_report(raw_data: str, report_type: str) -> str:
    system_prompt = _load_prompt(f"{report_type}_report.txt")
    client = _get_client()

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_data},
        ],
        temperature=0.3,
        max_tokens=2048,
    )

    return response.choices[0].message.content or ""


# =========================
# 🔧 TOOL DEFINITIONS
# =========================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_1c_query",
            "description": (
                "Выполняет запрос на языке 1С к базе данных 1С УНФ 3.0. "
                "Используй когда пользователю нужны актуальные данные: "
                "остатки, продажи, задолженности, контрагенты и т.д. "
                "Возвращает JSON с результатом."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Запрос на языке 1С (только ВЫБРАТЬ/SELECT)"
                    }
                },
                "required": ["query"],
            },
        },
    },
]


# =========================
# 💬 CHAT
# =========================
def answer_prompt(user_prompt: str, credentials: BaseCredentials) -> str:
    client = _get_client()
    system_prompt = _load_prompt("chat.txt")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        # Первый вызов LLM
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=2048,
        )

        # Tool loop — до 5 итераций
        for _ in range(settings.max_tool_iterations):
            msg = response.choices[0].message

            # Если нет tool_calls — LLM дал финальный ответ
            if not msg.tool_calls:
                return msg.content or "Не удалось получить ответ"

            # Добавляем ответ LLM с tool_calls в историю
            messages.append(msg)

            # Обрабатываем каждый tool call
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name

                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except Exception:
                    logger.exception("Ошибка парсинга arguments")
                    args = {}

                logger.info(f"Tool call: {tool_name} | args: {args}")

                # Выполняем инструмент
                try:
                    if tool_name == "execute_1c_query":
                        result = _execute_1c_query(args, credentials)
                    else:
                        result = {"error": f"Неизвестный инструмент: {tool_name}"}
                except Exception as e:
                    logger.exception(f"Ошибка выполнения {tool_name}")
                    result = {"status": "error", "message": str(e)}

                # Добавляем результат tool в историю
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            # Отправляем обратно в LLM с результатами tool
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=2048,
            )

        # Если вышли из цикла — берём последний ответ
        final = response.choices[0].message.content
        return final or "Не удалось получить ответ"

    except Exception:
        logger.exception("Ошибка при работе с LLM")
        return "Ошибка обработки запроса. Проверьте что LLM сервер запущен."


# =========================
# 🔧 TOOL IMPLEMENTATIONS
# =========================

def _execute_1c_query(args: dict, credentials: BaseCredentials):
    query = args.get("query")
    if not query:
        return {"error": "query не передан"}

    logger.info(f"[TOOL] execute_1c_query: {query}")

    try:
        result = execute_query(credentials, query)
        logger.info(f"[TOOL RESULT] записей: {len(result) if isinstance(result, list) else 'N/A'}")
        return result
    except Exception as e:
        logger.exception("Ошибка запроса к 1С")
        return {"status": "error", "message": str(e)}
