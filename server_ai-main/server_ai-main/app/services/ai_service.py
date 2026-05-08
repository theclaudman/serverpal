"""
ai_service.py — отправка запросов в LLM (Chat Completions API)

Совместим с LM Studio и любым OpenAI-совместимым провайдером.
Поддерживает function calling: LLM может вызвать execute_1c_query,
результат возвращается обратно в LLM для формирования ответа.

Две функции:
  answer_prompt()        — синхронный ответ целиком (для POST /chat/)
  stream_answer_prompt() — генератор токенов для WebSocket стриминга
"""

import json
import logging
from openai import OpenAI
from app.core.config import settings
from app.models.schemas import BaseCredentials
from pathlib import Path
from app.services.onec_service import execute_query, query_fingerprint, validate_readonly_query

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
# 💬 CHAT (синхронный)
# =========================
def answer_prompt(user_prompt: str, credentials: BaseCredentials, system_prompt: str = "") -> str:
    client = _get_client()

    # Промпт из БД дашборда (приоритет) или из файла (фолбэк)
    if system_prompt.strip():
        system_content = system_prompt
    else:
        system_content = _load_prompt("chat.txt")

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=2048,
        )

        for _ in range(settings.max_tool_iterations):
            msg = response.choices[0].message

            if not msg.tool_calls:
                return msg.content or "Не удалось получить ответ"

            messages.append(msg)

            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except Exception:
                    logger.exception("Ошибка парсинга arguments")
                    args = {}

                logger.info(f"Tool call: {tool_name} | args: {args}")

                try:
                    if tool_name == "execute_1c_query":
                        result = _execute_1c_query(args, credentials)
                    else:
                        result = {"error": f"Неизвестный инструмент: {tool_name}"}
                except Exception as e:
                    logger.exception(f"Ошибка выполнения {tool_name}")
                    result = {"status": "error", "message": str(e)}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=2048,
            )

        final = response.choices[0].message.content
        return final or "Не удалось получить ответ"

    except Exception:
        logger.exception("Ошибка при работе с LLM")
        return "Ошибка обработки запроса. Проверьте что LLM сервер запущен."


# =========================
# 💬 CHAT (стриминг)
# =========================
def stream_answer_prompt(user_prompt: str, credentials: BaseCredentials, system_prompt: str = ""):
    """
    Генератор, yield-ит dict-события для WebSocket:
      {"type": "token",  "content": "..."}     — очередной токен текста
      {"type": "tool",   "name": "...", ...}    — начало вызова инструмента
      {"type": "tool_result", "name": "..."}    — инструмент выполнен, стрим продолжается
      {"type": "done"}                          — конец генерации
      {"type": "error",  "message": "..."}      — ошибка
    """
    client = _get_client()

    if system_prompt.strip():
        system_content = system_prompt
    else:
        system_content = _load_prompt("chat.txt")

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_prompt},
    ]

    try:
        for iteration in range(settings.max_tool_iterations + 1):
            # Стриминговый запрос к LLM
            stream = client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=2048,
                stream=True,
            )

            # Собираем ответ из чанков
            collected_content = ""
            collected_tool_calls = {}  # index → {id, name, arguments}

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Текстовый контент — стримим токен
                if delta.content:
                    collected_content += delta.content
                    yield {"type": "token", "content": delta.content}

                # Tool calls приходят по частям
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            collected_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                collected_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                collected_tool_calls[idx]["arguments"] += tc.function.arguments

            # Если нет tool calls — генерация завершена
            if not collected_tool_calls:
                yield {"type": "done"}
                return

            # Есть tool calls — выполняем каждый
            # Формируем assistant message с tool_calls для истории
            tool_calls_list = []
            for idx in sorted(collected_tool_calls.keys()):
                tc = collected_tool_calls[idx]
                tool_calls_list.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                })

            assistant_msg = {
                "role": "assistant",
                "content": collected_content or None,
                "tool_calls": tool_calls_list,
            }
            messages.append(assistant_msg)

            # Выполняем каждый tool call
            for tc_data in tool_calls_list:
                tool_name = tc_data["function"]["name"]
                try:
                    args = json.loads(tc_data["function"]["arguments"] or "{}")
                except Exception:
                    args = {}

                logger.info(f"[stream] Tool call: {tool_name} | args: {args}")
                yield {"type": "tool", "name": tool_name}

                try:
                    if tool_name == "execute_1c_query":
                        result = _execute_1c_query(args, credentials)
                    else:
                        result = {"error": f"Неизвестный инструмент: {tool_name}"}
                except Exception as e:
                    logger.exception(f"Ошибка выполнения {tool_name}")
                    result = {"status": "error", "message": str(e)}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_data["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

                yield {"type": "tool_result", "name": tool_name}

            # Цикл продолжится — следующая итерация отправит результаты обратно в LLM

        # Вышли из цикла — слишком много итераций
        yield {"type": "token", "content": "\n\n(Достигнут лимит вызовов инструментов)"}
        yield {"type": "done"}

    except Exception as e:
        logger.exception("Ошибка стриминга LLM")
        yield {"type": "error", "message": str(e)}


# =========================
# 🔧 TOOL IMPLEMENTATIONS
# =========================

def _execute_1c_query(args: dict, credentials: BaseCredentials):
    query = args.get("query")
    if not query:
        return {"error": "query не передан"}

    try:
        validate_readonly_query(query)
    except ValueError as exc:
        return {"status": "error", "message": str(exc), "query_id": query_fingerprint(query)}

    logger.info(f"[TOOL] execute_1c_query query_id={query_fingerprint(query)}")

    try:
        result = execute_query(credentials, query)
        logger.info(f"[TOOL RESULT] записей: {len(result) if isinstance(result, list) else 'N/A'}")
        return result
    except Exception as e:
        logger.exception("Ошибка запроса к 1С")
        return {"status": "error", "message": str(e)}
