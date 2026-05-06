"""
digest.py — точка входа утреннего дайджеста

Запуск:
  python digest.py                     # дайджест за вчера
  python digest.py --date 2026-04-21   # дайджест за конкретную дату
  python digest.py --anonymize         # с маскировкой контрагентов
  python digest.py --provider openai   # через OpenAI
  python digest.py --no-llm            # только агрегация, без LLM

Структура папки прогона:

  ANONYMIZE = False:
    data/runs/2026-04-23_10-15/
      1_raw.txt           — сырые данные с реальными названиями
      3_aggregated.txt    — данные которые ушли в LLM
      4_digest.md         — ответ LLM

  ANONYMIZE = True:
    data/runs/2026-04-23_10-15/
      1_raw.txt           — сырые данные с реальными названиями
      2_mask_log.txt      — лог: реальное → псевдоним
      3_raw_masked.txt    — сырые данные с псевдонимами (для проверки)
      3_aggregated.txt    — агрегация, идёт в LLM
      4_digest_masked.md  — ответ LLM (с псевдонимами)
      5_digest_clear.md   — ответ LLM с реальными названиями

Матрица переключений:
  ANONYMIZE    = False          # True | False
  LLM_PROVIDER = "lmstudio"    # "lmstudio" | "openai"
"""

import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Матрица переключений — меняй здесь
# ---------------------------------------------------------------------------

ANONYMIZE    = False         # True | False
LLM_PROVIDER = "lmstudio"   # "lmstudio" | "openai"

# ---------------------------------------------------------------------------
# Подключение к 1С — меняй здесь
# ---------------------------------------------------------------------------

BASE_URL  = "http://127.0.0.1/Eu/odata/standard.odata"
LOGIN     = "admin_r"
PASSWORD  = "123"
CLIENT_ID = "client_001"

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------

BASE_DIR    = Path(__file__).parent
PROMPTS_DIR = BASE_DIR / "prompts"
RUNS_DIR    = BASE_DIR / "data" / "runs"


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _make_run_dir() -> Path:
    """Создаёт папку для текущего прогона с таймстампом."""
    stamp   = datetime.now().strftime("%Y-%m-%d_%H-%M")
    run_dir = RUNS_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _save(run_dir: Path, filename: str, content: str) -> Path:
    """Сохраняет файл в папку прогона и печатает размер."""
    path = run_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  💾 {filename} ({len(content)} симв / ~{len(content)//4} токенов)")
    return path


def _load_prompt(filename: str) -> str:
    """Загружает системный промпт из файла prompts/."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Промпт не найден: {path}\n"
            f"Создай файл prompts/{filename}"
        )
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _demask_with_names(text: str, client_id: str,
                       real_names: dict[str, str]) -> str:
    """
    Заменяет псевдонимы на реальные названия в тексте ответа LLM.
    real_names — {guid: реальное_название} из aggregator.
    """
    from anonymizer import _load_registry
    registry = _load_registry(client_id)

    # Строим: {Контрагент_001: реальное_название}
    inverse = {}
    for key, mask in registry.items():
        if "::" not in key:
            continue
        guid = key.split("::", 1)[1]
        real_name = real_names.get(guid)
        if real_name:
            inverse[mask] = real_name

    result = text
    # Длинные маски сначала — чтобы Контрагент_100 не заменился раньше Контрагент_1001
    for mask in sorted(inverse.keys(), key=len, reverse=True):
        result = result.replace(mask, inverse[mask])

    return result


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Утренний финансовый дайджест из 1С"
    )
    parser.add_argument("--date", type=str, default=None,
        help="Дата в формате YYYY-MM-DD (по умолчанию вчера)")
    parser.add_argument("--provider", type=str, default=None,
        help="lmstudio | openai (переопределяет LLM_PROVIDER)")
    parser.add_argument("--anonymize", action="store_true", default=False,
        help="Маскировать контрагентов (переопределяет ANONYMIZE)")
    parser.add_argument("--no-llm", action="store_true", default=False,
        help="Только агрегация, без LLM")
    parser.add_argument("--debug", action="store_true", default=False,
        help="Сохранять промежуточные файлы каждого блока")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# API-версия — для server.py (без print, без записи файлов)
# ---------------------------------------------------------------------------

def run_digest_api(
    base_url: str,
    login: str,
    password: str,
    date: datetime = None,
    provider: str = "lmstudio",
    system_prompt: str = "",
) -> dict:
    """
    API-версия run_digest().
    Без print(), без записи файлов.
    Возвращает dict с результатом.

    Анонимизация определяется автоматически по провайдеру:
      lmstudio → anonymize=False
      openai   → anonymize=True
    """
    anonymize = provider.lower().strip() != "lmstudio"

    if date is None:
        date = datetime.now() - timedelta(days=1)

    date_from = date.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    date_to   = date.replace(hour=23, minute=59, second=59, microsecond=0)

    date_str     = date.strftime("%Y-%m-%d")
    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    # 1. Проверка подключения к 1С
    from onec_client import check_connection
    if not check_connection(base_url, login, password):
        return {
            "status": "error",
            "error": "connection_failed",
            "message": f"Не удалось подключиться к 1С: {base_url}",
        }

    # 2. Агрегация
    from aggregator import build_layer1
    (aggregated_text, raw_guid_text, raw_readable_text,
     raw_masked_text, mask_log, real_names) = build_layer1(
        base_url, login, password, date_from, date_to,
        anonymize, CLIENT_ID,
    )

     # 2b. Сохраняем файлы прогона (аудит)
    run_dir = _make_run_dir()
    _save(run_dir, "1_raw.txt", raw_guid_text)
    _save(run_dir, "2_raw_readable.txt", raw_readable_text)
    if anonymize:
        if raw_masked_text:
            _save(run_dir, "3_masked.txt", raw_masked_text)
        if mask_log:
            _save(run_dir, "4_mask_log.txt", mask_log)
    _save(run_dir, "5_aggregated.txt", aggregated_text)

    # 3. Отправка в LLM
    # Промпт из БД дашборда (приоритет) или из файла (фолбэк)
    if system_prompt.strip():
        final_prompt = system_prompt
    else:
        prompt_file   = "digest_anonymous.txt" if anonymize else "digest.txt"
        final_prompt  = _load_prompt(prompt_file)

    from lm_client import send
    try:
        digest_masked = send(aggregated_text, final_prompt, provider=provider)
    except Exception as e:
        return {
            "status": "error",
            "error": "llm_unavailable",
            "message": f"LLM недоступен ({provider}): {e}",
        }

    # 4. Демаскировка если нужно
    if anonymize:
        digest_text = _demask_with_names(digest_masked, CLIENT_ID, real_names)
    else:
        digest_text = digest_masked

    # Сохраняем дайджест в файл
    if anonymize:
        _save(run_dir, "6_digest_masked.md", digest_masked)
        _save(run_dir, "7_digest_clear.md", digest_text)
    else:
        _save(run_dir, "6_digest.md", digest_text)
        
    return {
        "status": "ok",
        "digest": digest_text,
        "date": date_str,
        "generated_at": generated_at,
        "provider": provider,
        "anonymized": anonymize,
        "aggregated_text": aggregated_text,   # для кэша (не отдаётся клиенту)
        "real_names": real_names,             # для демаскировки вопросов
    }


# ---------------------------------------------------------------------------
# Главная функция — CLI
# ---------------------------------------------------------------------------

def run_digest(target_date: datetime = None,
               provider: str = None,
               anonymize: bool = None,
               no_llm: bool = False,
               debug: bool = False) -> str:


    _provider  = provider  if provider  is not None else LLM_PROVIDER
    _anonymize = anonymize if anonymize is not None else ANONYMIZE

    if target_date is None:
        target_date = datetime.now() - timedelta(days=1)

    date_from = target_date.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    date_to   = target_date.replace(hour=23, minute=59, second=59, microsecond=0)

    run_dir = _make_run_dir()

    print(f"\n{'='*60}")
    print(f"ДАЙДЖЕСТ за {target_date.strftime('%d.%m.%Y')}")
    print(f"  Провайдер:    {_provider}")
    print(f"  Анонимизация: {'вкл' if _anonymize else 'выкл'}")
    print(f"  Папка:        {run_dir}")
    print(f"{'='*60}\n")

    # ── Шаг 1: Проверка подключения к 1С ─────────────────────────────────────
    print("[1/3] Проверка подключения к 1С...")

    from onec_client import check_connection
    if not check_connection(BASE_URL, LOGIN, PASSWORD):
        raise ConnectionError(f"Нет подключения к 1С: {BASE_URL}")
    print("  ✅ Подключение успешно")

    # ── Шаг 2: Агрегация (загрузка + обработка по YAML-конфигам) ─────────────
    print("\n[2/3] Загрузка и агрегация данных...")

    from aggregator import build_layer1
    aggregated_text, raw_guid_text, raw_readable_text, raw_masked_text, mask_log, real_names = build_layer1(
        BASE_URL, LOGIN, PASSWORD, date_from, date_to,
        _anonymize, CLIENT_ID,
        debug=debug, debug_dir=run_dir,
    )

    # ── Сохраняем файлы этапов ───────────────────────────────────────────────
    print("\n  Сохраняем файлы прогона:")

    # 1 — сырые данные с GUIDами
    _save(run_dir, "1_raw.txt", raw_guid_text)

    # 2 — читаемый текст (GUIDы → названия)
    _save(run_dir, "2_raw_readable.txt", raw_readable_text)

    if _anonymize:
        # 3 — замаскированный текст
        if raw_masked_text:
            _save(run_dir, "3_masked.txt", raw_masked_text)
        # 4 — лог маскировки
        if mask_log:
            _save(run_dir, "4_mask_log.txt", mask_log)

    # 5 — агрегированный текст (уходит в LLM)
    _save(run_dir, "5_aggregated.txt", aggregated_text)
    
    # Если --no-llm — выходим после сохранения файлов
    if no_llm:
        print(f"\n⚠️  Режим --no-llm: остановка после агрегации")
        print(f"   Файлы сохранены в: {run_dir}")
        return aggregated_text

    # ── Шаг 3: Отправка в LLM ───────────────────────────────────────────────
    print(f"\n[3/3] Отправка в LLM ({_provider})...")

    prompt_file   = "digest_anonymous.txt" if _anonymize else "digest.txt"
    system_prompt = _load_prompt(prompt_file)
    print(f"  Промпт файл: {prompt_file}")
    print(f"  Промпт:  {len(system_prompt)} символов")
    print(f"  Данные:  {len(aggregated_text)} символов")
    print(f"  Ожидаем ответ...")

    from lm_client import send
    digest_masked = send(aggregated_text, system_prompt, provider=_provider)

    # ── Сохранение результатов ───────────────────────────────────────────────
    print(f"\n  Сохранение результатов...")

    if _anonymize:
        _save(run_dir, "6_digest_masked.md", digest_masked)

        digest_clear = _demask_with_names(digest_masked, CLIENT_ID, real_names)
        _save(run_dir, "7_digest_clear.md", digest_clear)

        print(f"\n✅ Прогон завершён: {run_dir}")
        return digest_clear
    else:
        _save(run_dir, "6_digest.md", digest_masked)
        print(f"\n✅ Прогон завершён: {run_dir}")
        return digest_masked


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = _parse_args()

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"❌ Неверный формат даты: {args.date}")
            print("   Используй: --date 2026-04-21")
            sys.exit(1)

    try:
        digest = run_digest(
            target_date = target_date,
            provider    = args.provider,
            anonymize   = args.anonymize if args.anonymize else None,
            no_llm      = args.no_llm,
            debug       = args.debug,
        )

        print("\n" + "=" * 60)
        print("ДАЙДЖЕСТ:")
        print("=" * 60)
        print(digest)
        print("=" * 60)

    except ConnectionError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        raise
