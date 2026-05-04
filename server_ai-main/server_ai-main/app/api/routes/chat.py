import logging
from fastapi import APIRouter
from app.core.security import make_base_id
from app.models.schemas import ChatRequest, ChatResponse
from app.services import ai_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse, summary="Произвольный запрос к AI")
def chat(req: ChatRequest) -> ChatResponse:
    """
    Принимает текстовый промпт клиента, передаёт в GigaChat, возвращает ответ.
    """
    base_id = make_base_id(req.credentials)
    answer = ai_service.answer_prompt(req.prompt, req.credentials)
    logger.info(f"[{base_id}] Ответ на промпт сформирован")
    return ChatResponse(base_id=base_id, answer=answer)
