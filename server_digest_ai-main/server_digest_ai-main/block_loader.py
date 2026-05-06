"""
block_loader.py — универсальный загрузчик блоков данных

Читает YAML-конфиг блока, выполняет полный цикл:
  загрузка из 1С → резолв GUIDов → маскировка → агрегация → текст

Публичный интерфейс:

  load_all_blocks(blocks_dir) -> list[BlockConfig]
      Загружает все YAML-конфиги из папки, сортирует по priority.

  fetch_block(config, connection, date_from, date_to) -> list[dict]
      Загружает сырые записи из 1С по конфигу.

  resolve_block(records, config, connection) -> dict[str, dict[str, str]]
      Резолвит GUIDы в названия. Возвращает {field: {guid: name}}.

  mask_block(records, config, client_id) -> list[dict]
      Маскирует чувствительные поля.

  aggregate_block(records, config, resolved_names, extras) -> dict
      Агрегирует записи по стратегии из конфига.

  format_block(aggregated, config) -> str
      Форматирует результат агрегации в текст по шаблону.

  process_block(config, connection, date_from, date_to,
                anonymize, client_id, extras) -> BlockResult
      Полный цикл для одного блока.

Добавление нового блока = новый YAML в blocks/. Код не трогать.
Добавление нового типа агрегации = новая функция _agg_<type>().
"""

import yaml
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field

from onec_client import _get, _fmt_date, fetch_names_by_guids


# ---------------------------------------------------------------------------
# Структуры данных
# ---------------------------------------------------------------------------

@dataclass
class BlockConfig:
    """Распарсенный YAML-конфиг блока."""
    id: str
    name: str
    enabled: bool
    priority: int | None        # None = вспомогательный блок
    source: dict
    resolve: list
    mask: list
    aggregation: dict
    template: str | None
    hide_if_empty: bool
    depends_on: list
    raw: dict                   # оригинальный YAML для дебага


@dataclass
class BlockResult:
    """Результат обработки одного блока."""
    config: BlockConfig
    records_raw: list           # сырые записи из 1С
    records_pre_resolve: list   # записи до резолва (чистые GUIDы)
    records_masked: list        # записи после маскировки (= records_raw если anonymize=False)
    resolved_names: dict        # {field: {guid: name}}
    aggregated: dict            # результат агрегации
    text: str                   # готовый текст для LLM
    record_count: int           # сколько записей загружено



@dataclass
class Connection:
    """Параметры подключения к 1С."""
    base_url: str
    login: str
    password: str


# ---------------------------------------------------------------------------
# Загрузка конфигов
# ---------------------------------------------------------------------------

def load_all_blocks(blocks_dir: str | Path) -> list[BlockConfig]:
    """
    Загружает все YAML-конфиги из папки.
    Возвращает список, отсортированный по priority.
    Блоки с enabled=False пропускаются.
    """
    blocks_dir = Path(blocks_dir)
    if not blocks_dir.exists():
        raise FileNotFoundError(f"Папка блоков не найдена: {blocks_dir}")

    configs = []
    for yaml_file in sorted(blocks_dir.glob("*.yaml")):
        with open(yaml_file, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw.get("enabled", True):
            continue

        config = BlockConfig(
            id=raw["id"],
            name=raw.get("name", raw["id"]),
            enabled=raw.get("enabled", True),
            priority=raw.get("priority"),
            source=raw.get("source", {}),
            resolve=raw.get("resolve", []),
            mask=raw.get("mask", []),
            aggregation=raw.get("aggregation", {}),
            template=raw.get("template"),
            hide_if_empty=raw.get("hide_if_empty", True),
            depends_on=raw.get("depends_on", []),
            raw=raw,
        )
        configs.append(config)

    # Сортировка: вспомогательные блоки (priority=None) — в конец
    configs.sort(key=lambda c: (c.priority is None, c.priority or 999))
    return configs


# ---------------------------------------------------------------------------
# Загрузка данных из 1С
# ---------------------------------------------------------------------------

def _build_period_filter(period: str, date_from: datetime,
                         date_to: datetime) -> str | None:
    """
    Строит OData-фильтр по дате в зависимости от типа периода.

    period:
      none      — без фильтра по дате (остатки на сейчас)
      yesterday  — date_from..date_to (передаётся извне)
      7d / 14d / 30d / 90d — последние N дней от сегодня
      mtd        — с начала текущего месяца
    """
    if not period or period == "none":
        return None

    if period == "yesterday":
        return (f"Date ge {_fmt_date(date_from)} "
                f"and Date le {_fmt_date(date_to)}")

    # Nд — последние N дней
    if period.endswith("d") and period[:-1].isdigit():
        days = int(period[:-1])
        start = datetime.now() - timedelta(days=days)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime.now()
        return (f"Date ge {_fmt_date(start)} "
                f"and Date le {_fmt_date(end)}")

    # mtd — с начала месяца
    if period == "mtd":
        start = datetime.now().replace(day=1, hour=0, minute=0,
                                       second=0, microsecond=0)
        end = datetime.now()
        return (f"Date ge {_fmt_date(start)} "
                f"and Date le {_fmt_date(end)}")

    return None


def fetch_block(config: BlockConfig, conn: Connection,
                date_from: datetime, date_to: datetime) -> list[dict]:
    """
    Загружает сырые записи из 1С по конфигу блока.
    """
    source = config.source
    entity = source["entity"]

    params = {}

    # $select
    fields = source.get("fields", [])
    if fields:
        params["$select"] = ",".join(fields)

    # $filter — комбинируем период + пользовательский фильтр
    filters = []

    period = source.get("period", "none")
    period_filter = _build_period_filter(period, date_from, date_to)
    if period_filter:
        filters.append(period_filter)

    user_filter = source.get("filter")
    if user_filter:
        filters.append(user_filter)

    if filters:
        params["$filter"] = " and ".join(filters)

    # $orderby
    orderby = source.get("orderby")
    if orderby:
        params["$orderby"] = orderby
    # $top
    top = source.get("top")
    if top:
        params["$top"] = str(top)

        
    return _get(conn.base_url, conn.login, conn.password, entity, params)
def _apply_compute(records: list[dict], config: BlockConfig) -> list[dict]:
    rules = config.raw.get("compute", [])
    if not rules:
        return records

    for rec in records:
        for rule in rules:
            op = rule["op"]
            
            if op == "days_from_today":
                date_str = rec.get(rule["a"], "")
                try:
                    from datetime import date as _date
                    doc_date = datetime.fromisoformat(date_str).date()
                    rec[rule["name"]] = (_date.today() - doc_date).days
                except Exception:
                    rec[rule["name"]] = -1
                continue  # ← важно, пропускаем float-логику ниже
            
            a = float(rec.get(rule["a"], 0))
            b = float(rec.get(rule["b"], 0))
            if op == "add":
                rec[rule["name"]] = a + b
            elif op == "subtract":
                rec[rule["name"]] = a - b
            elif op == "multiply":
                rec[rule["name"]] = a * b
            elif op == "divide":
                rec[rule["name"]] = a / b if b else 0

    return records

def _apply_join_parent(records: list[dict], config: BlockConfig,
                       extras: dict) -> list[dict]:
    """
    Приклеивает поля из родительского блока по Ref_Key.
    Например: строки _Запасы получают Date из шапки накладной.
    """
    if not config.depends_on:
        return records

    for dep in config.depends_on:
        if dep.get("merge") != "join_parent":
            continue

        dep_block_id = dep["block"]
        match_field = dep["match_field"]       # поле в дочерних записях (Ref_Key)
        parent_field = dep["parent_field"]      # поле в родителе (Ref_Key)
        copy_fields = dep.get("copy_fields", [])  # какие поля скопировать

        parent_records = extras.get(dep_block_id, [])
        if not parent_records:
            continue

        # Индекс: {parent_ref_key: запись}
        parent_index = {}
        for prec in parent_records:
            key = prec.get(parent_field, "")
            if key:
                parent_index[key] = prec

        # Приклеиваем поля
        enriched = []
        for rec in records:
            rec_copy = dict(rec)
            parent_key = rec_copy.get(match_field, "")
            parent = parent_index.get(parent_key)
            if parent:
                for cf in copy_fields:
                    rec_copy[cf] = parent.get(cf, "")
            enriched.append(rec_copy)

        records = enriched
        # Фильтруем: оставляем только записи, у которых нашёлся родитель
        if dep.get("filter_unmatched", True):
            records = [r for r in records if r.get(copy_fields[0], "")]
    return records

# ---------------------------------------------------------------------------
# Резолв GUIDов в названия
# ---------------------------------------------------------------------------

def resolve_block(records: list[dict], config: BlockConfig,
                  conn: Connection,
                  batch_size: int = 50) -> dict[str, dict[str, str]]:
    """
    Резолвит GUID-поля в человеческие названия.
    Возвращает {field_name: {guid: name}}.

    Пример:
      {"Контрагент_Key": {"guid-abc": "ООО Ромашка", ...}}
    """
    if not config.resolve:
        return {}

    resolved = {}
    for res_cfg in config.resolve:
        field_name = res_cfg["field"]
        catalog = res_cfg["catalog"]

        # Собираем уникальные GUIDы из этого поля
        guids = set()
        for rec in records:
            val = rec.get(field_name, "")
            if val and val != "00000000-0000-0000-0000-000000000000":
                guids.add(val)

        if not guids:
            resolved[field_name] = {}
            continue

        # Загружаем названия батчами по 50
        names = {}
        guids_list = list(guids)
        for i in range(0, len(guids_list), batch_size):
            batch = guids_list[i:i + batch_size]
            names.update(
                fetch_names_by_guids(conn.base_url, conn.login,
                                     conn.password, catalog, batch)
            )

        resolved[field_name] = names

    return resolved


# ---------------------------------------------------------------------------
# Маскировка
# ---------------------------------------------------------------------------

def mask_block(records: list[dict], config: BlockConfig,
               client_id: str) -> list[dict]:
    """
    Маскирует чувствительные поля записей по конфигу блока.
    Использует anonymizer.mask_record — единый реестр масок.
    """
    if not config.mask:
        return records

    from anonymizer import mask_record
    return [mask_record(rec, client_id) for rec in records]


def build_mask_names(records: list[dict], config: BlockConfig,
                     resolved_names: dict,
                     client_id: str) -> dict[str, dict[str, str]]:
    """
    Строит словарь {field: {guid: псевдоним}} для агрегации
    замаскированных записей.
    Нужен чтобы в агрегации использовать псевдонимы как ключи группировки.
    """
    if not config.mask:
        return {}

    from anonymizer import mask_names as _mask_names

    masked_names = {}
    for mask_cfg in config.mask:
        field_name = mask_cfg["field"]
        prefix = mask_cfg["prefix"]

        # Берём реальные названия для этого поля
        real = resolved_names.get(field_name, {})
        if not real:
            continue

        # mask_names возвращает {guid: псевдоним}
        masked = _mask_names(real, category=prefix, client_id=client_id)
        masked_names[field_name] = masked

    return masked_names


# ---------------------------------------------------------------------------
# Форматирование чисел
# ---------------------------------------------------------------------------

def _fmt_money(value) -> str:
    """106000000 → '106 000 000 ₽'"""
    try:
        return f"{float(value):,.0f} ₽".replace(",", " ")
    except Exception:
        return str(value)


def _fmt_qty(value) -> str:
    """42.0 → '42', 3.75 → '3.75'"""
    try:
        v = float(value)
        return str(int(v)) if v == int(v) else f"{v:.2f}"
    except Exception:
        return str(value)


# ---------------------------------------------------------------------------
# Агрегация — стратегии
# ---------------------------------------------------------------------------

def _agg_total_by_field(records: list[dict], config: BlockConfig,
                        names: dict) -> dict:
    """
    Суммирует по полю группировки.
    Пример: деньги по типу (наличные / безналичные).
    """
    agg = config.aggregation
    sum_field = agg["sum_field"]
    group_by = agg.get("group_by")

    total = 0.0
    by_group = defaultdict(float)

    for rec in records:
        val = float(rec.get(sum_field, 0))
        total += val
        if group_by:
            key = rec.get(group_by, "Прочее")
            by_group[key] += val

    rows = sorted(by_group.items(), key=lambda x: x[1], reverse=True)

    return {"total": total, "rows": rows, "count": len(records)}


def _agg_group_sum(records: list[dict], config: BlockConfig,
                   names: dict) -> dict:
    """
    Группирует по полю, суммирует, берёт топ-N.
    Пример: дебиторка по контрагентам.
    """
    agg = config.aggregation
    sum_field = agg["sum_field"]
    group_by = agg["group_by"]
    max_rows = agg.get("max_rows")

    total = 0.0
    by_group = defaultdict(float)

    # Какой словарь названий использовать для этого поля
    field_names = names.get(group_by, {})

    for rec in records:
        val = float(rec.get(sum_field, 0))
        total += val
        key = rec.get(group_by, "")
        # Отображаемое имя: из resolved_names или сам ключ
        display_name = field_names.get(key, key)
        by_group[display_name] += val

    top = sorted(by_group.items(), key=lambda x: x[1], reverse=True)
    count = len(by_group)

    if max_rows:
        top = top[:max_rows]

    return {"total": total, "count": count, "top_items": top}


def _agg_classify(records: list[dict], config: BlockConfig,
                  names: dict, extras: dict) -> dict:
    """
    Классифицирует записи по порогам: critical / at_risk / top.
    Используется для остатков на складе.
    extras["order_items"] — записи заказов для расчёта резервов.
    """
    agg = config.aggregation
    physical_field = agg["physical_field"]
    item_field = agg["item_field"]
    threshold = agg.get("low_threshold", 0.10)
    max_rows = agg.get("max_rows", 20)

    # Суммируем физический остаток по номенклатуре
    physical = defaultdict(float)
    for rec in records:
        guid = rec.get(item_field, "")
        if guid:
            physical[guid] += float(rec.get(physical_field, 0))

    # Суммируем резервы из зависимого блока
    reserved = defaultdict(float)
    deps = config.depends_on
    if deps:
        dep = deps[0]  # пока поддерживаем одну зависимость
        dep_block_id = dep["block"]
        match_field = dep["match_field"]
        reserve_field = dep["reserve_field"]

        dep_records = extras.get(dep_block_id, [])
        for item in dep_records:
            guid = item.get(match_field, "")
            if guid:
                reserved[guid] += float(item.get(reserve_field, 0))

    # Считаем свободный остаток
    items = []
    for guid, qty_phys in physical.items():
        qty_res = reserved.get(guid, 0.0)
        qty_free = qty_phys - qty_res
        items.append({
            "guid": guid,
            "qty_physical": qty_phys,
            "qty_reserved": qty_res,
            "qty_free": qty_free,
        })

    # Классификация
    field_names = names.get(item_field, {})

    def _name(guid):
        return field_names.get(guid, guid[:8] + "...")

    critical = [i for i in items if i["qty_free"] <= 0]
    at_risk = [i for i in items
               if i["qty_free"] > 0
               and i["qty_physical"] > 0
               and (i["qty_free"] / i["qty_physical"]) < threshold]
    rest = [i for i in items
            if i not in critical and i not in at_risk]
    top = sorted(rest, key=lambda x: x["qty_physical"], reverse=True)
    if max_rows:
        top = top[:max_rows]

    return {
        "critical": critical,
        "at_risk": at_risk,
        "top": top,
        "names": field_names,
        "total_positions": len(items),
    }


def _agg_list(records: list[dict], config: BlockConfig,
              names: dict) -> dict:
    """
    Список записей без группировки.
    Каждая запись важна (возвраты, рекламации).
    """
    max_rows = config.aggregation.get("max_rows")
    items = records[:max_rows] if max_rows else records
    return {"items": items, "count": len(records)}

def _agg_list_top(records: list[dict], config: BlockConfig,
                  names: dict) -> dict:
    """
    Топ-N записей по полю сортировки.
    Каждая запись выводится отдельно — с датой, суммой, контрагентом.
    Используется для просроченной дебиторки.
    """
    agg = config.aggregation
    sort_field = agg.get("sort_by", "СуммаBalance")
    max_rows = agg.get("max_rows", 30)
    display_fields = agg.get("display_fields", [])

    # Сортируем по убыванию sort_field
    try:
        sorted_records = sorted(
            records,
            key=lambda r: float(r.get(sort_field, 0)),
            reverse=True
        )
    except Exception:
        sorted_records = records

    top = sorted_records[:max_rows]

    # Для каждой записи строим display_name из resolved_names
    field_names = {}
    for field_name, nmap in names.items():
        field_names[field_name] = nmap

    items = []
    for rec in top:
        item = {}
        for f in display_fields:
            val = rec.get(f, "")
            # Пробуем резолвить GUID
            resolved = field_names.get(f, {}).get(val, val)
            item[f] = resolved
        items.append(item)

    total = sum(float(r.get(sort_field, 0)) for r in records)
    return {"items": items, "count": len(records), "total": total,
            "display_fields": display_fields}

def _agg_time_series(records: list[dict], config: BlockConfig,
                     names: dict) -> dict:
    """
    Временной ряд — группировка по дате.
    Пример: выручка по дням за 30 дней.
    """
    agg = config.aggregation
    date_field = agg.get("date_field", "Date")
    sum_field = agg.get("sum_field", "СуммаДокумента")

    by_date = defaultdict(float)
    for rec in records:
        date_str = rec.get(date_field, "")[:10]  # YYYY-MM-DD
        val = float(rec.get(sum_field, 0))
        by_date[date_str] += val

    # Сортировка по дате
    series = sorted(by_date.items())
    total = sum(v for _, v in series)

    return {"series": series, "total": total, "count": len(records)}


def _agg_none(records: list[dict], config: BlockConfig,
              names: dict) -> dict:
    """Без агрегации — вспомогательный блок."""
    return {"records": records, "count": len(records)}


# Реестр стратегий агрегации
_AGG_REGISTRY = {
    "total_by_field": _agg_total_by_field,
    "group_sum":      _agg_group_sum,
    "classify":       _agg_classify,
    "list_top":       _agg_list_top,
    "list":           _agg_list,
    "time_series":    _agg_time_series,
    "none":           _agg_none,
}


def aggregate_block(records: list[dict], config: BlockConfig,
                    resolved_names: dict,
                    extras: dict = None) -> dict:
    """
    Агрегирует записи по стратегии из конфига.
    resolved_names: {field: {guid: name}} — для отображения.
    extras: {"order_items": [...]} — данные зависимых блоков.
    """
    agg_type = config.aggregation.get("type", "none")

    if agg_type not in _AGG_REGISTRY:
        raise ValueError(
            f"Неизвестный тип агрегации: '{agg_type}' в блоке '{config.id}'.\n"
            f"Доступные: {', '.join(_AGG_REGISTRY.keys())}"
        )

    fn = _AGG_REGISTRY[agg_type]

    # classify принимает extras
    if agg_type == "classify":
        return fn(records, config, resolved_names, extras or {})
    else:
        return fn(records, config, resolved_names)


# ---------------------------------------------------------------------------
# Форматирование текста
# ---------------------------------------------------------------------------

def format_block(aggregated: dict, config: BlockConfig,
                 period_label: str = "") -> str:
    """
    Форматирует результат агрегации в текст по шаблону из конфига.
    Если записей нет и hide_if_empty=True — возвращает None.
    """
    agg_type = config.aggregation.get("type", "none")

    # Проверка пустоты
    is_empty = False
    if agg_type == "group_sum":
        is_empty = aggregated.get("count", 0) == 0
    elif agg_type == "total_by_field":
        is_empty = aggregated.get("count", 0) == 0
    elif agg_type == "list":
        is_empty = aggregated.get("count", 0) == 0
    elif agg_type == "list_top":
        is_empty = aggregated.get("count", 0) == 0        
    elif agg_type == "time_series":
        is_empty = len(aggregated.get("series", [])) == 0
    elif agg_type == "classify":
        is_empty = aggregated.get("total_positions", 0) == 0

    if is_empty and config.hide_if_empty:
        return None

    # Форматирование по типу агрегации
    if agg_type == "total_by_field":
        return _format_total_by_field(aggregated, config)
    elif agg_type == "group_sum":
        return _format_group_sum(aggregated, config, period_label)
    elif agg_type == "classify":
        return _format_classify(aggregated, config)
    elif agg_type == "list":
        return _format_list(aggregated, config)
    elif agg_type == "list_top":
        return _format_list_top(aggregated, config)        
    elif agg_type == "time_series":
        return _format_time_series(aggregated, config)
    elif agg_type == "none":
        return None  # вспомогательный блок — текста нет
    # В format_block добавить ветки (после строки 648):
    elif agg_type == "list_top":
        is_empty = aggregated.get("count", 0) == 0
        # ...и в форматировании:
    elif agg_type == "list_top":
        return _format_list_top(aggregated, config)

    return None

def _format_list_top(data: dict, config: BlockConfig) -> str:
    items = data.get("items", [])
    if not items:
        return None

    total = data.get("total", 0)
    count = data.get("count", 0)

    lines = [
        f"ПРОСРОЧЕННАЯ ДЕБИТОРКА: {_fmt_money(total)} "
        f"({count} накладных, топ {len(items)} по сумме)"
    ]
    for item in items:
        контрагент = item.get("Контрагент_Key", "?")
        number     = item.get("Number", "?")
        date_str   = item.get("Date", "")[:10]  # только дата без времени
        сумма      = _fmt_money(item.get("СуммаBalance", 0))
        дней       = item.get("ДнейПросрочки", "?")
        lines.append(
            f"  {контрагент} | {number} от {date_str} | {сумма} | {дней} дн."
        )
    return "\n".join(lines)
    
def _format_total_by_field(data: dict, config: BlockConfig) -> str:
    lines = [f"{config.name.upper()}: {_fmt_money(data['total'])}"]
    for key, val in data["rows"]:
        lines.append(f"  {key}: {_fmt_money(val)}")
    return "\n".join(lines)

# Новая функция форматирования — добавить рядом с остальными _format_*:
def _format_list_top(data: dict, config: BlockConfig) -> str:
    items = data.get("items", [])
    display_fields = data.get("display_fields", [])
    total = data.get("total", 0)
    count = data.get("count", 0)

    lines = [f"{config.name.upper()}: {_fmt_money(total)} ({count} строк, топ {len(items)})"]
    for item in items:
        parts = []
        for f in display_fields:
            val = item.get(f, "")
            # Деньги форматируем красиво
            if "Сумма" in f or "Balance" in f:
                try:
                    parts.append(f"{f}: {_fmt_money(val)}")
                    continue
                except Exception:
                    pass
            if "Дней" in f:
                parts.append(f"{val} дн.")
                continue
            parts.append(f"{val}")
        lines.append("  " + " | ".join(parts))
    return "\n".join(lines)


def _format_group_sum(data: dict, config: BlockConfig,
                      period_label: str = "") -> str:
    total_str = _fmt_money(data["total"])
    count = data["count"]

    # Заголовок
    if period_label and config.id == "sales":
        header = f"ПРОДАЖИ ({period_label}): {total_str}, накладных: {data.get('count', 0)}"
    else:
        header = f"{config.name.upper()}: {total_str} ({count} контрагентов)"

    lines = [header]
    if data["top_items"]:
        lines.append("  Крупнейшие:")
        for name, amount in data["top_items"]:
            lines.append(f"    {name}: {_fmt_money(amount)}")
    return "\n".join(lines)


def _format_classify(data: dict, config: BlockConfig) -> str:
    names = data.get("names", {})

    def _name(guid):
        return names.get(guid, guid[:8] + "...")

    lines = []

    critical = data["critical"]
    if critical:
        lines.append(f"КРИТИЧНЫЕ ОСТАТКИ ({len(critical)} позиций — "
                      f"заказов больше чем на складе):")
        for item in critical:
            lines.append(
                f"  ⚠️  {_name(item['guid'])}: "
                f"на складе {_fmt_qty(item['qty_physical'])}, "
                f"в заказах {_fmt_qty(item['qty_reserved'])}, "
                f"свободно {_fmt_qty(item['qty_free'])}"
            )
    else:
        lines.append("КРИТИЧНЫЕ ОСТАТКИ: нет")

    at_risk = data["at_risk"]
    if at_risk:
        lines.append(f"\nПОД УГРОЗОЙ ({len(at_risk)} позиций — свободно < 10%):")
        for item in at_risk[:10]:
            pct = int(item["qty_free"] / item["qty_physical"] * 100) \
                if item["qty_physical"] else 0
            lines.append(
                f"  {_name(item['guid'])}: "
                f"всего {_fmt_qty(item['qty_physical'])}, "
                f"свободно {_fmt_qty(item['qty_free'])} ({pct}%)"
            )
        if len(at_risk) > 10:
            lines.append(f"  ...и ещё {len(at_risk) - 10} позиций")
    else:
        lines.append("\nПОД УГРОЗОЙ: нет")

    top = data["top"]
    if top:
        lines.append(f"\nТОП ОСТАТКОВ (по количеству):")
        for item in top[:10]:
            lines.append(
                f"  {_name(item['guid'])}: "
                f"{_fmt_qty(item['qty_physical'])} шт "
                f"(свободно {_fmt_qty(item['qty_free'])})"
            )

    return "\n".join(lines)


def _format_list(data: dict, config: BlockConfig) -> str:
    lines = [f"{config.name.upper()} ({data['count']} записей):"]
    for item in data["items"]:
        # Универсальный вывод всех полей записи
        parts = []
        for k, v in item.items():
            if k.startswith("odata") or k == "Ref_Key":
                continue
            parts.append(f"{k}: {v}")
        lines.append(f"  {' | '.join(parts)}")
    return "\n".join(lines)


def _format_time_series(data: dict, config: BlockConfig) -> str:
    count = data.get("count", 0)
    lines = [f"{config.name.upper()} (итого: {_fmt_money(data['total'])}, "
             f"записей: {count})"]
    for date_str, val in data["series"]:
        # YYYY-MM-DD → DD.MM
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            label = d.strftime("%d.%m")
        except Exception:
            label = date_str
        lines.append(f"  {label}: {_fmt_money(val)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Полный цикл обработки одного блока
# ---------------------------------------------------------------------------

def _resolve_after_classify(aggregated: dict, config: BlockConfig,
                            conn: Connection,
                            batch_size: int = 50) -> dict:
    """
    Отложенный резолв для classify-блоков.
    Резолвит GUIDы только для отобранных позиций (critical + at_risk + top),
    а не для всех 51 783 записей.
    """
    # Собираем GUIDы только из результата классификации
    guids_needed = set()
    for group in ("critical", "at_risk", "top"):
        for item in aggregated.get(group, []):
            guids_needed.add(item["guid"])

    guids_needed.discard("")
    if not guids_needed:
        return {}

    # Определяем справочник из конфига resolve
    if not config.resolve:
        return {}

    catalog = config.resolve[0]["catalog"]
    field_name = config.resolve[0]["field"]

    print(f"  [{config.id}] отложенный резолв: {len(guids_needed)} GUIDов "
          f"(вместо всех записей)")

    names = {}
    guids_list = list(guids_needed)
    for i in range(0, len(guids_list), batch_size):
        batch = guids_list[i:i + batch_size]
        names.update(
            fetch_names_by_guids(conn.base_url, conn.login,
                                 conn.password, catalog, batch)
        )

    # Записываем названия обратно в aggregated
    aggregated["names"] = names
    return {field_name: names}

def _debug_save(debug_dir: Path, block_id: str, filename: str, data, as_json: bool = False):
    """Сохраняет промежуточный файл в папку debug блока."""
    block_dir = debug_dir / "blocks" / block_id
    block_dir.mkdir(parents=True, exist_ok=True)
    path = block_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        if as_json:
            import json
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        elif isinstance(data, list):
            for rec in data:
                f.write(str(rec) + "\n")
        else:
            f.write(str(data))
    print(f"    🔍 {block_id}/{filename}")

def process_block(
    config: BlockConfig,
    conn: Connection,
    date_from: datetime,
    date_to: datetime,
    anonymize: bool = False,
    client_id: str = "client_001",
    extras: dict = None,
    prefetched: list[dict] = None,
    debug: bool = False,
    debug_dir: Path = None,
) -> BlockResult:
    """
    Полный цикл обработки одного блока:
      загрузка → резолв → маскировка → агрегация → текст.

    Для classify-блоков (остатки) резолв откладывается ПОСЛЕ агрегации —
    резолвятся только отобранные позиции, а не все записи.

    extras: {"order_items": [записи]} — данные зависимых блоков.
    prefetched: если данные уже загружены — не ходить в 1С повторно.
    """
    agg_type = config.aggregation.get("type", "none")

    # 1. Загрузка
    if prefetched is not None:
        records = prefetched
    else:
        records = fetch_block(config, conn, date_from, date_to)

    print(f"  [{config.id}] загружено записей: {len(records)}")
    if debug and debug_dir:
        _debug_save(debug_dir, config.id, "1_raw.json", records, as_json=True)
    # 1b. Join с родительским блоком (если есть)
    records = _apply_join_parent(records, config, extras or {})
    if debug and debug_dir and config.depends_on:
        has_join = any(d.get("merge") == "join_parent" for d in config.depends_on)
        if has_join:
            _debug_save(debug_dir, config.id, "5_joined.json", records, as_json=True)
    # Сохраняем копию до резолва
    import copy
    records_pre_resolve = copy.deepcopy(records)
    # 1c. Вычисления по полям (если есть compute в конфиге)
    records = _apply_compute(records, config)
    if debug and debug_dir and config.raw.get("compute"):
        _debug_save(debug_dir, config.id, "6_computed.json", records, as_json=True)
    # 2. Резолв GUIDов
    #    Для classify — пропускаем, сделаем после агрегации
    if agg_type == "classify":
        resolved_names = {}
        print(f"  [{config.id}] резолв отложен до после агрегации")
    else:
        resolved_names = resolve_block(records, config, conn)
        for field_name, names_dict in resolved_names.items():
            print(f"  [{config.id}] резолв {field_name}: {len(names_dict)} названий")
    if debug and debug_dir and resolved_names:
        resolved_text = []
        for rec in records:
            parts = []
            for k, v in rec.items():
                if k.startswith("odata"):
                    continue
                display = resolved_names.get(k, {}).get(v, v) if isinstance(v, str) else v
                parts.append(f"{k}: {display}")
            resolved_text.append(" | ".join(parts))
        _debug_save(debug_dir, config.id, "2_resolved.txt", "\n".join(resolved_text))

    # 3. Маскировка
    if anonymize and config.mask:
        records_masked = mask_block(records, config, client_id)
        masked_name_map = build_mask_names(
            records, config, resolved_names, client_id
        )
        names_for_agg = {}
        for field_name in resolved_names:
            if field_name in masked_name_map:
                names_for_agg[field_name] = {
                    v: v for v in masked_name_map[field_name].values()
                }
            else:
                names_for_agg[field_name] = resolved_names[field_name]
    else:
        records_masked = records
        names_for_agg = resolved_names
    if debug and debug_dir and anonymize and config.mask:
        _debug_save(debug_dir, config.id, "3_masked.json", records_masked, as_json=True)

    # 4. Агрегация
    aggregated = aggregate_block(
        records_masked, config, names_for_agg, extras
    )
    if debug and debug_dir:
        _debug_save(debug_dir, config.id, "7_aggregated_data.json", aggregated, as_json=True)
        
    # 4b. Отложенный резолв для classify
    if agg_type == "classify":
        deferred_names = _resolve_after_classify(aggregated, config, conn)
        resolved_names.update(deferred_names)

    # 5. Форматирование
    period_label = date_from.strftime("%d.%m.%Y") if date_from else ""
    text = format_block(aggregated, config, period_label)
    if debug and debug_dir and text:
        _debug_save(debug_dir, config.id, "10_formatted.txt", text)
    return BlockResult(
        config=config,
        records_raw=records,
        records_pre_resolve=records_pre_resolve,
        records_masked=records_masked,
        resolved_names=resolved_names,
        aggregated=aggregated,
        text=text,
        record_count=len(records),
    )


# ---------------------------------------------------------------------------
# Собрать все реальные названия из всех блоков (для деанонимизации)
# ---------------------------------------------------------------------------

def collect_real_names(results: list[BlockResult]) -> dict[str, str]:
    """
    Собирает {guid: реальное_название} из всех блоков.
    Используется для деанонимизации ответа LLM.
    """
    all_names = {}
    for result in results:
        for field_name, names_dict in result.resolved_names.items():
            all_names.update(names_dict)
    return all_names


# ---------------------------------------------------------------------------
# Точка входа для ручного теста
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    blocks_dir = Path(__file__).parent / "blocks"

    print("=" * 60)
    print("ТЕСТ block_loader.py")
    print("=" * 60)

    print(f"\nЗагрузка конфигов из {blocks_dir}...")
    try:
        configs = load_all_blocks(blocks_dir)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print(f"Загружено блоков: {len(configs)}\n")

    for cfg in configs:
        priority_str = str(cfg.priority) if cfg.priority else "вспом."
        agg_type = cfg.aggregation.get("type", "?")
        print(f"  [{priority_str}] {cfg.id:15s} | {cfg.name:15s} | "
              f"агрегация: {agg_type:15s} | "
              f"маскировка: {len(cfg.mask)} полей | "
              f"резолв: {len(cfg.resolve)} полей | "
              f"зависимости: {[d['block'] for d in cfg.depends_on]}")

    print(f"\n✅ Конфиги валидны")
    print(f"\nДля полного теста с 1С запусти:")
    print(f"  python block_loader.py --live")

    if "--live" in sys.argv:
        print("\n" + "=" * 60)
        print("LIVE-ТЕСТ — загрузка из 1С")
        print("=" * 60)

        conn = Connection(
            base_url="http://127.0.0.1/Eu/odata/standard.odata",
            login="admin_r",
            password="123",
        )

        from onec_client import check_connection
        if not check_connection(conn.base_url, conn.login, conn.password):
            print("❌ Нет подключения к 1С")
            sys.exit(1)

        yesterday = datetime.now() - timedelta(days=1)
        date_from = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)

        # Сначала загружаем вспомогательные блоки
        extras = {}
        for cfg in configs:
            if cfg.priority is None:
                result = process_block(cfg, conn, date_from, date_to)
                extras[cfg.id] = result.records_raw
                print(f"  Вспомогательный блок {cfg.id}: {result.record_count} записей")

        # Потом основные
        print()
        for cfg in configs:
            if cfg.priority is None:
                continue
            print(f"\n--- {cfg.name} ---")
            result = process_block(
                cfg, conn, date_from, date_to,
                extras=extras
            )
            if result.text:
                print(result.text)
            else:
                print("  (нет текста — пустой или вспомогательный блок)")
