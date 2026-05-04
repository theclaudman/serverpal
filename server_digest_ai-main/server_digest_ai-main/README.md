# server_digest_ai

Интеллектуальный финансовый дайджест из 1С УНФ.

Сервис автоматически загружает данные из 1С через OData, агрегирует их и отправляет в LLM для формирования аналитического отчёта. Руководитель получает готовый дайджест и может задавать вопросы по данным.

## Что делает

- Загружает данные из 1С УНФ: продажи, дебиторку, кредиторку, остатки, возвраты, денежные средства
- Агрегирует и форматирует в компактный текст для LLM
- Вычисляет метрики: ликвидность, концентрация дебиторки, покрытие кредиторки
- Отправляет в LLM (LM Studio локально или OpenAI) и возвращает готовый дайджест
- Позволяет задавать вопросы по данным: «какие риски по дебиторке?», «что происходит на складе?»
- При использовании облачных LLM автоматически анонимизирует контрагентов

## Архитектура

```
[Дашборд :8000] → [Digest API :8002] → [LLM (LM Studio :1234 / OpenAI)]
                         ↓
                   [1С УНФ OData]
```

Digest API — самостоятельный сервис. Дашборд обращается к нему через HTTP.

## Быстрый старт

### 1. Установка зависимостей

```bash
cd server_digest_ai
pip install -r requirements.txt
```

### 2. Настройка LLM-провайдера

**LM Studio (локальный, без анонимизации):**
- Установи и запусти [LM Studio](https://lmstudio.ai)
- Загрузи модель и запусти локальный сервер на порту 1234

**OpenAI (облачный, с анонимизацией):**
- Создай файл `.env` в корне проекта с одной строкой:
```
OPENAI_API_KEY=sk-...
```

### 3. Запуск сервиса

```bash
python server.py
```

Сервис поднимается на `http://localhost:8002`.

### 4. Проверка

Открой в браузере:
- `http://localhost:8002/health` — статус сервиса
- `http://localhost:8002/api/providers` — доступные LLM-провайдеры
- `http://localhost:8002/docs` — Swagger UI для тестирования API

## API

### GET /health

Проверка что сервис жив.

```json
{"status": "ok", "version": "0.1.0"}
```

### GET /api/providers

Список LLM-провайдеров с проверкой доступности.

```json
{
  "providers": [
    {"id": "lmstudio", "name": "LM Studio (локальный)", "available": true, "anonymize": false},
    {"id": "openai", "name": "OpenAI GPT-4o", "available": true, "anonymize": true}
  ]
}
```

### POST /api/digest

Генерация дайджеста. Занимает 15–60 секунд.

**Запрос:**
```json
{
  "credentials": {
    "base_url": "http://localhost/Eu/odata/standard.odata",
    "login": "admin_r",
    "password": "123"
  },
  "date": "2026-04-28",
  "provider": "lmstudio"
}
```

- `date` — необязательно, по умолчанию вчера
- `provider` — `"lmstudio"` или `"openai"`
- анонимизация определяется автоматически по провайдеру, если модель облачная - то сработает принудительная анонимизация 

**Ответ:**
```json
{
  "status": "ok",
  "digest": "## Утренний дайджест — 28.04.2026\n...",
  "date": "2026-04-28",
  "generated_at": "29.04.2026 08:15",
  "provider": "lmstudio",
  "anonymized": false
}
```

### POST /api/ask

Вопрос по данным последнего дайджеста. Использует кэшированный контекст (TTL 4 часа).

**Запрос:**
```json
{
  "credentials": {
    "base_url": "http://localhost/Eu/odata/standard.odata",
    "login": "admin_r",
    "password": "123"
  },
  "question": "Какие риски по дебиторке?",
  "provider": "lmstudio"
}
```

**Ответ:**
```json
{
  "status": "ok",
  "answer": "По данным дебиторки наблюдается критическая концентрация...",
  "question": "Какие риски по дебиторке?",
  "context_date": "2026-04-28",
  "context_age_minutes": 12,
  "provider": "lmstudio"
}
```

## CLI-режим

Дайджест можно запускать из терминала без сервера:

```bash
python digest.py                      # дайджест за вчера
python digest.py --date 2026-04-28    # за конкретную дату
python digest.py --provider openai    # через OpenAI
python digest.py --anonymize          # с анонимизацией
python digest.py --no-llm             # только агрегация, без LLM
python digest.py --debug              # с сохранением промежуточных файлов
```

## Структура проекта

```
server_digest_ai/
├── server.py              # FastAPI, 4 эндпоинта
├── api_models.py          # Pydantic-модели запросов/ответов
├── context_builder.py     # Кэш контекста (dict, TTL 4ч)
├── digest.py              # Точка входа: CLI + API-функция
├── aggregator.py          # Агрегация данных из блоков
├── block_loader.py        # Загрузка и обработка YAML-блоков
├── metrics_loader.py      # Вычисление метрик из YAML-конфигов
├── lm_client.py           # Отправка в LLM (LM Studio / OpenAI)
├── onec_client.py         # HTTP-клиент к 1С OData
├── anonymizer.py          # Маскировка контрагентов
├── mask_config.json       # Какие поля маскировать
├── requirements.txt       # Зависимости Python
├── .env                   # OPENAI_API_KEY (не в git)
│
├── blocks/                # YAML-конфиги блоков данных
│   ├── money.yaml
│   ├── sales.yaml
│   ├── debts.yaml
│   ├── creditors.yaml
│   ├── stocks.yaml
│   └── ...
│
├── metrics/               # YAML-конфиги метрик
│   ├── current_liquidity.yaml
│   ├── debtor_concentration.yaml
│   └── debt_coverage.yaml
│
├── prompts/               # Системные промпты для LLM
│   ├── digest.txt
│   ├── digest_anonymous.txt
│   ├── ask.txt
│   └── ask_anonymous.txt
│
└── data/                  # Рабочие данные (не в git)
    ├── runs/              # Результаты прогонов
    └── clients/           # Реестры масок
```

## Конфигурация без кода

**Новый блок данных** — создай YAML в `blocks/`. Код не трогать.

**Новая метрика** — создай YAML в `metrics/`. Код не трогать.

**Новое чувствительное поле для маскировки** — добавь запись в `mask_config.json`. Код не трогать.

## Анонимизация

При отправке в облачные LLM (OpenAI) контрагенты автоматически заменяются на псевдонимы:

```
ООО СтройГрупп     → Контрагент_001
ИП Харченко В.И.   → Контрагент_002
```

Маскировка персистентная — один контрагент всегда получает один и тот же псевдоним. Ответ LLM демаскируется перед отдачей клиенту.

## Интеграция с дашбордом

Дашборд (Server_fastapi_1c) обращается к Digest API на порту 8002. Подробности интеграции — в техническом плане (часть 2).
