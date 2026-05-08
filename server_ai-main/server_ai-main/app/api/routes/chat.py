import logging
import json
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from app.core.auth import verify_service_key, verify_ws_service_key
from app.core.security import make_base_id
from app.models.schemas import ChatRequest, ChatResponse, BaseCredentials
from app.services import ai_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse, summary="Произвольный запрос к AI", dependencies=[Depends(verify_service_key)])
def chat(req: ChatRequest) -> ChatResponse:
    """
    Принимает текстовый промпт клиента, передаёт в LLM, возвращает ответ.
    Обратная совместимость — синхронный POST.
    """
    base_id = make_base_id(req.credentials)
    answer = ai_service.answer_prompt(req.prompt, req.credentials, system_prompt=req.system_prompt)
    logger.info(f"[{base_id}] Ответ на промпт сформирован")
    return ChatResponse(base_id=base_id, answer=answer)


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket):
    """
    WebSocket стриминг чата.

    Клиент отправляет JSON:
      {"prompt": "...", "credentials": {"login": "...", "password": "...", "ip": "..."}, "system_prompt": "..."}

    Сервер отправляет JSON-события:
      {"type": "token",       "content": "..."}     — токен текста
      {"type": "tool",        "name": "..."}         — вызов инструмента
      {"type": "tool_result", "name": "..."}         — результат инструмента
      {"type": "done"}                                — конец генерации
      {"type": "error",       "message": "..."}      — ошибка
    """
    if not await verify_ws_service_key(websocket):
        return

    await websocket.accept()
    logger.info("WebSocket подключён")

    try:
        while True:
            # Ждём сообщение от клиента
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Невалидный JSON"})
                continue

            prompt = data.get("prompt", "").strip()
            if not prompt:
                await websocket.send_json({"type": "error", "message": "Пустой промпт"})
                continue

            creds_data = data.get("credentials", {})
            credentials = BaseCredentials(
                login=creds_data.get("login", ""),
                password=creds_data.get("password", ""),
                ip=creds_data.get("ip", ""),
            )
            system_prompt = data.get("system_prompt", "")

            base_id = make_base_id(credentials)
            logger.info(f"[{base_id}] WS запрос: {prompt[:80]}...")

            # Стримим ответ
            for event in ai_service.stream_answer_prompt(prompt, credentials, system_prompt):
                await websocket.send_json(event)

    except WebSocketDisconnect:
        logger.info("WebSocket отключён клиентом")
    except Exception as e:
        logger.exception("Ошибка WebSocket")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
