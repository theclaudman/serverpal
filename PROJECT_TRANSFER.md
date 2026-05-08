# ServerPal Project Transfer

This is the canonical handoff file for Codex/GPT sessions and developers. Keep it current when architecture, startup, env, tests, or deployment flow changes.

## Summary

ServerPal is an AI finance assistant for 1C:UNF 3.0. It loads company data from 1C through OData, aggregates it, sends compact context to an LLM, and exposes a web UI for executives.

Core modes:

- Dashboard: KPI pages, price list, sales report, prompt management.
- Chat: free-form questions over 1C data through AI Bridge.
- Digest: proactive financial analysis and Q&A over aggregated data.

The project is intentionally split into three services. Do not merge them into one FastAPI app before Docker; compose them at process/container level.

## Architecture

| Service | Path | Port | Responsibility |
|---|---|---:|---|
| Dashboard | `Server_fastapi_1c-main/Server_fastapi_1c-main` | 9001 | UI, auth, SQLite users/prompts, health, proxy to AI/Digest |
| AI Bridge | `server_ai-main/server_ai-main` | 8001 | Chat, OpenAI-compatible LLM client, function calling, 1C query proxy |
| Digest API | `server_digest_ai-main/server_digest_ai-main` | 8002 | OData blocks, aggregation, digest generation, digest Q&A |
| LM Studio | external/local | 1234 | Optional local OpenAI-compatible LLM server |

Browser -> Dashboard -> AI Bridge / Digest API -> LLM and 1C.

Important local convention: use `127.0.0.1`, not `localhost`, to avoid IPv6/IPv4 resolution issues.

## Current State

Implemented:

- Login/register with encrypted 1C credentials and cookie session.
- Dashboard pages: price list, manager dashboard, sales report, chat, digest, prompts.
- Prompt management in dashboard DB; prompts are passed to AI Bridge and Digest API.
- WebSocket chat streaming is active through `/ws/chat` -> `/chat/ws`.
- POST fallback remains active through `/api/chat` if WS fails.
- Unified root `.env` support with local service `.env` fallback.
- AI Bridge and Digest API require `X-Service-API-Key` on internal routes.
- LLM-generated 1C queries are validated as read-only before execution.
- Dashboard cookie security is configurable through `COOKIE_SECURE` and `COOKIE_SAMESITE`.
- Dashboard registration is closed by default through `REGISTRATION_ENABLED=false`; optional token access uses `REGISTRATION_TOKEN` and `/register?token=<token>`.
- Smoke check for starting all three services.
- Fast pytest default: unit tests run, integration tests are skipped unless explicitly enabled.

Known debt:

- No DB migrations; SQLite schema changes are manual.
- Dashboard templates use string replacement rather than Jinja2.
- Digest context cache is in-memory.
- `knowledge_base.txt` is loaded broadly and should eventually become RAG/filtering.
- VPS deployment still needs Nginx + HTTPS + WS proxy headers.

## Environment

Use one root `.env` copied from `.env.example`. The root `.env` is mandatory in the hardened configuration; service-local `.env` files should not be relied on.

Key local defaults:

```env
AI_SERVICE_URL=http://127.0.0.1:8001
DIGEST_SERVICE_URL=http://127.0.0.1:8002
OPENAI_BASE_URL=http://127.0.0.1:1234/v1
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
ALLOWED_ORIGINS=http://127.0.0.1:9001,http://127.0.0.1:8001,http://127.0.0.1:8002
SERVICE_API_KEY=<shared internal service key>
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
REGISTRATION_ENABLED=false
REGISTRATION_TOKEN=
```

For Docker local with LM Studio on the host, use:

```env
OPENAI_BASE_URL=http://host.docker.internal:1234/v1
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
```

Never commit real `.env`, real API keys, `users.db`, logs, caches, or generated data.

## Development Workflow

Start all services locally:

```powershell
python run_all.py
```

Smoke check all services:

```powershell
python scripts\smoke_check.py --timeout 30
```

Run default tests:

```powershell
cd server_ai-main\server_ai-main
python -m pytest -q
```

Run the combined dev check from root:

```powershell
python scripts\dev_check.py
```

Integration tests require live 1C/LLM and are skipped by default. Enable them with `server_ai-main/server_ai-main/tests/.env.test`:

```env
ONEC_IP=127.0.0.1/publication
ONEC_LOGIN=...
ONEC_PASSWORD=...
RUN_LLM_TESTS=1
```

## Docker Direction

Docker entrypoint is root `docker-compose.yml`. Each service has its own Dockerfile and dependencies. Compose wires services together through internal service names:

- Dashboard sees AI Bridge as `http://ai-bridge:8001`.
- Dashboard sees Digest API as `http://digest-api:8002`.
- Dashboard is the only service intended to be exposed publicly in production.
- Compose requires explicit secrets/IDs instead of falling back to `change-me` values.

For VPS production:

- Add Nginx as reverse proxy.
- Terminate HTTPS with Let's Encrypt.
- Preserve WebSocket headers: `Upgrade`, `Connection`, and long read timeouts.
- Keep AI Bridge and Digest API internal to the Docker network.
- Add backup policy for dashboard SQLite, logs, and data volumes.

## Roadmap

Recommended order:

1. Finish README/transfer cleanup and commit.
2. Validate local Docker compose.
3. Add Nginx + HTTPS deployment docs/config.
4. Refresh dashboard UI for demo.
5. Add UI for OData YAML blocks.
6. Add compute rules.
7. Add manual events layer.
8. Add external factors: exchange rates, key rate, calendar, seasonality.
9. Add DB migrations.
10. Optimize knowledge base with RAG/filtering.

## Do Not Break

- Keep `/api/chat`, `/ws/chat`, and AI Bridge `/chat/ws` compatible.
- Keep POST fallback for chat.
- Keep root `.env` as the preferred configuration source.
- Keep `SERVICE_API_KEY` enforcement on internal AI Bridge and Digest routes.
- Keep read-only validation before sending LLM-generated queries to 1C.
- Keep local no-Docker workflow working; Docker is an additional deployment path, not a replacement.


последние сообщения были:
Я тебя спрашивал что ещё можно улучшить ты не ответила хотя в проекте есть явные критические замечания о которых мне поведал друг:


AI Bridge и Digest API не имеют собственной авторизации на маршрутах. Если запускать локально через run_all.py, AI Bridge слушает 0.0.0.0:8001, а Digest 0.0.0.0:8002; при доступности машины в сети туда можно отправить credentials в body. Смотри chat.py, query.py, server.py.

Cookie сессии в dashboard шифруются, но не ставится secure=True. Для HTTPS/prod это обязательно, иначе cookie может уйти по HTTP. Смотри main.py и main.py.

SERVICE_API_KEY есть в .env.example и compose, но по коду AI Bridge я не увидел enforcement. То есть переменная существует как намерение, но не защищает API. Смотри config.py.

LLM tool execute_1c_query декларирован как “только SELECT/ВЫБРАТЬ”, но в коде нет валидации запроса перед отправкой в 1C. Сейчас это доверие к промпту/модели. Смотри ai_service.py и onec_service.py.

В execute_query остался print(query_text), который может светить бизнес-запросы в stdout/logs. Смотри onec_service.py.

Docker-compose содержит небезопасные дефолты для ключей и нулевые GUID типов цен. Для локалки нормально, для prod нужно fail-fast, а не fallback change-me. Смотри docker-compose.yml.

Локальная среда сейчас не запускает проверки: python не найден, а py.exe указывает на отсутствующий Python314. Поэтому py_compile и pytest я не смог выполнить.

.env нужно чтоб обязательно было в корне проекта, чтобы дальше если она не найдёт не падала на локальный .env сервиса,

Кодировка файлов сломана
В run_all.py и части файлов русские строки отображаются mojibake (Р•РґРёРЅ...). Это не всегда ломает запуск, но портит поддержку.

Нет единого runtime requirements в корне
Есть requirements-dev.txt, но он только для тестов. Для запуска надо ставить три сервисных файла. Лучше добавить requirements.txt или requirements-all.txt в корень.

Сервисные .env создают риск случайного чтения старых секретов
Ты правильно чувствуешь: если мы говорим “главный .env в корне”, то fallback на локальные .env может маскировать ошибку. Для строгой модели лучше: root .env обязателен, если его нет - падать с понятным сообщением.

Локальный и Docker режимы сейчас смешаны в голове и документации
Нужно явно разделить: “как запускать локально” и “как запускать Docker”. Сейчас проект как будто пытается быть сразу всем.

Да, замечания друга в основном правильные. Я должен был вынести это отдельным security/pre-production списком. По приоритету это важнее дизайна, слоя 2/3 и RAG.

Я бы сейчас поставил перед Docker/local production такой порядок.

P0: критично до любого production

Закрыть AI Bridge и Digest API авторизацией

Добавить обязательный X-Service-API-Key.
Dashboard должен передавать этот ключ при запросах к AI Bridge/Digest.
AI Bridge защищает /chat/, /query/, /report/*, /chat/ws.
Digest API защищает /api/digest, /api/ask, /api/providers, кроме /health.
Плюс для run_all.py: AI Bridge и Digest лучше слушают 127.0.0.1, а не 0.0.0.0.
Cookie security

Для prod/HTTPS ставить secure=True.
Добавить настройки:
COOKIE_SECURE=true/false
COOKIE_SAMESITE=lax
Локально без HTTPS можно COOKIE_SECURE=false, но в prod fail-fast, если false.
Enforce SERVICE_API_KEY

Сейчас переменная есть как намерение, но реально не защищает API.
Нужно сделать её обязательной для server-to-server запросов.
Валидация 1С-запросов от LLM

Перед отправкой в 1С разрешать только ВЫБРАТЬ / SELECT.
Запретить опасные слова: УДАЛИТЬ, ОБНОВИТЬ, ВСТАВИТЬ, DELETE, UPDATE, INSERT, DROP, POST, etc.
Это нужно и в ai_service.py, и в прямом /query/.
Убрать print(query_text)

Да, это утечка бизнес-запросов в stdout/logs.
Логировать только факт запроса и, максимум, длину/хэш.
Docker fail-fast

В docker-compose.yml нельзя оставлять production fallback типа change-me и нулевые GUID.
Для local можно иметь .env.example, но compose должен требовать реальные переменные:
SECRET_KEY: ${SECRET_KEY:?set SECRET_KEY}
ENCRYPTION_KEY: ${ENCRYPTION_KEY:?set ENCRYPTION_KEY}
Отдельно можно сделать docker-compose.local.yml с мягкими дефолтами, если нужно.
Root .env обязателен

Согласен. Fallback на сервисные .env удобен, но опасен: можно случайно читать старые секреты.
Лучше правило:
root .env обязателен;
если его нет, падать с понятной ошибкой;
сервисные .env больше не использовать.
P1: важно перед local production
8. Разделить local и Docker режимы в документации

Local dev
Local production Docker
VPS production
Сейчас это действительно смешивается.
Единый runtime requirements

Добавить requirements-all.txt в корень для no-Docker запуска.
Docker всё равно пусть использует сервисные requirements.
Python launcher

В моей среде python есть: C:\whisperx\venv\Scripts\python.exe.
py сломан/недоступен.
Команды лучше документировать через python, не py.
Если у тебя локально python не найден, надо чинить PATH/venv отдельно.
Кодировка

У меня UTF-8 чтение показывало русские строки нормально, поэтому часть mojibake могла быть от PowerShell encoding.
Но нужно проверить файлы поиском по Рџ, Рћ, Рµ и при наличии реально битых строк исправить в UTF-8.
P2: после security/local production
12. Миграции

Я всё ещё советую простой versioned migration script, не Alembic на старте.
Jinja2
Важно, но после security. Это рефактор UI, не блокер первого production.
RAG, слой 2, слой 3
Это продуктовые улучшения. Их не надо делать до защиты API/cookie/backups/deploy-контура.
Мой рекомендуемый следующий шаг: Security hardening P0. То есть сначала закрыть внутренние API ключом, включить cookie security настройки, запретить опасные 1С-запросы, убрать print, сделать root .env обязательным и fail-fast в Docker. После этого уже запускать реальный docker compose up --build.









последнее изменение было:

Сделал первый P0-блок.

Что закрыто:

AI Bridge теперь требует X-Service-API-Key на:

/chat/
/query/
/report/daily
/report/weekly
/chat/ws
Digest API теперь требует X-Service-API-Key на:

/api/providers
/api/digest
/api/ask
/health оставлен открытым для healthcheck.
Dashboard теперь передаёт X-Service-API-Key в AI Bridge и Digest API, включая WebSocket-прокси.

SERVICE_API_KEY теперь реально enforced, а не просто лежит в env.

Сравнение ключей сделано через secrets.compare_digest.

Root .env теперь обязателен. Fallback на сервисные .env убран: если корневого .env нет, сервис падает с понятной ошибкой.

Cookie session получила настройки:

COOKIE_SECURE
COOKIE_SAMESITE
В run_all.py AI Bridge и Digest API больше не слушают 0.0.0.0:

AI Bridge: 127.0.0.1:8001
Digest API: 127.0.0.1:8002
Dashboard остаётся доступен на 0.0.0.0:9001.
Для Docker Digest получает DIGEST_HOST=0.0.0.0, чтобы контейнер был доступен внутри Docker-сети.

Добавлена read-only валидация 1С-запросов:

разрешены только запросы, начинающиеся с ВЫБРАТЬ или SELECT;
запрещены DELETE, UPDATE, INSERT, DROP, УДАЛИТЬ, ОБНОВИТЬ, ВСТАВИТЬ и т.д.
Убран print(query_text) из onec_service.py.

В error dict больше не возвращается полный текст запроса, только query_id по hash.

Docker compose переведён ближе к fail-fast:

SECRET_KEY, ENCRYPTION_KEY, SERVICE_API_KEY, price GUIDs и основные LLM URL теперь обязательные через ${VAR:?set ...}.
Документация обновлена: README.md и PROJECT_TRANSFER.md.

Проверки:

python scripts\dev_check.py
7 passed, 12 skipped
smoke check passed
dev check passed
docker compose config
OK
Есть старое предупреждение Docker про доступ к C:\Users\klodc\.docker\config.json, но compose валидный.

Важно: я создал локальный корневой .env из .env.example для проверок и поставил туда SERVICE_API_KEY=dev-local-service-key. Файл игнорируется git и не будет закоммичен. Перед реальным production надо заменить ключи/секреты/ценовые GUID на настоящие.

Registration guard для /register добавлен. Следующий практичный шаг: почистить mojibake/кодировку в handoff и Python-файлах, затем удалить мёртвый закомментированный execute_query из onec_service.py.
