import json
import logging
from app.models.schemas import BaseCredentials
from app.services.onec_service import execute_query

logger = logging.getLogger(__name__)


def dispatch(tool_name: str, arguments: dict, credentials: BaseCredentials) -> str:
    """
    Выполняет инструмент по имени и возвращает результат в виде строки.
    Вызывается когда OpenAI возвращает finish_reason='tool_calls'.

    Возвращает строку — она вставляется в диалог как сообщение role=tool.
    """
    if tool_name == "execute_1c_query":
        return _execute_1c_query(arguments, credentials)

    raise ValueError(f"Неизвестный инструмент: {tool_name!r}")


def _execute_1c_query(arguments: dict, credentials: BaseCredentials) -> str:
    query_text = arguments.get("query_text", "")
    if not query_text:
        return json.dumps({"error": "Пустой текст запроса"}, ensure_ascii=False)

    logger.info(f"Tool execute_1c_query: {query_text[:120]}")

    try:
        result = execute_query(credentials, query_text)
        return json.dumps(result, ensure_ascii=False)
    except RuntimeError as e:
        logger.warning(f"Ошибка запроса к 1С: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
