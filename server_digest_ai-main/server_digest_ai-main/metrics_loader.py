"""
metrics_loader.py — вычисление метрик по итогам блоков

Читает YAML-конфиги из папки metrics/.
Берёт итоги из уже обработанных блоков (total, top_1 и т.д.).
Применяет формулу, форматирует текст, проверяет пороги.

Добавить новую метрику = создать YAML в metrics/. Код не трогать.

Публичный интерфейс:
  compute_metrics(metrics_dir, block_results) -> str
"""

import yaml
from pathlib import Path

from block_loader import BlockResult


# ---------------------------------------------------------------------------
# Извлечение значений из результатов блоков
# ---------------------------------------------------------------------------

def _get_block_value(block_id: str, value_key: str,
                     block_totals: dict) -> float:
    """
    Извлекает числовое значение из итогов блока.

    value_key:
      total  — общая сумма блока
      top_1  — сумма крупнейшего элемента
      count  — количество записей/групп
    """
    totals = block_totals.get(block_id)
    if totals is None:
        return 0.0

    if value_key == "total":
        return totals.get("total", 0.0)

    if value_key == "top_1":
        top_items = totals.get("top_items", [])
        if top_items:
            return top_items[0][1]  # (name, amount) — берём amount
        return 0.0

    if value_key == "count":
        return float(totals.get("count", 0))

    return 0.0


def _fmt_money(value) -> str:
    """106000000 → '106 000 000 ₽'"""
    try:
        return f"{float(value):,.0f} ₽".replace(",", " ")
    except Exception:
        return str(value)


# ---------------------------------------------------------------------------
# Построение итогов из результатов блоков
# ---------------------------------------------------------------------------

def _build_block_totals(results: list[BlockResult]) -> dict:
    """
    Строит словарь {block_id: aggregated_data} из результатов блоков.
    """
    totals = {}
    for result in results:
        totals[result.config.id] = result.aggregated
    return totals


# ---------------------------------------------------------------------------
# Вычисление одной метрики
# ---------------------------------------------------------------------------

def _compute_one(metric_cfg: dict, block_totals: dict) -> str | None:
    """
    Вычисляет одну метрику и возвращает отформатированную строку.
    Возвращает None если данных нет.
    """
    formula = metric_cfg.get("formula", {})
    op = formula.get("op", "divide")

    # Получаем значения a и b
    a_cfg = formula.get("a", {})
    b_cfg = formula.get("b", {})

    a = _get_block_value(a_cfg.get("block", ""), a_cfg.get("value", "total"),
                         block_totals)
    b = _get_block_value(b_cfg.get("block", ""), b_cfg.get("value", "total"),
                         block_totals)

    # Вычисляем
    if op == "divide":
        result = a / b if b else 0.0
    elif op == "subtract":
        result = a - b
    elif op == "add":
        result = a + b
    elif op == "multiply":
        result = a * b
    else:
        return None

    # Форматируем
    fmt = metric_cfg.get("format", "{result}")
    try:
        text = fmt.format(
            result=result,
            result_pct=result * 100,
            a=a,
            b=b,
            a_fmt=_fmt_money(a),
            b_fmt=_fmt_money(b),
        )
    except Exception:
        text = f"{metric_cfg.get('name', '?')}: {result:.2f}"

    # Проверяем порог предупреждения
    warning = metric_cfg.get("warning")
    if warning:
        condition = warning.get("condition", "")
        threshold = warning.get("threshold", 0)
        warning_text = warning.get("text", "")

        triggered = False
        if condition == "below" and result < threshold:
            triggered = True
        elif condition == "above" and result > threshold:
            triggered = True

        if triggered and warning_text:
            text += f"\n  {warning_text}"

    return text


# ---------------------------------------------------------------------------
# Публичный интерфейс
# ---------------------------------------------------------------------------

def compute_metrics(metrics_dir: str | Path,
                    results: list[BlockResult]) -> str | None:
    """
    Загружает все метрики из YAML, вычисляет, возвращает текст.
    Возвращает None если папки нет или метрик нет.
    """
    metrics_dir = Path(metrics_dir)
    if not metrics_dir.exists():
        return None

    # Загружаем конфиги
    configs = []
    for yaml_file in sorted(metrics_dir.glob("*.yaml")):
        with open(yaml_file, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if cfg.get("enabled", True):
            configs.append(cfg)

    if not configs:
        return None

    # Строим итоги блоков
    block_totals = _build_block_totals(results)

    # Вычисляем каждую метрику
    lines = ["МЕТРИКИ:"]
    for cfg in configs:
        text = _compute_one(cfg, block_totals)
        if text:
            lines.append(f"  {text}")

    if len(lines) <= 1:
        return None

    return "\n".join(lines)
