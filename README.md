# ServerPal

ServerPal is an AI finance assistant for 1C:UNF. It reads 1C data through OData, builds dashboards and reports, and sends compact context to an LLM for chat and financial digest workflows.

Current implementation status, architecture notes, decisions, and roadmap live in [PROJECT_TRANSFER.md](PROJECT_TRANSFER.md). Keep this README short.

## Services

| Service | Port | Purpose |
|---|---:|---|
| Dashboard | 9001 | Web UI, auth, prompts, chat, reports, service health |
| AI Bridge | 8001 | LLM chat, function calling, 1C query proxy |
| Digest API | 8002 | OData aggregation, financial digest, Q&A over digest data |

## Local Start

```powershell
copy .env.example .env
python -m pip install -r requirements-all.txt
python run_all.py
```

Open:

```text
http://127.0.0.1:9001
```

Use `127.0.0.1`, not `localhost`, for local checks. The root `.env` is required; service-local `.env` files are not used as fallback.

## Checks

```powershell
python scripts\dev_check.py
python scripts\prod_check.py
python scripts\smoke_check.py --timeout 30
```

Dashboard DB migrations and local backup helpers:

```powershell
python scripts\migrate_dashboard_db.py
python scripts\backup.py
python scripts\restore.py backups\serverpal-backup-YYYYMMDD-HHMMSS.zip --yes
```

## Docker/VPS

Docker/VPS deployment is not final yet. Before production deployment, read [PROJECT_TRANSFER.md](PROJECT_TRANSFER.md) and decide the VPS networking model for 1C OData, Nginx/HTTPS, WebSocket proxying, volumes, and backup policy.
