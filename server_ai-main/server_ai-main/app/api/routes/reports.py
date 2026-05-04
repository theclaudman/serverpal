import json
import logging
from datetime import date
from fastapi import APIRouter
from app.core.security import make_base_id
from app.models.schemas import ReportRequest, ReportResponse
from app.services import ai_service, storage_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/report", tags=["reports"])


def _handle_report(req: ReportRequest, report_type: str) -> ReportResponse:
    base_id = make_base_id(req.credentials)
    raw_data = json.dumps(req.data, ensure_ascii=False)
    report_content = ai_service.generate_report(raw_data, report_type)

    today = date.today()
    saved_path = storage_service.save_report(base_id, report_type, report_content, today)

    logger.info(f"[{base_id}] {report_type}-отчёт сохранён: {saved_path}")

    return ReportResponse(
        base_id=base_id,
        report_type=report_type,
        report_date=today.isoformat(),
        content=report_content,
        saved_path=str(saved_path),
    )


@router.post("/daily", response_model=ReportResponse, summary="Ежедневный отчёт")
def daily_report(req: ReportRequest) -> ReportResponse:
    """Принимает сырые данные из 1С, формирует ежедневный отчёт через AI."""
    return _handle_report(req, "daily")


@router.post("/weekly", response_model=ReportResponse, summary="Еженедельный отчёт")
def weekly_report(req: ReportRequest) -> ReportResponse:
    """Принимает сырые данные из 1С, формирует еженедельный отчёт через AI."""
    return _handle_report(req, "weekly")
