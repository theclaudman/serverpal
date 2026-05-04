import logging
from fastapi import APIRouter, HTTPException
from app.core.security import make_base_id
from app.models.schemas import OnecQueryRequest, OnecQueryResponse
from app.services.onec_service import execute_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/query", tags=["query"])


@router.post("/", response_model=OnecQueryResponse, summary="Выполнить запрос к базе 1С")
def run_query(req: OnecQueryRequest) -> OnecQueryResponse:
    """
    Принимает текст запроса на языке 1С, выполняет его на целевой базе,
    возвращает результат.
    """
    base_id = make_base_id(req.credentials)

    try:
        result = execute_query(req.credentials, req.query_text)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    logger.info(f"[{base_id}] Выполнен запрос к 1С")
    return OnecQueryResponse(base_id=base_id, result=result)
