"""
anonymizer.py — обезличивание данных перед отправкой в облачные LLM

Два публичных интерфейса:

  mask_names(names, category, client_id)
    Принимает {guid: название}, возвращает {guid: псевдоним}.
    Используется для быстрой маскировки словаря контрагентов.

  mask_record(record, client_id)
    Принимает одну запись из 1С (dict), возвращает ту же запись
    с замаскированными чувствительными полями.
    Какие поля маскировать — читает из mask_config.json.

Два типа полей в mask_config.json:

  guid_ref   — поле содержит GUID ссылки на справочник (Контрагент_Key,
               Ответственный_Key и т.д.). Маскируется по GUID.
               Ключ реестра: "Контрагент::guid-abc-123"

  free_text  — поле содержит свободный текст (телефон, комментарий и т.д.).
               Маскируется по значению.
               Ключ реестра: "Телефон::89001234567"

Добавление нового чувствительного поля — только в mask_config.json, код не трогать.

Реестр масок:
  data/clients/client_001/mask_registry.json
  Структура: {"Контрагент::guid-abc": "Контрагент_001", ...}
  Персистентный: один ключ → один псевдоним навсегда.

Мультитенантность:
  client_id заложен под будущий SaaS — каждый клиент изолирован.
"""

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# Конфигурация по умолчанию — если mask_config.json не найден
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "fields": [
        {
            "source_field": "Контрагент_Key",
            "type": "guid_ref",
            "catalog": "Catalog_Контрагенты",
            "prefix": "Контрагент"
        },
        {
            "source_field": "Ответственный_Key",
            "type": "guid_ref",
            "catalog": "Catalog_Сотрудники",
            "prefix": "Сотрудник"
        }
    ],
    "mask_amounts": False
}

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------

BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "mask_config.json"


def _registry_path(client_id: str) -> Path:
    path = BASE_DIR / "data" / "clients" / client_id / "mask_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Загрузка / сохранение реестра
# ---------------------------------------------------------------------------

def _load_registry(client_id: str) -> dict:
    """
    Загружает реестр масок.
    Структура: {"Контрагент::guid-abc": "Контрагент_001"}

    Если реестр содержит старые ключи (из прошлых версий) —
    они не мешают работе, просто не совпадут с поиском.
    Для чистки: удали mask_registry.json, пересоздастся автоматически.
    """
    path = _registry_path(client_id)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_registry(client_id: str, registry: dict) -> None:
    path = _registry_path(client_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Загрузка конфигурации
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG


def _get_field_config(config: dict) -> list[dict]:
    """Возвращает список конфигураций полей из конфига."""
    return config.get("fields", [])


# ---------------------------------------------------------------------------
# Создание / получение маски
# ---------------------------------------------------------------------------

def _get_or_create_mask(registry_key: str, prefix: str,
                        registry: dict) -> str:
    """
    Возвращает псевдоним для ключа реестра.
    Если ключа нет — создаёт новый уникальный псевдоним.

    Счётчик по значениям с нужным префиксом —
    гарантирует уникальность даже при частичной загрузке реестра.
    """
    if registry_key in registry:
        return registry[registry_key]

    count = sum(
        1 for v in registry.values()
        if v.startswith(f"{prefix}_")
    )
    new_mask = f"{prefix}_{count + 1:03d}"
    registry[registry_key] = new_mask
    return new_mask


# ---------------------------------------------------------------------------
# Интерфейс 1 — маскировка словаря {guid: название}
# ---------------------------------------------------------------------------

def mask_names(names: dict[str, str],
               category: str = "Контрагент",
               client_id: str = "client_001") -> dict[str, str]:
    """
    Принимает {guid: реальное_название}, возвращает {guid: псевдоним}.

    Используется в aggregator для быстрой маскировки словаря контрагентов
    до построения агрегированного текста.

    Маскировка по GUID — не по тексту имени.
    РосСельхоз Банк (без ООО) маскируется так же надёжно как ООО СтройГрупп.

    Аргументы:
      names     — {guid: название} из aggregator
      category  — префикс (например "Контрагент")
      client_id — изоляция реестров для SaaS
    """
    if not names:
        return {}

    config   = _load_config()
    registry = _load_registry(client_id)

    # Ищем префикс для категории в конфиге
    prefix = category  # fallback — используем category как префикс напрямую
    for field_cfg in _get_field_config(config):
        if (field_cfg.get("source_field") == category or
                field_cfg.get("prefix") == category):
            prefix = field_cfg["prefix"]
            break

    masked = {}
    for guid, real_name in names.items():
        if not guid:
            masked[guid] = real_name
            continue
        registry_key = f"{prefix}::{guid}"
        mask = _get_or_create_mask(registry_key, prefix, registry)
        masked[guid] = mask

    _save_registry(client_id, registry)
    return masked


# ---------------------------------------------------------------------------
# Интерфейс 2 — маскировка одной записи из 1С
# ---------------------------------------------------------------------------

def mask_record(record: dict,
                client_id: str = "client_001") -> dict:
    """
    Принимает одну запись из 1С (словарь полей).
    Возвращает ту же запись с замаскированными чувствительными полями.

    Какие поля маскировать — читает из mask_config.json.
    Добавить новое поле = одна запись в конфиге, код не трогать.

    Типы маскировки:
      guid_ref  — поле содержит GUID (Контрагент_Key, Ответственный_Key)
                  ключ реестра: "Контрагент::guid-abc-123"
      free_text — поле содержит свободный текст (телефон, комментарий)
                  ключ реестра: "Телефон::89001234567"

    Пример:
      запись  = {"Контрагент_Key": "guid-abc", "СуммаДокумента": 50000}
      результат = {"Контрагент_Key": "Контрагент_001", "СуммаДокумента": 50000}
    """
    if not record:
        return record

    config   = _load_config()
    registry = _load_registry(client_id)
    fields   = _get_field_config(config)

    # Индекс: source_field → конфиг поля
    field_index = {f["source_field"]: f for f in fields}

    result = dict(record)  # копия — не мутируем оригинал

    for field_name, field_cfg in field_index.items():
        if field_name not in result:
            continue

        value  = result[field_name]
        prefix = field_cfg["prefix"]
        ftype  = field_cfg.get("type", "guid_ref")

        if not value:
            continue

        if ftype == "guid_ref":
            registry_key = f"{prefix}::{value}"
            result[field_name] = _get_or_create_mask(
                registry_key, prefix, registry
            )

        elif ftype == "free_text":
            registry_key = f"{prefix}::{value}"
            result[field_name] = _get_or_create_mask(
                registry_key, prefix, registry
            )

    _save_registry(client_id, registry)
    return result


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def print_registry(client_id: str = "client_001") -> None:
    """Выводит текущий реестр для дебага."""
    registry = _load_registry(client_id)
    if not registry:
        print(f"Реестр для {client_id} пуст.")
        return

    print(f"Реестр масок ({client_id}) — {len(registry)} записей:")

    by_category: dict[str, list] = {}
    for key, mask in sorted(registry.items(), key=lambda x: x[1]):
        if "::" in key:
            cat, val = key.split("::", 1)
        else:
            cat, val = "?", key
        by_category.setdefault(cat, []).append((val, mask))

    for cat, entries in by_category.items():
        print(f"\n  [{cat}]")
        for val, mask in entries:
            short_val = val[:12] + "..." if len(val) > 12 else val
            print(f"  {mask:20s} → {short_val}")


def clear_registry(client_id: str = "client_001") -> None:
    """
    Удаляет реестр масок.
    При следующем прогоне пересоздастся с чистого листа.
    Используй если реестр засорён старыми записями.
    """
    path = _registry_path(client_id)
    if path.exists():
        path.unlink()
        print(f"✅ Реестр {client_id} удалён: {path}")
    else:
        print(f"Реестр {client_id} не существует: {path}")


# ---------------------------------------------------------------------------
# Точка входа для ручного теста
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print(f"✅ Создан mask_config.json\n")

    print("=" * 60)
    print("ТЕСТ mask_names — маскировка словаря контрагентов")
    print("=" * 60)

    test_names = {
        "guid-aaa-001": "ООО СтройГрупп",
        "guid-bbb-002": "ИП Харченко Василий Иванович",
        "guid-ccc-003": "РосСельхоз Банк",    # без ООО/ИП — должен маскироваться
        "guid-ddd-004": "Сбербанк",            # тоже без префикса
    }

    masked = mask_names(test_names, category="Контрагент", client_id="client_test")

    for guid, name in test_names.items():
        print(f"  {name:35s} → {masked[guid]}")

    print("\n" + "=" * 60)
    print("ТЕСТ mask_record — маскировка записи из 1С")
    print("=" * 60)

    test_record = {
        "Date":               "2026-04-22T10:00:00",
        "Number":             "РН-001234",
        "Контрагент_Key":     "guid-aaa-001",
        "Ответственный_Key":  "guid-emp-001",
        "СуммаДокумента":     150000,
        "Posted":             True,
    }

    print("Исходная запись:")
    for k, v in test_record.items():
        print(f"  {k}: {v}")

    masked_record = mask_record(test_record, client_id="client_test")

    print("\nЗамаскированная запись:")
    for k, v in masked_record.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("ТЕСТ персистентности — повторный вызов даёт те же маски")
    print("=" * 60)

    masked2 = mask_record(test_record, client_id="client_test")
    if masked_record == masked2:
        print("✅ Персистентность работает")
    else:
        print("❌ Ошибка — маски отличаются!")

    print("\n" + "=" * 60)
    print("РЕЕСТР МАСОК:")
    print_registry("client_test")

    print("\n" + "=" * 60)
    print("Чистка тестового реестра...")
    clear_registry("client_test")
