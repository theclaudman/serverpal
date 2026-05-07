# ServerPal Chat Handoff

Дата: 2026-05-07

Этот файл фиксирует контекст текущей переписки, чтобы следующий чат Codex/GPT мог продолжить работу без повторного разбора проекта.

## 1. Что за проект

ServerPal — ИИ-финдиректор/ассистент на базе 1С:УНФ 3.0.

Система состоит из трёх FastAPI-сервисов:

| Сервис | Путь | Порт | Назначение |
|---|---|---:|---|
| Dashboard | `Server_fastapi_1c-main/Server_fastapi_1c-main` | 9001 | Web UI, авторизация, чат, дайджест, прайс, отчёты, prompt UI |
| AI Bridge | `server_ai-main/server_ai-main` | 8001 | LLM chat, function calling, запросы к 1С |
| Digest API | `server_digest_ai-main/server_digest_ai-main` | 8002 | OData-агрегация, финансовый дайджест, вопросы по данным |

Внешние зависимости:

- 1С:УНФ через OData.
- LM Studio локально на `1234` или внешний OpenAI-compatible API.

Важно: локально использовать `127.0.0.1`, не `localhost`, чтобы не ловить IPv6/IPv4 проблемы.

## 2. Что обсуждали

### WebSocket

Ранее были ошибки WS, потому что пользователь работал через антидетект-браузер. После проверки выяснили:

- WebSocket-код фактически активен:
  - Dashboard: `/ws/chat`
  - AI Bridge: `/chat/ws`
  - UI chat пытается WS и имеет POST fallback на `/api/chat`.
- В обычном браузере локальный запуск работает.
- Антидетект-браузер может ломать cookie или WS upgrade.

Решение: WS оставить включённым, POST fallback сохранить.

### `main.py` и `main old.py`

Был вопрос, менялся ли `main.py`. Codex в начале ничего не менял; `main.py` уже был изменён до анализа.

Позже по плану:

- `main.py` сделан каноническим.
- `main old.py` удалён как backup-файл.
- `reload=True` в dashboard заменён на `reload=False` для стабильного запуска через `run_all.py`.

### Локальный production vs VPS

Обсуждали два варианта:

1. **Local production на мощном ПК**
   - всё крутится на локальном ПК;
   - подходит для офисной сети;
   - можно сделать стабильно через Docker, volumes, backups, healthchecks;
   - не является полноценным публичным сайтом без домена/HTTPS.

2. **VPS production**
   - публичный сайт: домен + HTTPS + Nginx;
   - dashboard публично доступен;
   - AI Bridge и Digest API должны быть внутренними;
   - если 1С/LM Studio остаются на локальном ПК, нужен защищённый канал VPS -> ПК.

Вывод: если пользователи должны заходить на сайт из интернета, нужен VPS + домен + HTTPS. “Только фронтенд на VPS, backend на ПК” не рекомендован как основная схема, потому что dashboard в проекте — это не чистый frontend, а FastAPI backend с авторизацией, cookie, API и WS proxy.

### Слои данных

Обсуждали смысл слоёв:

- **Слой 1** — данные из 1С: продажи, деньги, дебиторка, кредиторка, остатки, возвраты, заказы, контрагенты, менеджеры.
- **Слой 2** — внешние измеримые факторы: курс валют, ключевая ставка, календарь, праздники, сезонность, погода, логистика, внешние API.
- **Слой 3** — ручной ввод событий: задержки поставщиков, обещанные оплаты, отпуска менеджеров, акции, крупные заказы, риски клиентов.

Сейчас реализован в основном слой 1. Слои 2 и 3 — развитие продукта после стабилизации production-контура.

### Список от друга перед деплоем

Друг предложил:

- Nginx reverse proxy + HTTPS
- Бэкапы и мониторинг
- Слой 2
- Слой 3
- RAG/фильтрация `knowledge_base.txt`
- Jinja2 вместо `html.replace`
- Alembic migrations

Оценка:

- До production обязательно: Nginx/HTTPS, backups, базовый monitoring, понятная migration strategy.
- Можно отложить: слой 2, слой 3, RAG, Jinja2.
- Вместо Alembic на данном этапе рекомендован простой versioned migration script, потому что проект маленький, SQLite и схема ещё простая.

### Jinja2 и `replace`

Сейчас dashboard местами рендерит HTML через `.replace(...)`.

Минусы:

- хрупко;
- сложнее поддерживать;
- риск XSS;
- плохо масштабируется для циклов/условий/сложного UI.

Jinja2 — нормальный шаблонизатор для FastAPI. Переход нужен, но не блокирует первый production.

### RAG

Обсуждали оптимизацию `knowledge_base.txt`.

Варианты:

- локальный RAG: embedding model + vector store + index script;
- облачный RAG/OpenAI file search: быстрее, но данные уходят наружу и нужен API.

Решение: RAG не делать до production-контура. Вернуться позже, если `knowledge_base.txt` реально тормозит или путает LLM.

## 3. Что было реализовано

### Стабилизация локального запуска

Изменено:

- `Server_fastapi_1c-main/.../main.py`
  - `reload=False` в запуске dashboard.
  - Глобальный обработчик ошибок и логирование оставлены.
- `Server_fastapi_1c-main/.../requirements.txt`
  - добавлены недостающие зависимости: `uvicorn[standard]`, `httpx`, `websockets`, `slowapi`, `cryptography`, `bcrypt`, `pydantic-settings`, `python-dotenv`.

Проверено:

- `py_compile` ключевых файлов.
- health всех трёх сервисов.
- `scripts/smoke_check.py`.

### Очистка репозитория

Удалены backup/runtime из git:

- `main old.py`
- `chat old.py`
- `test_ws_backup.py`
- `__pycache__` / `.pyc`
- `users.db` снят с git-отслеживания, но оставлен на диске.

Обновлён `.gitignore`:

- `.env`
- `users.db`
- `*.db`
- logs/data/cache
- `.smoke-logs`
- backup-файлы

### Единый env

Добавлен корневой `.env.example`.

Сервисы теперь поддерживают общий корневой `.env`, но сохраняют fallback к локальному `.env` сервиса.

Важные переменные:

- `SECRET_KEY`
- `ENCRYPTION_KEY`
- `AI_SERVICE_URL`
- `DIGEST_SERVICE_URL`
- `PRICE_TYPE_RETAIL`
- `PRICE_TYPE_WHOLESALE`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `LMSTUDIO_BASE_URL`
- `LMSTUDIO_MODEL`
- `DASHBOARD_DB_PATH`

### Тесты

Тесты AI Bridge разделены:

- быстрые unit-тесты запускаются по умолчанию;
- integration-тесты с 1С/LLM помечены `integration` и пропускаются без `tests/.env.test`.

Команда:

```powershell
cd C:\Users\klodc\Desktop\Serverpal\server_ai-main\server_ai-main
python -m pytest -q
```

Результат после изменений:

```text
3 passed, 12 skipped
```

Есть warning про `.pytest_cache` из-за прав sandbox, не критично.

### Scripts

Добавлены/используются:

- `scripts/smoke_check.py`
  - стартует Digest API, AI Bridge, Dashboard;
  - проверяет `/health`;
  - гасит процессы.
- `scripts/dev_check.py`
  - запускает `py_compile`;
  - запускает pytest;
  - запускает smoke-check.

Команда:

```powershell
python scripts\dev_check.py
```

Результат:

```text
dev check passed
```

### Документация

Добавлены/переоформлены:

- `README.md` в корне — короткий вход в проект.
- `PROJECT_TRANSFER.md` — главный transfer/spec файл для следующих чатов/разработчиков.
- `CHAT_HANDOFF.md` — этот файл, конспект переписки.

Локальные README сервисов пользователь уже отметил как указывающие на корневую документацию.

### Docker-точка

Добавлено:

- `docker-compose.yml`
- `.dockerignore`
- Dockerfile для Dashboard
- Dockerfile для AI Bridge
- Dockerfile для Digest API
- `requirements-dev.txt`

Проверено:

```powershell
docker compose config
```

Compose валиден. Docker выводил warning про доступ к `C:\Users\klodc\.docker\config.json`, но это проблема прав Docker config на машине, не ошибка compose-файла.

Реальный `docker compose up --build` ещё не прогоняли.

## 4. Текущее состояние команд

Локальный запуск:

```powershell
cd C:\Users\klodc\Desktop\Serverpal
python run_all.py
```

Smoke:

```powershell
python scripts\smoke_check.py --timeout 30
```

Полная dev-проверка:

```powershell
python scripts\dev_check.py
```

Docker config:

```powershell
docker compose config
```

Планируемый Docker build:

```powershell
docker compose up --build
```

Для Docker local с LM Studio на хосте в `.env`:

```env
OPENAI_BASE_URL=http://host.docker.internal:1234/v1
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
```

## 5. Что осталось сделать следующим

Рекомендуемый следующий порядок:

1. **Закоммитить текущий cleanup/dev workflow/Docker skeleton**, если всё устраивает.
2. **Запустить реальный Docker build**:
   ```powershell
   docker compose up --build
   ```
   Исправить ошибки сборки/запуска контейнеров.
3. **Local production mode**:
   - стабильный запуск на мощном ПК;
   - persistent volumes;
   - `DASHBOARD_DB_PATH`;
   - registration guard/invite code;
   - backup script;
   - prod check script;
   - инструкция автозапуска после перезагрузки.
4. **Backup/restore**:
   - скрипт `scripts/backup.py`;
   - возможно `scripts/restore.py`;
   - архивировать `users.db`, data/logs, важные volumes.
5. **Migration strategy**:
   - простой versioned migration script;
   - не Alembic пока.
6. **VPS production**:
   - `docker-compose.prod.yml`;
   - Nginx;
   - HTTPS Let’s Encrypt;
   - WebSocket proxy headers;
   - backend-сервисы закрыть внутрь Docker-сети.
7. **Дизайн dashboard**.
8. Потом продуктовые функции:
   - слой 3;
   - слой 2;
   - Jinja2;
   - RAG/knowledge base optimization.

## 6. Важные решения

- Не сливать три сервиса в один Python app.
- Объединять сервисы через Docker Compose.
- Корневой `.env` — главный источник конфигурации.
- Локальный no-Docker workflow должен продолжать работать.
- Для публичного доступа нужен VPS + домен + HTTPS.
- “Только frontend на VPS, backend на локальном ПК” не рекомендован.
- До первого production не делать большие продуктовые фичи типа слоя 2/3/RAG.
- Сначала инфраструктура, backup, стабильный запуск, потом дизайн и функции.

## 7. Осторожности для следующего чата

- Не удалять реальные `.env`.
- Не удалять локальный `users.db` с диска без явного подтверждения.
- Не делать `git reset --hard`.
- Не возвращать `main old.py` / `chat old.py`.
- Перед любым Docker/VPS шагом запускать:
  ```powershell
  python scripts\dev_check.py
  ```
- После изменений в Docker запускать:
  ```powershell
  docker compose config
  ```
