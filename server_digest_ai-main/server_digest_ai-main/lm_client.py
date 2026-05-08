"""
lm_client.py — единый интерфейс отправки данных в LLM

Поддерживаемые провайдеры:
  lmstudio  — локальная модель через LM Studio (порт 1234)
  openai    — OpenAI API (gpt-4o и др.)

Добавление нового провайдера:
  1. Написать функцию _send_<name>(text, system_prompt, **kwargs) -> str
  2. Добавить ветку в send()

Интерфейс:
  from lm_client import send
  response = send(text, system_prompt, provider="lmstudio")
"""

import os
import json
from pathlib import Path

from dotenv import load_dotenv


def get_env_file() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "run_all.py").exists():
            root_env = candidate / ".env"
            if root_env.exists():
                return root_env
            raise RuntimeError(
                f"Корневой .env не найден: {root_env}. "
                "Создайте его из .env.example в корне проекта."
            )
    raise RuntimeError("Не удалось найти корень проекта ServerPal")


load_dotenv(get_env_file(), override=False)

# ---------------------------------------------------------------------------
# Конфигурация провайдеров
# ---------------------------------------------------------------------------

# LM Studio
LMSTUDIO_BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
LMSTUDIO_MODEL    = os.environ.get("LMSTUDIO_MODEL", "dolphin-2.9.4-llama3.1-8b")

# OpenAI
OPENAI_BASE_URL   = os.environ.get("DIGEST_OPENAI_BASE_URL", "https://api.hydraai.ru/v1")
OPENAI_MODEL      = os.environ.get("DIGEST_OPENAI_MODEL", "gpt-4o")

# Таймаут запроса в секундах — локальная модель может думать долго
REQUEST_TIMEOUT   = int(os.environ.get("DIGEST_REQUEST_TIMEOUT", "120"))


# ---------------------------------------------------------------------------
# Внутренние функции провайдеров
# ---------------------------------------------------------------------------

def _send_lmstudio(text: str, system_prompt: str) -> str:
    """
    Отправляет текст в LM Studio на порт 1234.
    LM Studio совместим с OpenAI API — используем requests напрямую
    без зависимости от openai SDK.
    """
    import urllib.request

    payload = {
        "model": LMSTUDIO_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": text},
        ],
        "temperature": 0.3,   # низкая температура — финансовый анализ, нужна точность
        "max_tokens": 2048,
    }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        f"{LMSTUDIO_BASE_URL}/chat/completions",
        data    = data,
        headers = {
            "Content-Type":  "application/json",
            "Authorization": "Bearer lm-studio",
        },
        method  = "POST",
    )

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    return result["choices"][0]["message"]["content"]


def _send_openai(text: str, system_prompt: str) -> str:
    """
    Отправляет текст в OpenAI API.
    API ключ берётся из переменной окружения OPENAI_API_KEY
    или из файла .env в корне проекта.
    """
    import urllib.request

    api_key = _get_openai_key()

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": text},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        f"{OPENAI_BASE_URL}/chat/completions",
        data    = data,
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method  = "POST",
    )

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    return result["choices"][0]["message"]["content"]


def _get_openai_key() -> str:
    """
    Ищет OPENAI_API_KEY в порядке приоритета:
      1. Переменная окружения
      2. Файл .env в корне проекта (простой парсинг KEY=VALUE)
    Если не найден — поднимает понятную ошибку.
    """
    # 1. Переменная окружения
    key = os.environ.get("OPENAI_API_KEY", "")
    if key and key != "lm-studio":
        return key

    # 2. .env файл
    env_path = get_env_file()
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENAI_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if key and key != "lm-studio":
                        return key

    raise ValueError(
        "OPENAI_API_KEY не найден.\n"
        "Добавь в .env файл строку: OPENAI_API_KEY=sk-...\n"
        "Или установи переменную окружения."
    )


# ---------------------------------------------------------------------------
# Публичный интерфейс
# ---------------------------------------------------------------------------

def send_with_question(aggregated_text: str, question: str,
                       system_prompt: str,
                       provider: str = "lmstudio") -> str:
    """
    Отправляет в LLM контекст данных + вопрос пользователя.

    Используется эндпоинтом POST /api/ask.
    Контекст — aggregated_text из build_layer1().
    Вопрос — свободный текст от руководителя.

    Аргументы:
      aggregated_text — агрегированные данные из 1С
      question        — вопрос пользователя
      system_prompt   — роль и инструкции (из prompts/ask.txt)
      provider        — "lmstudio" | "openai"

    Возвращает:
      Строку с ответом модели.
    """
    user_message = (
        f"{aggregated_text}\n\n"
        f"ВОПРОС:\n{question}"
    )
    return send(user_message, system_prompt, provider=provider)


def send(text: str, system_prompt: str,
         provider: str = "lmstudio") -> str:
    """
    Отправляет текст в LLM и возвращает ответ.

    Аргументы:
      text          — агрегированные данные из aggregator (layer1.txt)
      system_prompt — роль и инструкции для модели (из prompts/digest.txt)
      provider      — "lmstudio" | "openai"

    Возвращает:
      Строку с ответом модели — готовый дайджест.

    Пример:
      from lm_client import send
      response = send(layer1_text, prompt_text, provider="lmstudio")
    """
    provider = provider.lower().strip()

    if provider == "lmstudio":
        return _send_lmstudio(text, system_prompt)

    elif provider == "openai":
        return _send_openai(text, system_prompt)

    else:
        raise ValueError(
            f"Неизвестный провайдер: '{provider}'.\n"
            f"Доступные: lmstudio, openai"
        )


def check_lmstudio() -> bool:
    """
    Проверяет что LM Studio запущен и отвечает.
    Возвращает True если доступен, False если нет.
    """
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(
            f"{LMSTUDIO_BASE_URL}/models",
            headers={"Authorization": "Bearer lm-studio"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            models = [m["id"] for m in result.get("data", [])]
            return len(models) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Точка входа для ручного теста
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 60)
    print("ТЕСТ lm_client.py")
    print("=" * 60)

    # Тест 1 — проверка доступности LM Studio
    print("\n[1] Проверка LM Studio...")
    if check_lmstudio():
        print(f"✅ LM Studio доступен на {LMSTUDIO_BASE_URL}")
    else:
        print(f"❌ LM Studio недоступен на {LMSTUDIO_BASE_URL}")
        print("   Убедись что LM Studio запущен и модель загружена.")
        print("   Тест отправки пропущен.\n")
        exit(1)

    # Тест 2 — короткий запрос к LM Studio
    print("\n[2] Тестовый запрос к LM Studio...")

    test_system = (
        "Ты финансовый аналитик. "
        "Отвечай кратко и по делу на русском языке."
    )
    test_text = (
        "ДЕНЬГИ НА СЧЕТАХ: 106 000 000 ₽\n"
        "ДЕБИТОРКА: 356 000 000 ₽ (309 контрагентов)\n"
        "КРИТИЧНЫЕ ОСТАТКИ: 3 позиции\n"
        "ПРОДАЖИ (вчера): 842 300 ₽, накладных: 7\n"
        "\nНазови одну главную проблему из этих данных."
    )

    print(f"  Провайдер: lmstudio")
    print(f"  Модель: {LMSTUDIO_MODEL}")
    print(f"  Запрос отправлен, ожидаем ответ (до {REQUEST_TIMEOUT} сек)...")

    try:
        response = send(test_text, test_system, provider="lmstudio")
        print(f"\n  Ответ модели:\n")
        print(f"  {response[:500]}")
        if len(response) > 500:
            print(f"  ... (всего {len(response)} символов)")
        print("\n✅ LM Studio работает")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")

    # Тест 3 — проверка OpenAI ключа (без реального запроса)
    print("\n[3] Проверка OpenAI API ключа...")
    try:
        key = _get_openai_key()
        print(f"✅ Ключ найден: {key[:8]}...{key[-4:]}")
        print("   (реальный запрос к OpenAI не делаем — платный)")
    except ValueError as e:
        print(f"⚠️  {e}")
        print("   Это нормально если OpenAI сейчас не нужен.")
