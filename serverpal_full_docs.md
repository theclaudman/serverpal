# ServerPal — Полная техническая документация

> Документ для передачи контекста в новый чат Claude.
> Содержит: архитектуру, текущее состояние, выполненные шаги, незавершённые задачи, известные проблемы.
> Дата: 06.05.2026

---

## 1. Концепция проекта

### Что это

**ИИ-финдиректор на базе 1С:УНФ 3.0** — система из трёх Python-сервисов, которая:
- Автоматически загружает данные из 1С через OData
- Агрегирует их в компактный текст
- Отправляет в LLM для аналитики
- Предоставляет веб-интерфейс руководителю

### Три режима работы

1. **Проактивный (дайджест)** — утром/вечером автоматически анализирует данные и предупреждает о проблемах (кассовый разрыв, критичные остатки, просрочки).
2. **Диалоговый (чат)** — руководитель задаёт произвольные вопросы по данным 1С.
3. **Дашборд** — веб-страницы с KPI менеджеров, прайс-листом, отчётом по продажам.

### Три слоя данных

**Слой 1 — Внутренние данные из 1С УНФ** (реализован):
- Деньги и ликвидность, продажи и выручка, дебиторка/кредиторка, остатки на складах, возвраты
- Загружается через OData, конфигурируется YAML-файлами в `blocks/`

**Слой 2 — Внешние измеримые факторы** (НЕ реализован):
- Курс валют (ЦБ РФ API), ключевая ставка, праздники, сезонность

**Слой 3 — Ручной ввод** (НЕ реализован):
- Директор/менеджер вводит события, ИИ учитывает при анализе

### Мультитенантность

Несколько баз 1С, каждая со своими клиентами. Не несколько пользователей к одной базе, а несколько компаний — каждая к своей базе.

### Только роль admin

Без разделения на manager/readonly. Один пользователь — один логин к одной базе 1С.

---

## 2. Архитектура

```
┌────────────────────────────────────────────────────────────────────┐
│                        Браузер (UI)                                │
│  /login  /register  /  /chat  /digest  /price-list  /prompts      │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │   Дашборд (FastAPI, порт 9001)   │
              │   Server_fastapi_1c-main/        │
              │   main.py + services/            │
              │   SQLite (users.db)              │
              ├─────────┬───────────────────────┤
              │         │                       │
    ┌─────────▼──────┐  │  ┌────────────────────▼───────────┐
    │  AI Bridge     │  │  │  Digest API                    │
    │  (порт 8001)   │  │  │  (порт 8002)                   │
    │  server_ai/    │  │  │  server_digest_ai/              │
    │  OpenAI API    │  │  │  OData → агрегация → LLM       │
    └───────┬────────┘  │  └────────────────┬───────────────┘
            │           │                   │
            └─────┬─────┘                   │
                  │                         │
         ┌────────▼────────┐       ┌────────▼────────┐
         │  LM Studio      │       │  1С:УНФ 3.0     │
         │  (порт 1234)    │       │  (OData API)     │
         │  локальная LLM  │       │                  │
         └─────────────────┘       └──────────────────┘
```

### Порты

| Сервис | Порт | Описание |
|--------|------|----------|
| Дашборд | 9001 | Веб-интерфейс, API, прокси к другим сервисам |
| AI Bridge | 8001 | Чат с LLM + function calling (запросы к 1С) |
| Digest API | 8002 | Загрузка данных из 1С, агрегация, дайджест через LLM |
| LM Studio | 1234 | Локальная LLM (OpenAI-совместимый API) |

### Важно: localhost vs 127.0.0.1

Везде используется `127.0.0.1`, НЕ `localhost`. Python httpx резолвит `localhost` в `::1` (IPv6), а сервисы слушают на `0.0.0.0` (IPv4). Это вызывает 503 ошибки.

Касается: `.env` дашборда, `config.py` AI Bridge, `lm_client.py` Digest API, адрес базы 1С при логине.

---

## 3. Структура файлов

```
Serverpal/
├── run_all.py                          # Единый запуск всех 3 сервисов
├── .env                                # (в папке дашборда, не в корне)
│
├── Server_fastapi_1c-main/Server_fastapi_1c-main/
│   ├── main.py                         # Дашборд — все роуты
│   ├── config.py                       # Настройки из .env
│   ├── database.py                     # SQLite: пользователи, промпты, шаблоны
│   ├── .env                            # SECRET_KEY, ENCRYPTION_KEY, URLs, порты
│   ├── templates/                      # HTML-шаблоны (chat, digest, prompts и др.)
│   └── services/
│       ├── ai_client.py                # HTTP-клиент к AI Bridge (httpx async)
│       ├── digest_client.py            # HTTP-клиент к Digest API (httpx async)
│       ├── onec_client.py              # HTTP-клиент к 1С OData (httpx async)
│       ├── cache.py                    # TTL-кэш данных из 1С
│       ├── data_builder.py             # Построение прайс-листа
│       ├── dashboard_builder.py        # Построение дашборда менеджеров
│       └── sales_builder.py            # Построение отчёта по продажам
│
├── server_ai-main/server_ai-main/
│   ├── app/
│   │   ├── main.py                     # FastAPI app, health, scheduler
│   │   ├── core/
│   │   │   ├── config.py               # openai_base_url, model, api_key
│   │   │   ├── scheduler.py            # APScheduler для отчётов
│   │   │   └── security.py             # make_base_id
│   │   ├── models/
│   │   │   └── schemas.py              # Pydantic: ChatRequest, ChatResponse и др.
│   │   ├── services/
│   │   │   ├── ai_service.py           # answer_prompt() — LLM + function calling
│   │   │   ├── onec_service.py         # execute_query() — запросы к 1С
│   │   │   └── storage_service.py      # Хранение отчётов
│   │   └── api/routes/
│   │       ├── chat.py                 # POST /chat/
│   │       ├── query.py                # POST /query/
│   │       └── reports.py              # Отчёты
│   ├── prompts/                        # Системные промпты (файлы .txt)
│   └── knowledge_base.txt              # База знаний (5564 строки)
│
└── server_digest_ai-main/server_digest_ai-main/
    ├── server.py                       # FastAPI app, /api/digest, /api/ask
    ├── digest.py                       # run_digest_api() — основная логика
    ├── api_models.py                   # Pydantic-модели
    ├── lm_client.py                    # Клиент к LM Studio / OpenAI
    ├── aggregator.py                   # Агрегация данных из 1С
    ├── onec_client.py                  # Загрузка данных из 1С OData
    ├── block_loader.py                 # Загрузка YAML-блоков
    ├── anonymizer.py                   # Анонимизация данных для OpenAI
    ├── context_builder.py              # Построение контекста для LLM
    ├── metrics_loader.py               # Загрузка метрик
    ├── blocks/                         # YAML-конфигурации OData-блоков
    └── prompts/                        # Системные промпты (файлы .txt)
```

---

## 4. .env дашборда

```
SECRET_KEY=<зашифрованный ключ>
ENCRYPTION_KEY=<ключ Fernet>
AI_SERVICE_URL=http://127.0.0.1:8001
DIGEST_SERVICE_URL=http://127.0.0.1:8002
PRICE_TYPE_RETAIL=<GUID из 1С>
PRICE_TYPE_WHOLESALE=<GUID из 1С>
ALLOWED_ORIGINS=http://127.0.0.1:9001,http://127.0.0.1:8002,http://127.0.0.1:8001
```

---

## 5. Выполненные шаги (1–13 + мелочи)

### Фаза 1: Безопасность (шаги 1–5)
- **Шаг 1**: Базовая авторизация (логин/пароль, cookie-сессии, Fernet)
- **Шаг 2**: Хэширование паролей (bcrypt), шифрование пароля 1С (Fernet)
- **Шаг 3**: Шифрование пароля в cookie-сессии
- **Шаг 4**: Rate limiting (slowapi)
- **Шаг 5**: CORS — ограничение origins

### Фаза 2: Стабильность (шаги 6–9)
- **Шаг 6**: Логирование (RotatingFileHandler, все 3 сервиса)
- **Шаг 7**: Единый запуск (`run_all.py`)
- **Шаг 8**: Async HTTP-клиент (urllib → httpx) для onec_client
- **Шаг 9**: Health checks между сервисами

### Фаза 3: UX (шаги 10–13)
- **Шаг 10**: Глобальная обработка ошибок
- **Шаг 11**: Кэширование данных из 1С (TTL-кэш)
- **Шаг 12**: Библиотека промптов — UI на `/prompts`, CRUD API, таблицы в SQLite (prompts + prompt_templates)

- **Шаг 13**: Подключение промптов из БД к AI Bridge и Digest API ✅
  - `ai_client.py` → переписан на httpx async + передаёт `system_prompt`
  - `digest_client.py` → переписан на httpx async + передаёт `system_prompt`
  - AI Bridge `schemas.py` → добавлено поле `system_prompt` в `ChatRequest`
  - AI Bridge `chat.py` → передаёт `system_prompt` в `ai_service.answer_prompt()`
  - AI Bridge `ai_service.py` → принимает `system_prompt`, фолбэк на файл
  - Digest API `api_models.py` → добавлено `system_prompt` в `DigestRequest` и `AskRequest`
  - Digest API `server.py` → передаёт `system_prompt` с фолбэком
  - Digest API `digest.py` → принимает `system_prompt` с фолбэком
  - Дашборд `main.py` → `post_chat`, `api_digest`, `api_digest_ask` достают промпт из БД через `get_prompt()` и передают вниз

### Мелочи (после шага 13)
- Дедуплицированы импорты в `main.py` (было 3 импорта database, 2 config, 2 hashlib, 2 Path)
- Все обработчики приведены к `async def` (login_page, register_page, logout, get_index, get_chat, digest_page были sync)
- Убран мёртвый код (закомментированный post_chat, дубликат api_digest, закомментированный api_digest_providers)
- Добавлен рабочий роут `GET /api/digest/providers` (с `await`)
- Pydantic-модели вынесены в начало файла
- `check_service()` с логированием ошибок и увеличенным таймаутом (5с)
- Пароли 1С расшифровываются через `decrypt_onec_password()` перед передачей в сервисы

---

## 6. Логика фолбэка промптов

Везде одинаковая: если в БД дашборда промпт заполнен — используется он. Если пустая строка — сервис берёт свой файл из `prompts/`.

Цепочка: Браузер → Дашборд (достаёт из БД) → AI Bridge / Digest API (используют или берут из файла)

---

## 7. База данных (SQLite, users.db)

```sql
-- Пользователи
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    onec_base_url TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Промпты
CREATE TABLE prompts (
    id TEXT PRIMARY KEY,          -- 'chat', 'digest', 'ask'
    name TEXT NOT NULL,           -- 'Чат-ассистент', 'Дайджест', 'Вопрос по данным'
    description TEXT DEFAULT '',
    content TEXT DEFAULT ''       -- текст промпта
);

-- Шаблоны промптов
CREATE TABLE prompt_templates (
    id INTEGER PRIMARY KEY,
    prompt_id TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);
```

**ВАЖНО:** при изменении схемы нужно удалять `users.db` и регистрироваться заново. Миграции через alembic пока не настроены.

---

## 8. Зависимости (общий venv)

```
fastapi "uvicorn[standard]" python-multipart
bcrypt cryptography                    # безопасность
slowapi                                 # rate limiting
pydantic-settings python-dotenv         # конфигурация
httpx                                   # async HTTP
cachetools                              # TTL-кэш
requests pyyaml                         # Digest API
openai apscheduler                      # AI Bridge
websockets httptools                    # для uvicorn WebSocket поддержки
```

Установка одной командой:
```bash
pip install fastapi "uvicorn[standard]" python-multipart bcrypt cryptography slowapi pydantic-settings python-dotenv httpx cachetools requests pyyaml openai apscheduler websockets httptools
```

**Важно:** `uvicorn[standard]` не всегда ставит зависимости. Если `pip show uvicorn` показывает `Requires: click, h11` (без websockets/httptools) — доставить вручную: `pip install websockets httptools`.

---

## 9. Запуск

```bash
cd C:\Users\klodc\Desktop\Serverpal
venv\scripts\activate
python run_all.py
```

Запускает 3 сервиса: Digest API (8002), AI Bridge (8001), Dashboard (9001).

Проверка здоровья: `http://127.0.0.1:9001/health` — должен показать `ai_bridge: true, digest_api: true`.

Автоматическая smoke-проверка локального запуска:
```bash
python scripts/smoke_check.py
```

---

## 10. Известные проблемы и технический долг

1. **HTML-шаблоны** — используют `html.replace()` вместо Jinja2. XSS-уязвимости (низкий риск, закрытая система).
2. **`knowledge_base.txt`** (5564 строки) — загружается целиком в промпт, съедает контекстное окно LLM. Нужен RAG или фильтрация.
3. **Контекст LLM** — при большом дайджесте промпт может превысить лимит модели. Нужно увеличивать контекст в LM Studio (8192+).
4. **Кэш контекста Digest API** — in-memory, теряется при перезапуске.
5. **Мало тестов** для дашборда и Digest API. Добавлен smoke-check локального запуска, но бизнес-логика пока не покрыта.
6. **Нет HTTPS** — будет в Фазе 4 с Nginx.
7. **Нет миграций БД** — alembic не настроен, при изменении схемы нужно удалять users.db.
8. **WebSocket стриминг** — активирован в дашборде и AI Bridge. UI использует WS для стриминга, но сохраняет fallback на обычный POST `/api/chat`, если WS не подключился.
9. **Docker контейнеры** — на компе заказчика запущены контейнеры (codeks) на порту 8000, поэтому дашборд перенесён на 9001.

---

## 11. WebSocket стриминг (шаг 21) — АКТИВЕН

Код активирован. Включает:
- `ai_service.py` → функция `stream_answer_prompt()` — генератор токенов с поддержкой function calling
- `chat.py` AI Bridge → WebSocket эндпоинт `/chat/ws`
- `main.py` дашборда → WebSocket прокси `/ws/chat`
- `chat.html` → JS с WebSocket подключением и посимвольным отображением

Проверено: локальный запуск на `127.0.0.1:9001` работает в обычном браузере. Антидетект-браузер может ломать cookie/WS, поэтому для проверки используется обычный Chrome/Edge/Firefox.

Если WebSocket недоступен, чат автоматически отправляет запрос через POST `/api/chat`.

---

## 12. План дальнейшей разработки

### Фаза 4: Деплой
- **Шаг 14**: Docker (3 Dockerfile + docker-compose)
- **Шаг 15**: Nginx reverse proxy + HTTPS (Let's Encrypt)
- **Шаг 16**: Бэкапы и мониторинг

### Фаза 5: Функциональные улучшения
- **Шаг 17**: Веб-интерфейс для YAML-блоков OData
- **Шаг 18**: Веб-интерфейс для compute-правил
- **Шаг 19**: Слой 2 — внешние API (курс ЦБ, календарь, сезонность)
- **Шаг 20**: Слой 3 — интерфейс ручного ввода событий
- **Шаг 21**: WebSocket стриминг (активен, есть POST fallback)
- **Шаг 22**: Оптимизация knowledge_base.txt (RAG или фильтрация)
- **Шаг 23**: Jinja2 вместо html.replace()
- **Шаг 24**: Миграции БД через alembic

### Ближайший шаг: 14 (Docker)

Заказчик хочет арендовать VPS и развернуть проект. Нужны:
- Dockerfile для каждого сервиса
- docker-compose.yml для единого запуска
- Nginx как reverse proxy + HTTPS

---

## 13. Желания заказчика

1. **Единый запуск** — ✅ сделано (`run_all.py`), в будущем Docker.
2. **Управляемые промпты** — ✅ UI + подключение к сервисам готово.
3. **Добавляемость блоков OData через интерфейс** — веб-редактор YAML-блоков.
4. **Добавляемость вычислений** — compute-правила через интерфейс.
5. **Слой 2 и 3** — внешние API + ручной ввод событий.
6. **Дайджест как в proj.txt** — утренний/вечерний автоматический анализ с прогнозами, рекомендациями, обнаружением аномалий.

### Пример идеального дайджеста

> **Кассовый разрыв через 11 дней** — На счетах 430 000 ₽. Через 11 дней нужно заплатить 380 000 ₽. Ожидаемые поступления 210 000 ₽. Дефицит 170 000 ₽. Клиент X должен 290 000 ₽, просрочка 6 дней. Рекомендую позвонить.

> **Товар на грани нуля** — Профлист: остаток 42 листа, расход 18/день, запас на 2.3 дня. Срок поставки 5 дней. 3 заказа на 87 000 ₽ под угрозой. Рекомендую заказать на 3 недели.

Для такого уровня нужны: история платежей, среднедневной расход, сроки поставок — это Слои 2 и 3.

---

## 14. Репозиторий

GitHub: `https://github.com/theclaudman/serverpal`

Локальный путь: `C:\Users\klodc\Desktop\Serverpal\`

Последний коммит на GitHub: `9c6fb2f после websocket` — содержит все изменения шага 13 + мелочи + незавершённый WebSocket код.
