# ServerPal

ServerPal is a local-first AI finance assistant for 1C:UNF. The repository contains three cooperating FastAPI services:

| Service | Port | Purpose |
|---|---:|---|
| Dashboard | 9001 | Web UI, auth, prompts, chat, reports, service health |
| AI Bridge | 8001 | LLM chat, function calling, 1C query proxy |
| Digest API | 8002 | OData aggregation, financial digest, Q&A over digest data |

The detailed handoff/specification for Codex/GPT or another developer is in [PROJECT_TRANSFER.md](PROJECT_TRANSFER.md).

## Local Start

```powershell
cd C:\Users\klodc\Desktop\Serverpal
copy .env.example .env
# edit .env: SECRET_KEY, ENCRYPTION_KEY, SERVICE_API_KEY, price type GUIDs, LLM settings
python run_all.py
```

Open:

```text
http://127.0.0.1:9001
```

Use `127.0.0.1`, not `localhost`, for local checks. Anti-detect browsers can break cookies or WebSocket upgrades; use a normal Chrome/Edge/Firefox profile for debugging.

The root `.env` is required. Service-local `.env` files are not used as fallback in the hardened configuration.

## Checks

Fast local smoke check for all services:

```powershell
python scripts\smoke_check.py --timeout 30
```

Unit tests that do not require live 1C/LLM:

```powershell
cd server_ai-main\server_ai-main
python -m pytest -q
```

Run the full development check from the repository root:

```powershell
python scripts\dev_check.py
```

Integration tests are marked `integration` and require `server_ai-main/server_ai-main/tests/.env.test` with `ONEC_IP`, `ONEC_LOGIN`, and `RUN_LLM_TESTS=1`.

## Docker Preview

Docker is prepared as the single deployment entrypoint, while the code remains split into three services:

```powershell
copy .env.example .env
docker compose up --build
```

For local Docker with LM Studio running on the host, set these in `.env`:

```env
OPENAI_BASE_URL=http://host.docker.internal:1234/v1
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
```

`docker-compose.yml` is fail-fast for required secrets and IDs. It will not silently use production-unsafe defaults for `SECRET_KEY`, `ENCRYPTION_KEY`, `SERVICE_API_KEY`, or price type GUIDs.

The next production step is Nginx + HTTPS + WebSocket proxy headers for VPS deployment.
