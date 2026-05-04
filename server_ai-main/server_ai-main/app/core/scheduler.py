import json
import logging
from datetime import date
from calendar import monthrange
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings
from app.services import ai_service, storage_service

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def _get_all_bases() -> list[dict]:
    """Возвращает список всех зарегистрированных баз."""
    if not settings.registry_file.exists():
        return []
    with open(settings.registry_file, "r", encoding="utf-8") as f:
        registry = json.load(f)
    return [{"base_id": k, **v} for k, v in registry.items()]


def _collect_daily_reports_for_month(base_id: str, year: int, month: int) -> str:
    """
    Собирает все ежедневные отчёты за указанный месяц в одну строку.
    Возвращает объединённый текст всех найденных отчётов.
    """
    _, days_in_month = monthrange(year, month)
    parts = []

    for day in range(1, days_in_month + 1):
        report_date = date(year, month, day)
        content = storage_service.load_report(base_id, "daily", report_date)
        if content:
            parts.append(f"### Отчёт за {report_date.isoformat()}\n\n{content}")

    if not parts:
        raise ValueError(f"Нет ежедневных отчётов за {year}-{month:02d} для базы {base_id}")

    return "\n\n---\n\n".join(parts)


def _collect_monthly_reports_for_quarter(base_id: str, year: int, quarter: int) -> str:
    """
    Собирает все ежемесячные отчёты за указанный квартал в одну строку.
    quarter: 1..4
    """
    first_month = (quarter - 1) * 3 + 1
    months = [first_month, first_month + 1, first_month + 2]
    parts = []

    for month in months:
        # Берём отчёт за 1-е число каждого месяца (дата сохранения по таймеру)
        report_date = date(year, month, 1)
        content = storage_service.load_report(base_id, "monthly", report_date)
        if content:
            parts.append(f"### Ежемесячный отчёт за {report_date.strftime('%B %Y')}\n\n{content}")

    if not parts:
        raise ValueError(f"Нет ежемесячных отчётов за Q{quarter} {year} для базы {base_id}")

    return "\n\n---\n\n".join(parts)


async def _generate_monthly_reports() -> None:
    """
    Ежемесячный отчёт: агрегирует ежедневные отчёты прошлого месяца,
    передаёт в GigaChat, сохраняет результат.
    """
    today = date.today()
    # Берём прошлый месяц
    if today.month == 1:
        target_year, target_month = today.year - 1, 12
    else:
        target_year, target_month = today.year, today.month - 1

    bases = _get_all_bases()
    logger.info(f"Формирование ежемесячных отчётов за {target_year}-{target_month:02d} для {len(bases)} баз")

    for entry in bases:
        base_id = entry["base_id"]
        try:
            aggregated = _collect_daily_reports_for_month(base_id, target_year, target_month)
            report_content = ai_service.generate_report(aggregated, "monthly")
            saved_path = storage_service.save_report(base_id, "monthly", report_content, date(target_year, target_month, 1))
            logger.info(f"[{base_id}] Ежемесячный отчёт сохранён: {saved_path}")
        except ValueError as e:
            logger.warning(f"[{base_id}] Пропуск: {e}")
        except Exception as e:
            logger.error(f"[{base_id}] Ошибка при формировании ежемесячного отчёта: {e}")


async def _generate_quarterly_reports() -> None:
    """
    Ежеквартальный отчёт: агрегирует ежемесячные отчёты прошлого квартала,
    передаёт в GigaChat, сохраняет результат.
    """
    today = date.today()
    current_quarter = (today.month - 1) // 3 + 1

    # Берём прошлый квартал
    if current_quarter == 1:
        target_year, target_quarter = today.year - 1, 4
    else:
        target_year, target_quarter = today.year, current_quarter - 1

    bases = _get_all_bases()
    logger.info(f"Формирование ежеквартальных отчётов за Q{target_quarter} {target_year} для {len(bases)} баз")

    for entry in bases:
        base_id = entry["base_id"]
        try:
            aggregated = _collect_monthly_reports_for_quarter(base_id, target_year, target_quarter)
            report_content = ai_service.generate_report(aggregated, "quarterly")
            first_month = (target_quarter - 1) * 3 + 1
            saved_path = storage_service.save_report(base_id, "quarterly", report_content, date(target_year, first_month, 1))
            logger.info(f"[{base_id}] Ежеквартальный отчёт сохранён: {saved_path}")
        except ValueError as e:
            logger.warning(f"[{base_id}] Пропуск: {e}")
        except Exception as e:
            logger.error(f"[{base_id}] Ошибка при формировании ежеквартального отчёта: {e}")


def start_scheduler() -> None:
    """Регистрирует задачи и запускает планировщик."""

    # Ежемесячно — 1-го числа в 06:00 (обрабатывает прошлый месяц)
    scheduler.add_job(
        _generate_monthly_reports,
        CronTrigger(day=1, hour=6, minute=0),
        id="monthly_reports",
        name="Ежемесячные отчёты",
        replace_existing=True,
    )

    # Ежеквартально — 1 января, апреля, июля, октября в 06:30 (обрабатывает прошлый квартал)
    scheduler.add_job(
        _generate_quarterly_reports,
        CronTrigger(month="1,4,7,10", day=1, hour=6, minute=30),
        id="quarterly_reports",
        name="Ежеквартальные отчёты",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Планировщик запущен")
