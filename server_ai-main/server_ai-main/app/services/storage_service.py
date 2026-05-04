from pathlib import Path
from datetime import date
from app.core.config import settings


REPORT_DIRS = {
    "daily":     "daily_reports",
    "weekly":    "weekly_reports",
    "monthly":   "monthly_reports",
    "quarterly": "quarterly_reports",
}


def get_base_dir(base_id: str) -> Path:
    """Возвращает корневую папку базы, создаёт если не существует."""
    path = settings.data_dir / base_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_report_dir(base_id: str, report_type: str) -> Path:
    """Возвращает папку для конкретного типа отчётов базы."""
    dir_name = REPORT_DIRS[report_type]
    path = get_base_dir(base_id) / dir_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_report(base_id: str, report_type: str, content: str, report_date: date | None = None) -> Path:
    """
    Сохраняет отчёт в файл.
    Имя файла: report_YYYY-MM-DD.md
    Возвращает путь к сохранённому файлу.
    """
    if report_date is None:
        report_date = date.today()

    report_dir = get_report_dir(base_id, report_type)
    filename = f"report_{report_date.isoformat()}.md"
    file_path = report_dir / filename

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


def load_report(base_id: str, report_type: str, report_date: date) -> str | None:
    """
    Загружает отчёт из файла по дате.
    Возвращает содержимое или None если файл не найден.
    """
    report_dir = get_report_dir(base_id, report_type)
    filename = f"report_{report_date.isoformat()}.md"
    file_path = report_dir / filename

    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def list_reports(base_id: str, report_type: str) -> list[str]:
    """Возвращает список файлов отчётов данного типа для базы."""
    report_dir = get_report_dir(base_id, report_type)
    return sorted(p.name for p in report_dir.glob("report_*.md"))
