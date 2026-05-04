"""
context_builder.py — кэш контекста данных из 1С

Обёртка над build_layer1() с кэшированием.
Ключ: {base_url}:{date}
TTL: 4 часа — руководитель утром получил дайджест, до обеда задаёт вопросы.

Хранит:
  - aggregated_text (то что уходит в LLM)
  - real_names (для демаскировки)
  - digest_text (последний дайджест)
  - timestamp создания

Сейчас: dict в памяти.
Потом: Redis. Интерфейс не изменится.
"""

from datetime import datetime, timedelta
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Структура записи кэша
# ---------------------------------------------------------------------------

@dataclass
class ContextEntry:
    """Одна запись кэша — данные за одну дату для одного клиента."""
    aggregated_text: str
    real_names: dict
    created_at: datetime
    digest_text: str = ""          # заполняется после генерации дайджеста
    anonymized: bool = False


# ---------------------------------------------------------------------------
# Кэш
# ---------------------------------------------------------------------------

# TTL по умолчанию — 4 часа
DEFAULT_TTL = timedelta(hours=4)

# In-memory хранилище: {cache_key: ContextEntry}
_cache: dict[str, ContextEntry] = {}


def _make_key(base_url: str, date_str: str) -> str:
    """Ключ кэша: base_url:date."""
    return f"{base_url}:{date_str}"


def get_context(base_url: str, date_str: str,
                ttl: timedelta = DEFAULT_TTL) -> ContextEntry | None:
    """
    Возвращает запись кэша если она свежая (< TTL).
    Если протухла или не существует — None.
    """
    key = _make_key(base_url, date_str)
    entry = _cache.get(key)

    if entry is None:
        return None

    age = datetime.now() - entry.created_at
    if age > ttl:
        # Протух — удаляем
        del _cache[key]
        return None

    return entry


def set_context(base_url: str, date_str: str,
                aggregated_text: str, real_names: dict,
                anonymized: bool = False) -> ContextEntry:
    """
    Сохраняет контекст в кэш.
    Вызывается после build_layer1().
    """
    key = _make_key(base_url, date_str)
    entry = ContextEntry(
        aggregated_text=aggregated_text,
        real_names=real_names,
        created_at=datetime.now(),
        anonymized=anonymized,
    )
    _cache[key] = entry
    return entry


def set_digest_text(base_url: str, date_str: str,
                    digest_text: str) -> None:
    """
    Сохраняет текст дайджеста в существующую запись кэша.
    Вызывается после получения ответа LLM.
    """
    key = _make_key(base_url, date_str)
    entry = _cache.get(key)
    if entry:
        entry.digest_text = digest_text


def get_context_age_minutes(base_url: str, date_str: str) -> int:
    """Сколько минут прошло с последней загрузки данных."""
    key = _make_key(base_url, date_str)
    entry = _cache.get(key)
    if entry is None:
        return -1
    age = datetime.now() - entry.created_at
    return int(age.total_seconds() / 60)


def clear_cache() -> None:
    """Очистка кэша — для тестов."""
    _cache.clear()
