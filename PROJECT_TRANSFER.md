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
- Smoke check for starting all three services.
- Fast pytest default: unit tests run, integration tests are skipped unless explicitly enabled.

Known debt:

- No DB migrations; SQLite schema changes are manual.
- Dashboard templates use string replacement rather than Jinja2.
- Digest context cache is in-memory.
- `knowledge_base.txt` is loaded broadly and should eventually become RAG/filtering.
- VPS deployment still needs Nginx + HTTPS + WS proxy headers.

## Environment

Use one root `.env` copied from `.env.example`.

Key local defaults:

```env
AI_SERVICE_URL=http://127.0.0.1:8001
DIGEST_SERVICE_URL=http://127.0.0.1:8002
OPENAI_BASE_URL=http://127.0.0.1:1234/v1
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
ALLOWED_ORIGINS=http://127.0.0.1:9001,http://127.0.0.1:8001,http://127.0.0.1:8002
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
- Keep local no-Docker workflow working; Docker is an additional deployment path, not a replacement.
