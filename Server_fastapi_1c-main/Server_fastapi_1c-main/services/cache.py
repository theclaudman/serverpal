"""
Кэш данных из 1С.
TTL-кэш в памяти. При переходе на несколько воркеров — заменить на Redis.
"""

import hashlib
from cachetools import TTLCache

# Кэши с разным временем жизни
_price_cache     = TTLCache(maxsize=50, ttl=300)    # 5 минут
_reference_cache = TTLCache(maxsize=50, ttl=1800)   # 30 минут
_dashboard_cache = TTLCache(maxsize=100, ttl=120)   # 2 минуты


def _make_key(*args) -> str:
    """Создаёт ключ кэша из аргументов."""
    raw = ":".join(str(a) for a in args)
    return hashlib.md5(raw.encode()).hexdigest()


def get_cached(cache_name: str, *key_parts):
    """Получить значение из кэша."""
    cache = _get_cache(cache_name)
    key = _make_key(*key_parts)
    return cache.get(key)


def set_cached(cache_name: str, value, *key_parts):
    """Сохранить значение в кэш."""
    cache = _get_cache(cache_name)
    key = _make_key(*key_parts)
    cache[key] = value


def clear_all():
    """Очистить все кэши."""
    _price_cache.clear()
    _reference_cache.clear()
    _dashboard_cache.clear()


def _get_cache(name: str) -> TTLCache:
    if name == "price":
        return _price_cache
    elif name == "reference":
        return _reference_cache
    elif name == "dashboard":
        return _dashboard_cache
    else:
        raise ValueError(f"Неизвестный кэш: {name}")