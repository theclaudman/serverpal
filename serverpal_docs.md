# ServerPal — Техническая документация

## Общее описание

ServerPal — это система из трёх взаимосвязанных Python-сервисов, которые работают поверх базы данных **1С:УНФ 3.0** (Управление Небольшой Фирмой). Система предоставляет веб-интерфейс для визуализации данных, AI-ассистента для запросов к базе и автоматический финансовый дайджест.

Все три сервиса запускаются параллельно и общаются друг с другом по HTTP.

---

## Архитектура системы

```
┌──────────────────────────────────────────────────────────────────┐
│                        БРАУЗЕР ПОЛЬЗОВАТЕЛЯ                      │
│                                                                  │
│   Прайс-лист   Дашборд менеджеров   Продажи   Чат AI   Дайджест │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP (порт 8000)
                            ▼
               ┌────────────────────────┐
               │   ДАШБОРД (порт 8000)  │  ← Server_fastapi_1c
               │    main.py (FastAPI)   │
               └──┬──────────┬────────┬─┘
                  │          │        │
     HTTP (OData) │          │        │ HTTP
                  ▼          ▼        ▼
           ┌──────────┐ ┌────────┐ ┌────────────────┐
           │ 1С:УНФ   │ │ AI     │ │ Digest-сервис  │
           │ OData API│ │ Bridge │ │ (порт 8002)    │
           │          │ │ :8001  │ │                │
           └──────────┘ └───┬────┘ └──────┬─────────┘
                            │             │
                     ┌──────┴──────┐      │
                     │  LLM-сервер │      │
                     │ (LM Studio  │◄─────┘
                     │  или OpenAI)│
                     └─────────────┘
```

### Порты

| Сервис | Порт | Назначение |
|--------|------|------------|
| Дашборд (Server_fastapi_1c) | 8000 | Веб-интерфейс, HTML-страницы, прокси к AI и Digest |
| AI Bridge (server_ai) | 8001 | Чат-ассистент, отчёты, запросы к 1С через язык запросов |
| Digest API (server_digest_ai) | 8002 | Финансовый дайджест, вопросы по данным |
| LLM-сервер (LM Studio) | 1234 | Локальная языковая модель |

---

## Порядок запуска

Сервисы запускаются в любом порядке, но для полноценной работы нужны все три:

**1. Digest-сервис (порт 8002):**
```bash
cd server_digest_ai-main/server_digest_ai-main
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
python server.py
```

**2. Дашборд (порт 8000):**
```bash
cd Server_fastapi_1c-main/Server_fastapi_1c-main
python -m venv venv
venv\Scripts\activate
pip install fastapi uvicorn python-multipart
python main.py
```

**3. AI Bridge (порт 8001):**
```bash
cd server_ai-main/server_ai-main
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**4. LLM-сервер:** запустить LM Studio, загрузить модель, установить контекст 16384 токенов.

---

## Сервис 1: Дашборд (Server_fastapi_1c)

### Назначение

Основной веб-интерфейс. Пользователь заходит через браузер, регистрируется с данными подключения к 1С, и получает доступ ко всем разделам. Сервис выступает прослойкой — сам данных не хранит (кроме учётных записей), всё получает из 1С на лету.

### Структура файлов

```
├── main.py                   # Маршруты, сессии, рендеринг
├── config.py                 # SECRET_KEY, UUID видов цен, URL других сервисов
├── database.py               # SQLite: пользователи (логин, пароль, URL базы 1С)
├── users.db                  # SQLite-база (создаётся автоматически)
├── services/
│   ├── onec_client.py        # HTTP-клиент к 1С OData
│   ├── data_builder.py       # Сборка прайс-листа
│   ├── dashboard_builder.py  # KPI менеджеров
│   ├── sales_builder.py      # Отчёт по продажам
│   ├── ai_client.py          # Клиент к AI Bridge (:8001)
│   └── digest_client.py      # Клиент к Digest API (:8002)
└── templates/                # HTML-шаблоны (7 страниц)
```

### Как работает авторизация

1. Пользователь заходит на `/register` и вводит: URL базы 1С (напр. `http://192.168.1.10/unf_dashboard`), логин и пароль 1С.
2. Сервис проверяет подключение к 1С, вызывая `fetch_employees()`.
3. Если успешно — сохраняет профиль в SQLite и выдаёт подписанную cookie-сессию (HMAC-SHA256, время жизни 12 часов).
4. При последующих запросах из cookie извлекаются `onec_base_url`, `user`, `password` и записываются в `ContextVar` — изоляция между параллельными async-запросами.

**Важно:** после входа SQLite больше не используется — всё из cookie. Пароль хранится в cookie открытым текстом (подписан, но не зашифрован).

### Страницы

| Путь | Что показывает |
|------|---------------|
| `/` | Главная — навигация по разделам |
| `/price-list` | Прайс-лист: товары с ценами (розничная/оптовая), остатками и свободными |
| `/dashboard/managers` | KPI менеджеров: выручка, прибыль, оплаты, заказы, долги, CRM-события |
| `/report/sales` | Детализация продаж по расходным накладным + график по дням |
| `/chat` | Чат с AI-ассистентом (проксирует запросы в AI Bridge) |
| `/digest` | Финансовый дайджест (проксирует в Digest API) |

### Как работает прайс-лист

Одновременно загружаются из 1С: номенклатура, цены (SliceLast — последний срез), остатки (Balance), резервы (Balance), группы товаров. Затем `data_builder.py` сводит всё в одну таблицу: для каждого товара берёт цены по GUID видов цен из `config.py`, вычисляет «Свободно» = Остаток − Резерв. Товары без цен, папки, исключённые из прайса и недействительные — отфильтровываются.

### Как работает дашборд менеджеров

`dashboard_builder.py` получает 6 наборов данных: сотрудники, заказы, доходы/расходы, оплаты, долги, CRM-события. Для каждого активного сотрудника:

- Находит его заказы за период.
- Считает выручку и прибыль через регистр «Доходы и расходы» (привязка по заказу).
- Считает оплаты через «Расчёты с покупателями».
- Считает долги из балансов «Расчёты с покупателями».
- Подсчитывает CRM-события: звонки и письма.

Результат — JSON-массив менеджеров с KPI + итоги, который вставляется в HTML-шаблон.

### Как работает отчёт по продажам

Загружает расходные накладные с табличной частью «Запасы» за период. Для каждой строки накладной вычисляет себестоимость пропорционально доле строки в общей выручке заказа (через регистр «Доходы и расходы»). Резолвит GUIDы номенклатуры, контрагентов, сотрудников и заказов в человеческие названия. Формирует ежедневный ряд выручки для графика Chart.js.

### Связь с 1С (`onec_client.py`)

Все запросы — GET к OData API: `http://{server}/{publication}/odata/standard.odata/{Сущность}?$format=json&...`. Используется `urllib` (без сторонних HTTP-библиотек). Кириллица в URL экранируется через `urllib.parse.quote()`. Basic Auth из `ContextVar` текущего запроса. Таймаут — 30 секунд.

Используемые OData-сущности: `Catalog_Номенклатура`, `Catalog_Сотрудники`, `Catalog_Контрагенты`, `InformationRegister_ЦеныНоменклатуры/SliceLast`, `AccumulationRegister_ЗапасыНаСкладах/Balance`, `AccumulationRegister_РезервыТоваровОрганизаций/Balance`, `Document_ЗаказПокупателя`, `Document_РасходнаяНакладная`, `AccumulationRegister_ДоходыИРасходы/Turnovers`, `AccumulationRegister_РасчетыСПокупателями/Balance` и `/Turnovers`, `Document_Событие`.

---

## Сервис 2: AI Bridge (server_ai)

### Назначение

Сервис-посредник между 1С и LLM (через OpenAI-совместимый API). Принимает текстовые запросы, при необходимости сам ходит в базу 1С (function calling) и формирует ответ. Также генерирует отчёты по расписанию.

### Структура файлов

```
app/
├── main.py                # FastAPI, lifespan, маршруты
├── core/
│   ├── config.py          # Настройки через .env (pydantic-settings)
│   ├── scheduler.py       # APScheduler: ежемесячные и квартальные отчёты
│   └── security.py        # base_id = MD5(ip + login)[:12]
├── api/routes/
│   ├── chat.py            # POST /chat/ — произвольный запрос к AI
│   ├── reports.py         # POST /report/daily и /report/weekly
│   └── query.py           # POST /query/ — прямой запрос к 1С
├── models/
│   └── schemas.py         # Pydantic-модели
├── services/
│   ├── ai_service.py      # Работа с LLM: chat + reports + function calling
│   ├── onec_service.py    # HTTP к 1С через /hs/ai/query (POST)
│   └── storage_service.py # Сохранение отчётов в файловую систему
├── tools/
│   ├── definitions.py     # Описание инструментов для LLM
│   └── executor.py        # Диспетчер вызова инструментов
├── prompts/               # Системные промпты: chat.txt, daily/weekly/monthly/quarterly_report.txt
├── knowledge_base.txt     # Полный анализ объектов конфигурации 1С УНФ 3.0
└── requirements.txt
```

### Как работает чат (function calling)

Дашборд отправляет `POST /chat/` с промптом и credentials 1С. `ai_service.answer_prompt()`:

1. Загружает системный промпт из `prompts/chat.txt` — в нём перечислены доступные запросы на языке 1С (остатки, продажи, дебиторка, кредиторка, деньги и т.д.).
2. Первый вызов LLM с `tools=[execute_1c_query]` и `tool_choice="auto"`.
3. Если LLM решает вызвать инструмент — парсит аргументы, выполняет запрос к 1С через `POST http://{ip}/hs/ai/query` (Basic Auth), получает JSON-результат.
4. Добавляет результат в историю сообщений как `role: tool` и снова вызывает LLM.
5. Цикл до 5 итераций или пока LLM не даст финальный ответ.

**Важно:** на стороне 1С должен быть HTTP-сервис по пути `/hs/ai/query`, принимающий POST с полем `query` (текст запроса на языке 1С).

### Идентификация баз

Каждая база 1С идентифицируется по `MD5(ip + "_" + login)[:12]` — это `base_id`. Под ним создаётся папка в `data/connected_bases/{base_id}/`.

### Автоматические отчёты

Планировщик APScheduler при старте регистрирует две задачи:

- **Ежемесячный отчёт** — 1-го числа в 06:00. Собирает все daily-отчёты за прошлый месяц, объединяет текст, отправляет в LLM с промптом `monthly_report.txt`.
- **Ежеквартальный** — 1 янв/апр/июл/окт в 06:30. Собирает monthly-отчёты за прошлый квартал.

### Файловое хранилище отчётов

```
data/connected_bases/{base_id}/
├── daily_reports/     report_2026-04-12.md
├── weekly_reports/    report_2026-04-12.md
├── monthly_reports/   report_2026-04-01.md
└── quarterly_reports/ report_2026-01-01.md
```

### Конфигурация

Через `.env` файл (pydantic-settings):

| Переменная | Умолчание | Описание |
|------------|-----------|----------|
| `OPENAI_API_KEY` | `lm-studio` | API-ключ LLM |
| `OPENAI_BASE_URL` | `http://localhost:1234/v1` | Адрес LLM API |
| `OPENAI_MODEL` | `dolphin-2.9.4-llama3.1-8b` | Модель |
| `MAX_TOOL_ITERATIONS` | 5 | Макс. итераций function calling |

---

## Сервис 3: Digest API (server_digest_ai)

### Назначение

Автоматически загружает данные из 1С через OData, агрегирует в компактный текст, вычисляет финансовые метрики и отправляет в LLM для формирования аналитического дайджеста. Руководитель получает готовый отчёт и может задавать вопросы по данным.

### Структура файлов

```
├── server.py              # FastAPI на порту 8002
├── api_models.py          # Pydantic-модели
├── digest.py              # Точка входа: CLI + API-функция
├── aggregator.py          # Оркестрация: загрузка всех блоков → текст
├── block_loader.py        # Универсальный загрузчик YAML-блоков
├── metrics_loader.py      # Вычисление метрик из YAML
├── lm_client.py           # Клиент к LLM (LM Studio / OpenAI)
├── onec_client.py         # HTTP к 1С OData (через requests)
├── anonymizer.py          # Маскировка контрагентов
├── context_builder.py     # Кэш контекста (in-memory, TTL 4 часа)
├── mask_config.json       # Какие поля маскировать
├── blocks/                # YAML-конфиги блоков данных
├── metrics/               # YAML-конфиги метрик
└── prompts/               # Системные промпты
```

### Ключевая идея: конфигурация без кода

Новый блок данных — создать YAML в `blocks/`. Новая метрика — создать YAML в `metrics/`. Новое чувствительное поле для маскировки — добавить запись в `mask_config.json`. Менять код не нужно.

### Как работает генерация дайджеста

Вызов `POST /api/digest` запускает цепочку:

**1. Загрузка YAML-конфигов** — `block_loader.load_all_blocks()` читает все `blocks/*.yaml`, сортирует по `priority`. Блоки с `priority: null` — вспомогательные (данные для зависимостей, в текст не попадают).

**2. Обработка каждого блока** — `process_block()` для каждого YAML выполняет полный цикл:
   - **Загрузка из 1С** — OData GET-запрос по параметрам из `source:` (entity, fields, filter, period, orderby, top).
   - **Join с родителем** — если есть `depends_on` с `merge: join_parent`, приклеивает поля из вспомогательного блока (напр. дата из шапки накладной к строкам).
   - **Вычисления** — `compute:` в YAML задаёт формулы (divide, subtract, days_from_today и т.д.).
   - **Резолв GUIDов** — `resolve:` превращает GUIDы в человеческие названия через батч-запросы к справочникам 1С.
   - **Маскировка** — если `anonymize=True` и есть `mask:`, чувствительные поля заменяются на псевдонимы (Контрагент_001).
   - **Агрегация** — стратегия из `aggregation.type`: `total_by_field`, `group_sum`, `classify`, `list_top`, `time_series`, `none`.
   - **Форматирование** — превращает результат агрегации в текст.

**3. Метрики** — `metrics_loader.compute_metrics()` вычисляет показатели (ликвидность, концентрация дебиторки, покрытие кредиторки) из итогов блоков.

**4. Отправка в LLM** — `lm_client.send()` передаёт агрегированный текст и системный промпт.

**5. Демаскировка** — если были псевдонимы, в ответе LLM они заменяются обратно на реальные названия.

### Блоки данных (blocks/)

| Файл | Приоритет | Что загружает | Агрегация |
|------|-----------|--------------|-----------|
| money.yaml | 1 | Остатки денежных средств | total_by_field |
| sales.yaml | 2 | Расходные накладные за день | group_sum по контрагенту |
| debts.yaml | 3 | Дебиторка (Balance) | group_sum по контрагенту |
| debts_overdue.yaml | 4 | Просроченная дебиторка | list_top (топ по сумме) |
| stocks.yaml | 4 | Остатки на складах | classify (critical/at_risk/top) |
| creditors.yaml | 5 | Кредиторка (Balance) | group_sum по контрагенту |
| returns.yaml | 6 | Чеки возврата за 90 дней | time_series |
| sales_items.yaml | 7 | Продажи по товарам | group_sum по номенклатуре |

Вспомогательные блоки (priority: null): `order_items` (состав заказов для расчёта резервов), `sales_headers` (шапки накладных для join), `debts_doc_headers` (шапки для просрочки).

### Метрики (metrics/)

| Файл | Формула | Порог предупреждения |
|------|---------|---------------------|
| current_liquidity.yaml | деньги / кредиторка | < 1.0 — денег меньше долгов |
| debtor_concentration.yaml | топ-1 должник / вся дебиторка | > 50% — зависимость от одного |
| debt_coverage.yaml | дебиторка / кредиторка | < 1.0 — дебиторка не покрывает |

### Анонимизация

При отправке в облачные LLM (OpenAI) контрагенты автоматически заменяются на псевдонимы: `ООО СтройГрупп → Контрагент_001`. Маскировка персистентная — реестр хранится в `data/clients/{client_id}/mask_registry.json`. Ответ LLM демаскируется перед отдачей клиенту (длинные маски заменяются первыми, чтобы Контрагент_100 не сломал Контрагент_1001).

### Кэш контекста

`context_builder.py` хранит в памяти (dict) агрегированный текст и реальные названия с TTL 4 часа. Это позволяет задавать вопросы (`POST /api/ask`) по данным последнего дайджеста без повторной загрузки из 1С.

### CLI-режим

Дайджест можно запускать из терминала:
```bash
python digest.py                      # за вчера
python digest.py --date 2026-04-28    # за конкретную дату
python digest.py --provider openai    # через OpenAI (с анонимизацией)
python digest.py --no-llm             # только агрегация
python digest.py --debug              # промежуточные файлы каждого блока
```

Результаты сохраняются в `data/runs/{timestamp}/`.

---

## Взаимодействие сервисов

### Дашборд → AI Bridge

Когда пользователь пишет в чат на странице `/chat`, дашборд отправляет `POST http://localhost:8001/chat/` с JSON:
```json
{
  "credentials": {"login": "...", "password": "...", "ip": "192.168.1.10/unf_dashboard"},
  "prompt": "Покажи остатки на складе"
}
```
AI Bridge принимает, вызывает LLM с function calling, при необходимости запрашивает данные через `POST http://{ip}/hs/ai/query` и возвращает `{"answer": "..."}`.

### Дашборд → Digest API

Страница `/digest` обращается к трём эндпоинтам:
- `GET /api/providers` — узнать доступные LLM.
- `POST /api/digest` — сгенерировать дайджест. Digest API сам ходит в 1С через OData.
- `POST /api/ask` — задать вопрос по данным последнего дайджеста.

Дашборд передаёт credentials из своей cookie-сессии и достраивает URL до OData-пути.

### Различия в подключении к 1С

| Сервис | Протокол | Путь | Библиотека |
|--------|----------|------|------------|
| Дашборд | OData REST (GET) | `/{publication}/odata/standard.odata/{Entity}` | urllib |
| AI Bridge | HTTP-сервис 1С (POST) | `/hs/ai/query` | urllib |
| Digest API | OData REST (GET) | `/{publication}/odata/standard.odata/{Entity}` | requests |

---

## Конфигурация

### config.py (Дашборд)

```python
SECRET_KEY = "change-me-in-production-use-random-string"  # Ключ HMAC-сессий
AI_SERVICE_URL = "http://localhost:8001"                    # AI Bridge
DIGEST_SERVICE_URL = "http://localhost:8002"                # Digest API
PRICE_TYPE_RETAIL = "55a36684-..."                          # UUID розничной цены
PRICE_TYPE_WHOLESALE = "05baa3c2-..."                       # UUID оптовой цены
```

### .env (AI Bridge)

```
OPENAI_API_KEY=lm-studio
OPENAI_BASE_URL=http://localhost:1234/v1
OPENAI_MODEL=dolphin-2.9.4-llama3.1-8b
```

### .env (Digest API)

```
OPENAI_API_KEY=sk-...   # только для OpenAI-провайдера
```

---

## База данных

Единственная БД — SQLite `users.db` в дашборде. Одна таблица:

```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password        TEXT NOT NULL,
    onec_base_url   TEXT NOT NULL DEFAULT ''
);
```

`onec_base_url` — полный URL до базы 1С без `/odata/standard.odata` (напр. `http://192.168.1.10/unf_dashboard`). При каждом запросе к 1С путь OData дописывается автоматически.

---

## Зависимости

### Дашборд
`fastapi`, `uvicorn`, `python-multipart` — и всё. HTTP-клиент к 1С через стандартный `urllib`.

### AI Bridge
`fastapi`, `uvicorn`, `openai`, `pydantic-settings`, `apscheduler`, `httpx`, `python-dotenv`, `pytest`.

### Digest API
`fastapi`, `uvicorn`, `requests`, `pyyaml`, `pydantic`, `python-dotenv`.

---

## Известные ограничения

- Пароль 1С хранится открытым текстом в подписанной cookie (не зашифрован).
- Нет HTTPS — трафик в открытом виде.
- Нет rate limiting — `/login` уязвим к брутфорсу.
- Нет кэширования данных 1С — каждая загрузка страницы → запросы к 1С.
- Кэш контекста Digest API — in-memory dict, теряется при перезапуске.
- AI Bridge требует HTTP-сервис на стороне 1С (`/hs/ai/query`), который нужно развернуть отдельно.
- Knowledge base (`knowledge_base.txt`) содержит полный анализ объектов конфигурации 1С УНФ 3.0 — используется как контекст для LLM.
