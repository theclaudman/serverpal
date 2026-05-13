# ServerPal Project Transfer

Canonical handoff/status file for Codex/GPT sessions and developers. Keep this file current when architecture, startup, env, tests, security, or deployment flow changes. Keep `README.md` as a short project overview only.

## Summary

ServerPal is an AI finance assistant for 1C:UNF 3.0. It loads company data from 1C through OData, aggregates it, sends compact context to an LLM, and exposes a web UI for executives.

Core modes:

- Dashboard: KPI pages, price list, sales report, prompt management.
- Chat: free-form questions over 1C data through AI Bridge.
- Digest: proactive financial analysis and Q&A over aggregated data.

Current runtime is intentionally split into three FastAPI services. Do not merge services in code casually. Docker packaging is not final yet: when we reach Docker, decide explicitly whether to run one container or three containers.

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

- Login/register with encrypted 1C credentials and encrypted cookie session.
- Dashboard pages: price list, manager dashboard, sales report, chat, digest, prompts.
- Prompt management in dashboard DB; prompts are passed to AI Bridge and Digest API.
- WebSocket chat streaming through `/ws/chat` -> `/chat/ws`.
- POST fallback remains active through `/api/chat` if WebSocket fails.
- Root `.env` is mandatory; service-local `.env` fallback was removed.
- AI Bridge and Digest API require `X-Service-API-Key` on internal routes.
- Dashboard passes `X-Service-API-Key` to AI Bridge and Digest API, including WebSocket proxy.
- AI Bridge uses `OPENAI_API_KEY`; Digest external provider uses `DIGEST_OPENAI_API_KEY` with `OPENAI_API_KEY` as compatibility fallback.
- LLM-generated 1C queries are validated as read-only before execution.
- Dashboard cookie security is configurable through `COOKIE_SECURE` and `COOKIE_SAMESITE`.
- Dashboard registration is closed by default through `REGISTRATION_ENABLED=false`.
- Optional registration token access: set `REGISTRATION_TOKEN` and open `/register?token=<token>`.
- `run_all.py` binds AI Bridge and Digest API to `127.0.0.1`.
- Direct AI Bridge startup also binds to `127.0.0.1:8001` to match `run_all.py`.
- Root `requirements-all.txt` is available for no-Docker local setup.
- Dashboard SQLite schema is managed by a simple versioned migration runner.
- Price type GUIDs are per-user/client settings in dashboard DB; root `.env` values are optional fallback only.
- Account settings API supports reading/updating per-user price type GUIDs through `/api/account/settings`.
- Account settings UI is available at `/account/settings` for editing per-user price type GUIDs.
- Local backup/restore scripts cover dashboard DB plus service logs/data.
- Smoke check for starting all three services.
- Security check covers internal API key enforcement and registration guard.
- Fast pytest default: unit tests run, integration tests are skipped unless explicitly enabled.

Known debt:

- Some source files still contain mojibake in Russian comments/messages.
- Dashboard DB has a simple versioned migration runner; broader migration tooling is still minimal.
- Dashboard templates use string replacement rather than Jinja2.
- Digest context cache is in-memory.
- `knowledge_base.txt` is loaded broadly and should eventually become RAG/filtering.
- VPS deployment still needs Nginx + HTTPS + WebSocket proxy headers.

## Environment

Use one root `.env` copied from `.env.example`. The root `.env` is mandatory in the hardened configuration.

Key local defaults:

```env
AI_SERVICE_URL=http://127.0.0.1:8001
DIGEST_SERVICE_URL=http://127.0.0.1:8002
OPENAI_BASE_URL=http://127.0.0.1:1234/v1
OPENAI_API_KEY=lm-studio
DIGEST_OPENAI_API_KEY=
DIGEST_OPENAI_BASE_URL=https://api.hydraai.ru/v1
DIGEST_OPENAI_MODEL=gpt-4o
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
ALLOWED_ORIGINS=http://127.0.0.1:9001,http://127.0.0.1:8001,http://127.0.0.1:8002
SERVICE_API_KEY=<shared internal service key>
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
REGISTRATION_ENABLED=false
REGISTRATION_TOKEN=
PRICE_TYPE_RETAIL=
PRICE_TYPE_WHOLESALE=
```

For local onboarding:

- Public local registration: `REGISTRATION_ENABLED=true`.
- Token registration: set `REGISTRATION_TOKEN=<secret>` and open `/register?token=<secret>`.

Never commit real `.env`, real API keys, `users.db`, logs, caches, or generated data.

## Development Workflow

Start all services locally:

```powershell
python -m pip install -r requirements-all.txt
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

Run production-like env validation:

```powershell
python scripts\prod_check.py
python scripts\prod_check.py --prod
```

`prod_check.py` validates the root `.env`; `--prod` adds stricter checks such as `COOKIE_SECURE=true` and an external Digest LLM key.

Run the combined dev check from root:

```powershell
python scripts\dev_check.py
```

`dev_check.py` runs py_compile, AI Bridge pytest, `scripts/security_check.py`, and the smoke check.

Run dashboard SQLite migrations explicitly:

```powershell
python scripts\migrate_dashboard_db.py
```

Dashboard startup still calls migrations through `init_db()` for compatibility.

Create and restore local backups:

```powershell
python scripts\backup.py
python scripts\restore.py backups\serverpal-backup-YYYYMMDD-HHMMSS.zip --yes
```

Backups go to `backups/` by default and are ignored by git. `.env` is not included unless `--include-env` is passed.

Integration tests require live 1C/LLM and are skipped by default. Enable them with `server_ai-main/server_ai-main/tests/.env.test`:

```env
ONEC_IP=127.0.0.1/publication
ONEC_LOGIN=...
ONEC_PASSWORD=...
RUN_LLM_TESTS=1
```

## Verification Status

Last verified after splitting Digest external LLM key:

```powershell
python scripts\dev_check.py
```

Result:

```text
7 passed, 12 skipped
security check passed
smoke check passed
dev check passed
```

Known warning: pytest may warn that it cannot write `.pytest_cache` because of local permissions. Tests still pass.

## Docker Direction

Docker discussion is intentionally postponed. Current repository has `docker-compose.yml`, service Dockerfiles, and fail-fast env handling, but before real Docker work decide:

- one container with process supervisor vs three service containers;
- local production vs VPS production;
- how Dashboard, AI Bridge, Digest API, LM Studio, and 1C should communicate in that mode.

Current compose assumes three service containers:

- Dashboard sees AI Bridge as `http://ai-bridge:8001`.
- Dashboard sees Digest API as `http://digest-api:8002`.
- Dashboard is the only service intended to be exposed publicly.
- Compose requires explicit secrets/IDs instead of falling back to `change-me` values.

For local Docker with LM Studio on the host, use:

```env
OPENAI_BASE_URL=http://host.docker.internal:1234/v1
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
```

For VPS production:

- Add Nginx as reverse proxy.
- Terminate HTTPS with Let's Encrypt.
- Preserve WebSocket headers: `Upgrade`, `Connection`, and long read timeouts.
- Keep AI Bridge and Digest API internal.
- Add backup policy for dashboard SQLite, logs, and data volumes.

## Roadmap

Recently completed:

- Clean documentation: keep `README.md` short, keep `PROJECT_TRANSFER.md` canonical, remove old chat handoff.
- Remove dead commented `execute_query` code from `onec_service.py`.
- Add focused security checks for `X-Service-API-Key`, registration guard, and read-only query validation.
- Make `run_all.py` console output readable on Windows and add root `requirements-all.txt`.
- Add versioned Dashboard SQLite migrations and a root migration script.
- Add local backup/restore scripts for dashboard DB, service logs, and service data.
- Move price type GUIDs from global required env into per-user/client DB settings with env fallback and account settings API.
- Add account settings UI for editing per-user/client price type GUIDs.
- Split Digest external LLM key into `DIGEST_OPENAI_API_KEY` while keeping `OPENAI_API_KEY` fallback.
- Remove stale service-local docs; keep `PROJECT_TRANSFER.md` as the canonical handoff/status file.
- Align direct AI Bridge startup with `run_all.py` (`127.0.0.1:8001`).
- Add clearer Digest LLM diagnostics for provider/model/base URL and HTTP response failures.
- Shorten `README.md` to a compact project overview that points to `PROJECT_TRANSFER.md`.
- Add `scripts/prod_check.py` for production-like `.env` validation.

Recommended next order:

1. Clean remaining mojibake only where it is real file corruption, not console output.
2. Discuss Docker shape before changing deployment.
3. Add Nginx + HTTPS deployment docs/config if going VPS.
4. Refresh dashboard UI for demo.
5. Add product features: OData YAML UI, compute rules, manual events layer, external factors, RAG/filtering.

## Do Not Break

- Keep `/api/chat`, `/ws/chat`, and AI Bridge `/chat/ws` compatible.
- Keep POST fallback for chat.
- Keep root `.env` as the preferred configuration source.
- Keep `SERVICE_API_KEY` enforcement on internal AI Bridge and Digest routes.
- Keep read-only validation before sending LLM-generated queries to 1C.
- Keep registration closed by default.
- Keep local no-Docker workflow working.
