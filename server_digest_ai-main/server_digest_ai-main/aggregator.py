"""
aggregator.py — агрегация сырых данных из 1С в компактный текст для LLM

НОВАЯ ВЕРСИЯ — на основе YAML-конфигов из папки blocks/.
Добавить новый блок данных = создать YAML в blocks/. Код не трогать.

Возвращает тот же кортеж что и раньше (совместимость с digest.py):
  (aggregated_text, raw_text, raw_masked_text, mask_log, real_names)

  aggregated_text — текст который идёт в LLM
  raw_text        — сырые данные с РЕАЛЬНЫМИ названиями → 1_raw.txt
  raw_masked_text — сырые данные с ПСЕВДОНИМАМИ         → 3_raw_masked.txt
  mask_log        — лог "реальное → псевдоним"          → 2_mask_log.txt
  real_names      — {guid: реальное_название} для деанонимизации
"""

from datetime import datetime, timedelta
from pathlib import Path

from block_loader import (
    load_all_blocks,
    process_block,
    collect_real_names,
    Connection,
    BlockConfig,
    BlockResult,
)
from metrics_loader import compute_metrics


# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------

BASE_DIR   = Path(__file__).parent
BLOCKS_DIR = BASE_DIR / "blocks"
METRICS_DIR = BASE_DIR / "metrics"

# ---------------------------------------------------------------------------
# Построение сырого текста из результатов блоков
# ---------------------------------------------------------------------------

def _build_raw_text(results: list[BlockResult],
                    date_label: str, generated_at: str,
                    label: str = "СЫРЫЕ ДАННЫЕ") -> str:
    """
    Строит сырой текст из записей всех блоков.
    Для 1_raw.txt (реальные названия) и 3_raw_masked.txt (псевдонимы).
    """
    lines = [
        f"=== {label} | {date_label} | сформирован {generated_at} ===",
        "",
    ]

    for result in results:
        cfg = result.config
        if cfg.priority is None:
            continue  # вспомогательные блоки — не в сырой текст

        lines.append(f"## {cfg.name.upper()}")

        # Определяем какие записи и какой словарь названий использовать
        records = result.records_raw
        resolved = result.resolved_names

        if not records:
            lines.append("  нет данных")
            lines.append("")
            continue

        for rec in records:
            parts = []
            for key, val in rec.items():
                # Пропускаем служебные OData-поля
                if key.startswith("odata") or key == "Ref_Key":
                    continue
                # Резолвим GUIDы в названия если есть
                if key in resolved and val in resolved[key]:
                    display = resolved[key][val]
                else:
                    display = val
                parts.append(f"{key}: {display}")
            lines.append(f"  {' | '.join(parts)}")

        lines.append("")

    lines.append("=== КОНЕЦ ===")
    return "\n".join(lines)

def _build_raw_guid_text(results: list[BlockResult],
                         date_label: str, generated_at: str) -> str:
    """
    Строит сырой текст с чистыми GUIDами (до резолва).
    Для файла 1_raw.txt.
    """
    lines = [
        f"=== СЫРЫЕ ДАННЫЕ (GUIDы) | {date_label} | сформирован {generated_at} ===",
        "",
    ]

    for result in results:
        cfg = result.config
        if cfg.priority is None:
            continue

        lines.append(f"## {cfg.name.upper()}")

        records = result.records_pre_resolve
        if not records:
            lines.append("  нет данных")
            lines.append("")
            continue

        for rec in records:
            parts = []
            for key, val in rec.items():
                if key.startswith("odata") or key == "Ref_Key":
                    continue
                parts.append(f"{key}: {val}")
            lines.append(f"  {' | '.join(parts)}")

        lines.append("")

    lines.append("=== КОНЕЦ ===")
    return "\n".join(lines)

def _build_raw_masked_text(results: list[BlockResult],
                           date_label: str, generated_at: str) -> str:
    """
    Строит сырой текст с псевдонимами (для 3_raw_masked.txt).
    Использует records_masked вместо records_raw.
    """
    lines = [
        f"=== СЫРЫЕ ДАННЫЕ (замаскированные) | {date_label} | "
        f"сформирован {generated_at} ===",
        "",
    ]

    for result in results:
        cfg = result.config
        if cfg.priority is None:
            continue

        lines.append(f"## {cfg.name.upper()}")

        records = result.records_masked
        resolved = result.resolved_names

        if not records:
            lines.append("  нет данных")
            lines.append("")
            continue

        for rec in records:
            parts = []
            for key, val in rec.items():
                if key.startswith("odata") or key == "Ref_Key":
                    continue
                # Для замаскированных записей ключ поля уже содержит
                # псевдоним — используем как есть
                if key in resolved and val in resolved[key]:
                    display = resolved[key][val]
                else:
                    display = val
                parts.append(f"{key}: {display}")
            lines.append(f"  {' | '.join(parts)}")

        lines.append("")

    lines.append("=== КОНЕЦ ===")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Лог маскировки
# ---------------------------------------------------------------------------

def _build_mask_log(results: list[BlockResult],
                    generated_at: str,
                    client_id: str) -> str | None:
    """
    Строит лог маскировки из всех блоков.
    Возвращает None если маскировки не было.
    """
    from anonymizer import _load_registry

    registry = _load_registry(client_id)
    if not registry:
        return None

    # Собираем все реальные названия
    real_names = collect_real_names(results)

    lines = [
        f"=== ЛОГ МАСКИРОВКИ | {generated_at} ===",
        f"Замаскировано записей: {len(registry)}",
        "",
    ]

    pairs = []
    for key, mask in sorted(registry.items(), key=lambda x: x[1]):
        if "::" not in key:
            continue
        guid = key.split("::", 1)[1]
        real_name = real_names.get(guid, guid[:12] + "...")
        pairs.append((real_name, mask))

    if not pairs:
        return None

    max_len = max((len(r) for r, _ in pairs), default=0)
    for real_name, mask in pairs:
        lines.append(f"  {real_name:<{max_len}}  →  {mask}")

    lines.append("\n=== КОНЕЦ ЛОГА ===")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Главная функция — совместимый интерфейс с digest.py
# ---------------------------------------------------------------------------

def build_layer1(
    base_url:   str,
    login:      str,
    password:   str,
    date_from:  datetime = None,
    date_to:    datetime = None,
    anonymize:  bool = False,
    client_id:  str = "client_001",
    prefetched: dict = None,
    debug:      bool = False,
    debug_dir:  Path = None,
) -> tuple:
    """
    Возвращает кортеж (совместимость с digest.py):
      (aggregated_text, raw_text, raw_masked_text, mask_log, real_names)

    Теперь работает через YAML-конфиги из blocks/.
    prefetched больше не используется — каждый блок загружает данные сам.
    """
    if date_from is None or date_to is None:
        yesterday = datetime.now() - timedelta(days=1)
        date_from = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)

    date_label = date_from.strftime("%d.%m.%Y")
    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    conn = Connection(base_url=base_url, login=login, password=password)

    print(f"[aggregator] Данные за {date_label}...")

    # ── 1. Загрузка конфигов ─────────────────────────────────────────────────
    configs = load_all_blocks(BLOCKS_DIR)
    print(f"[aggregator] Загружено блоков: {len(configs)}")

    # ── 2. Обработка вспомогательных блоков (зависимости) ─────────────────────
    extras = {}
    for cfg in configs:
        if cfg.priority is None:  # вспомогательный
            print(f"\n  → вспомогательный блок: {cfg.id}...")
            result = process_block(
                cfg, conn, date_from, date_to,
                anonymize=anonymize, client_id=client_id,
                debug=debug, debug_dir=debug_dir,
            )
            extras[cfg.id] = result.records_raw

    # ── 3. Обработка основных блоков ──────────────────────────────────────────
    results: list[BlockResult] = []
    for cfg in configs:
        if cfg.priority is None:
            continue
        print(f"\n  → блок: {cfg.name}...")
        result = process_block(
            cfg, conn, date_from, date_to,
            anonymize=anonymize, client_id=client_id,
            extras=extras,
            debug=debug, debug_dir=debug_dir,
        )
        results.append(result)

    # ── 4. Собираем aggregated_text ───────────────────────────────────────────
    sections = [
        f"=== ФИНАНСОВЫЙ ДАЙДЖЕСТ | {date_label} | "
        f"сформирован {generated_at} ===",
        "",
    ]

    for result in results:
        if result.text:
            sections.append(result.text)
            sections.append("")

    # ── Метрики ───────────────────────────────────────────────────────────────
    metrics_text = compute_metrics(METRICS_DIR, results)
    if metrics_text:
        sections.append(metrics_text)
        sections.append("")

    sections.append("=== КОНЕЦ ДАЙДЖЕСТА ===")
    aggregated_text = "\n".join(sections)


    # ── 5. Сырой текст с GUIDами ──────────────────────────────────────────────
    raw_guid_text = _build_raw_guid_text(results, date_label, generated_at)

    # ── 5b. Сырой текст с названиями (читаемый) ──────────────────────────────
    raw_readable_text = _build_raw_text(results, date_label, generated_at)

    # ── 6. Маскированный сырой текст ──────────────────────────────────────────
    raw_masked_text = None
    mask_log = None

    if anonymize:
        raw_masked_text = _build_raw_masked_text(
            results, date_label, generated_at
        )
        mask_log = _build_mask_log(results, generated_at, client_id)

    # ── 7. Реальные названия для деанонимизации ───────────────────────────────
    real_names = collect_real_names(results)

    print(f"\n[aggregator] Готово. aggregated_text: "
          f"{len(aggregated_text)} симв / ~{len(aggregated_text)//4} токенов")

    #return aggregated_text, raw_text, raw_masked_text, mask_log, real_names
    return aggregated_text, raw_guid_text, raw_readable_text, raw_masked_text, mask_log, real_names

# ---------------------------------------------------------------------------
# Точка входа для ручного теста
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    BASE_URL = "http://localhost/Eu/odata/standard.odata"
    LOGIN = "admin_r"
    PASSWORD = "123"

    date_from = datetime(2026, 4, 23, 0, 0, 0)
    date_to = datetime(2026, 4, 23, 23, 59, 59)

    print("=" * 60)
    print("ТЕСТ aggregator.py (новая версия — YAML-конфиги)")
    print("=" * 60)

    aggregated_text, raw_text, raw_masked_text, mask_log, real_names = build_layer1(
        BASE_URL, LOGIN, PASSWORD, date_from, date_to,
        anonymize=False
    )

    print("\n" + "=" * 60)
    print("AGGREGATED TEXT (идёт в LLM):")
    print("=" * 60)
    print(aggregated_text)

    os.makedirs("data/aggregated", exist_ok=True)
    out_path = "data/aggregated/layer1.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(aggregated_text)
    print(f"\n✅ Сохранено в {out_path}")
    print(f"   Размер: {len(aggregated_text)} симв / ~{len(aggregated_text)//4} токенов")
