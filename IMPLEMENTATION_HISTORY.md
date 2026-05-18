# ServerPal Implementation History

This file is a chronological engineering history of how ServerPal was assembled. It is intentionally separate from `PROJECT_TRANSFER.md`: this file explains how and why the project evolved, while `PROJECT_TRANSFER.md` remains the operational handoff/runbook.

Do not add secrets, real passwords, real API keys, or full `.env` values here.

## 01. Initial Service Split

Goal:

- Build ServerPal as an AI finance assistant for 1C:UNF 3.0.
- Keep UI, LLM orchestration, and digest aggregation as separate services.

What was built:

- Dashboard service in `Server_fastapi_1c-main/Server_fastapi_1c-main`.
- AI Bridge service in `server_ai-main/server_ai-main`.
- Digest API service in `server_digest_ai-main/server_digest_ai-main`.

Why:

- Dashboard owns web UI, login/session state, SQLite users/settings/prompts, and report pages.
- AI Bridge owns chat, OpenAI-compatible LLM access, function/tool flow, and 1C query proxying.
- Digest API owns OData aggregation, financial digest generation, and Q&A over digest data.

Result:

- Browser talks only to Dashboard.
- Dashboard talks server-side to AI Bridge and Digest API.
- AI Bridge/Digest can be internal-only in production.

Important ports:

```text
Dashboard: 9001
AI Bridge: 8001
Digest API: 8002
```

## 02. Local Startup Unification

Goal:

- Make local development start all services from one command.

What was built:

- Root `run_all.py` starts:
  - Digest API on `127.0.0.1:8002`;
  - AI Bridge on `127.0.0.1:8001`;
  - Dashboard on `0.0.0.0:9001`.

Why:

- Running three terminals manually was error-prone.
- Local Dashboard must use local service URLs:

```env
AI_SERVICE_URL=http://127.0.0.1:8001
DIGEST_SERVICE_URL=http://127.0.0.1:8002
```

Result:

- Local run is:

```powershell
python -m pip install -r requirements-all.txt
python run_all.py
```

- Dashboard opens at:

```text
http://127.0.0.1:9001
```

Important local note:

- Use `127.0.0.1`, not `localhost`, for local checks.
- If using a virtualenv, activate `.venv` before installing dependencies.

## 03. Environment Policy

Goal:

- Move secrets and runtime settings into one root `.env`.
- Avoid service-local `.env` fallback confusion.

What was standardized:

- Root `.env` is the source of truth.
- `.env.example` documents expected variables.
- Real `.env` is ignored by git.

Critical values:

```env
SECRET_KEY=<session-cookie secret>
ENCRYPTION_KEY=<Fernet key for stored 1C passwords>
SERVICE_API_KEY=<internal shared API key>
OPENAI_API_KEY=<AI Bridge provider key>
DIGEST_OPENAI_API_KEY=<Digest provider key>
```

Why:

- `ENCRYPTION_KEY` protects stored 1C passwords in Dashboard SQLite.
- `SERVICE_API_KEY` protects internal Dashboard -> AI/Digest calls.
- Losing `ENCRYPTION_KEY` means old stored 1C passwords cannot be decrypted.

Result:

- Code can be restored from git.
- `.env`, Dashboard SQLite, Docker volumes, and TLS certs must be backed up separately.

## 04. Docker Compose Layout

Goal:

- Support both simple/local Docker and production Docker without duplicating everything.

What was built:

- `docker-compose.yml` as base compose.
- `docker-compose.prod.yml` as production override.

Why:

- Base compose can expose Dashboard on `:9001` for testing.
- Production override adds Nginx/HTTPS and removes public app-service ports.

Result:

- Production command uses both files:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --force-recreate
```

Important invariant:

- Do not collapse base/prod compose files unless there is a deliberate replacement design.

## 05. VPS Production Shape

Goal:

- Run ServerPal on a public VPS safely.

What was deployed:

- VPS working copy:

```text
/opt/serverpal
```

- Public site:

```text
https://1rpanel.fun
```

- Public IP:

```text
194.147.215.155
```

- Docker services:
  - `serverpal-nginx-1`;
  - `serverpal-dashboard-1`;
  - `serverpal-ai-bridge-1`;
  - `serverpal-digest-api-1`.

Why:

- Public ingress should be only Nginx on `80/443`.
- Dashboard, AI Bridge, and Digest API should remain internal Docker services.

Result:

- Expected production shape:

```text
nginx        0.0.0.0:80->80, 0.0.0.0:443->443
dashboard    healthy 9001/tcp
ai-bridge    healthy 8001/tcp
digest-api   healthy 8002/tcp
```

Health check:

```bash
curl https://1rpanel.fun/health
```

Expected:

```json
{"status":"ok","services":{"dashboard":true,"ai_bridge":true,"digest_api":true}}
```

## 06. Nginx And HTTPS

Goal:

- Terminate HTTPS at Nginx and proxy all public traffic to Dashboard.

What was configured:

- Nginx image: `nginx:1.27-alpine`.
- Nginx template:

```text
deploy/nginx/templates/serverpal.conf.template
```

- Let's Encrypt lineage currently used:

```text
/etc/letsencrypt/live/1rpanel.fun-0001/fullchain.pem
/etc/letsencrypt/live/1rpanel.fun-0001/privkey.pem
```

Why:

- A previous non-`-0001` certificate path had invalid/non-certificate content and caused Nginx certificate load errors.

Result:

- HTTP redirects to HTTPS.
- Regular requests proxy to `dashboard:9001`.
- `/ws/chat` proxies with WebSocket headers.
- Dashboard/AI/Digest app ports are not public in production.

## 07. 1C Publication Through Apache HTTPS

Goal:

- Make a test 1C file database reachable by ServerPal from the VPS.

What was set up:

- Windows PC publishes 1C `/Eu` through Apache HTTPS.
- External endpoint:

```text
https://client1.1rpanel.fun:8443/Eu
```

- OData endpoint:

```text
https://client1.1rpanel.fun:8443/Eu/odata/standard.odata/
```

Why:

- Browser should not talk directly to customer 1C.
- ServerPal containers on VPS need outbound server-side access to OData.

Result:

- From VPS, OData returns `401 Unauthorized`, which is correct: 1C is reachable and asks for Basic Auth.

Checks:

```bash
curl -k -I https://client1.1rpanel.fun:8443/Eu
curl -k -I https://client1.1rpanel.fun:8443/Eu/odata/standard.odata/
```

Expected OData result:

```text
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="1C:Enterprise 8.3"
```

## 08. IP Allowlist For 1C

Goal:

- Avoid exposing 1C publication to the whole internet.

What was configured:

- Apache `/Eu` publication allows the VPS IP:

```text
194.147.215.155
```

Why:

- ServerPal on VPS needs access.
- Random internet clients should not get direct access to the 1C publication.

Result:

- VPS can reach OData and receives `401`.
- Non-allowed networks should be forbidden.

Important operational point:

- If local development needs direct access to the same external 1C publication, the local public IP must also be allowed, or a VPN/tunnel must be used.
- If ServerPal and Apache/1C are on the same PC, a local URL such as `http://127.0.0.1:8080/Eu` can be used instead.

## 09. Registration And Users

Goal:

- Control whether new ServerPal users can register.

What was implemented:

- Registration is controlled by:

```env
REGISTRATION_ENABLED=true|false
REGISTRATION_TOKEN=<optional token>
```

- `docker-compose.prod.yml` reads `REGISTRATION_ENABLED` from `.env`.

Why:

- Registration should be open only during onboarding windows.
- Production should normally run with registration closed.

Result:

- Register at:

```text
https://1rpanel.fun/register
```

- Then close registration again:

```env
REGISTRATION_ENABLED=false
```

Future work:

- Add `/admin` panel so registration can be toggled without editing `.env` and restarting containers.

## 10. Login 502 Root Cause

Goal:

- Fix a login flow that loaded for about 30 seconds and returned `502`.

Observed:

```text
POST /login -> 502 (30.4s)
```

Discovery:

- Network from VPS to 1C was OK.
- Network from Dashboard container to 1C was OK.
- Dashboard login validates 1C by calling an OData employees endpoint.
- User `res1` had stale stored 1C base URL:

```text
http://client1.1rpanel.fun/Eu
```

Fix:

- Updated `res1` in Dashboard SQLite to:

```text
https://client1.1rpanel.fun:8443/Eu
```

Check saved user URLs:

```bash
docker exec serverpal-dashboard-1 python -c "import sqlite3; conn=sqlite3.connect('/data/users.db'); conn.row_factory=sqlite3.Row; [print(dict(r)) for r in conn.execute('select username, onec_base_url from users')]"
```

Result:

- Login became successful.
- Dashboard logs showed `Catalog_Сотрудники` returned `200 OK`, then `POST /login -> 302`.

Important behavior:

- Current login form password is used both for ServerPal password verification and as the 1C Basic Auth password for the session.

## 11. Login Error Diagnostics

Goal:

- Avoid blank or unclear "Не удалось подключиться к 1С" messages.

What was added:

- Login connection errors are classified into user-facing reasons where possible:
  - `401 Unauthorized`: 1C rejected login/password;
  - `403 Forbidden`: no access to publication;
  - `404 Not Found`: wrong OData URL;
  - timeout: 1C did not answer within the request timeout;
  - 5xx: Apache/1C server error;
  - network request errors.

Why:

- Operators need to distinguish wrong credentials from wrong URL, timeout, or server-side failure.

Result:

- Login page now shows more concrete reasons.
- Dashboard logs include traceback for failed login 1C checks.

## 12. Safe Deploy Command

Goal:

- Avoid public `502 Bad Gateway` after app container recreation.

Observed:

- App containers were recreated and healthy.
- Nginx container had been running for days.
- Public site returned `502`.
- Nginx could reach Dashboard after manual check/recreate.

Working check:

```bash
docker exec serverpal-nginx-1 wget -S -O- http://dashboard:9001/health
```

Fix:

- Recreate Nginx or the full stack.

Operational decision:

- Use full recreate after deploy:

```bash
cd /opt/serverpal
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --force-recreate
curl https://1rpanel.fun/health
```

Why:

- It avoids stale Nginx/upstream state after app containers change.
- It is simple and reliable for current project size.

Tradeoff:

- Brief downtime during full recreate.

## 13. Light AI-Dashboard UI Shell

Goal:

- Move UI closer to the provided light AI-dashboard mockup without introducing a frontend framework.

What was implemented:

- Shared static assets:

```text
Server_fastapi_1c-main/Server_fastapi_1c-main/static/app-shell.css
Server_fastapi_1c-main/Server_fastapi_1c-main/static/app-shell.js
```

- FastAPI static mount:

```text
/static
```

- Server-side helper wraps protected pages with shell assets and `data-active`.
- `/` now renders the digest workspace.
- `/digest`, `/price-list`, `/dashboard/managers`, `/report/sales`, `/chat`, `/account/settings`, and `/prompts` get the shared shell.

Why:

- Existing frontend is plain HTML templates.
- A React/Vue rewrite would add build tooling and delay.
- Injecting a shell keeps existing page JS and backend contracts intact.

Result:

- Left sidebar navigation.
- Top title/user area.
- Static right panel "Сегодня важно".
- Responsive layout.
- Login/register remain standalone pages.

Known limitation:

- The shell is layered over old standalone templates. Some table/report pages may still need visual polish.

## 14. Digest Conversation Persistence

Goal:

- Preserve digest conversation when the user refreshes the page or navigates away and back.

What was added:

- SQLite migration `003_digest_history`.
- New table:

```text
digest_messages
```

- Server helpers to:
  - add digest messages;
  - read digest history;
  - clear digest history.

- API:

```text
GET /api/digest/history
DELETE /api/digest/history
```

Behavior:

- Successful digest generation clears the user's previous current digest history and saves the new digest.
- Successful Q&A saves user question and assistant answer.
- Page load restores saved digest conversation.

Why:

- The original UI kept conversation only in the browser DOM.
- A refresh or route switch lost all messages.

Result:

- Current digest conversation survives refresh/navigation.

Important limitation:

- This is one current conversation per user, not a full archive.
- A future archive should add `digest_threads` and store messages by `thread_id`.
- Digest API still keeps analysis context in memory; after Digest API restart, the visible saved history may exist, but asking a new question may require regenerating the digest.

## 15. Digest History Clear Button

Goal:

- Let the user clear the current digest conversation manually.

What was added:

- Button "Очистить" on the digest page.
- Client call to:

```text
DELETE /api/digest/history
```

- UI reset:
  - messages removed from screen;
  - stored history deleted from SQLite;
  - question input disabled;
  - welcome state restored.

Why:

- Once history persists, users need a clear/reset action.

Result:

- User can clear the current digest conversation without touching SQLite.

## 16. Digest UI Cleanup

Goal:

- Remove extra visual noise from the new digest UI.

What was changed:

- Removed the visible label:

```text
Дайджест — <date>
```

- Kept digest body, metadata, and `.md` download link.
- Removed the empty panel below "Сегодня важно".

Why:

- The label duplicated the digest content and looked like a service artifact.
- The empty right card created unused visual space.

Result:

- Cleaner digest screen.

## 17. Transfer File Update

Goal:

- Keep the operational handoff current after deployment, UI, and digest-state changes.

What was updated in `PROJECT_TRANSFER.md`:

- Current production-like status.
- Light UI shell notes.
- Digest history and clear behavior.
- Login 502 root cause.
- Safe deploy with `--build --force-recreate`.
- Known issues and next steps.
- "Do Not Break" rules for static shell and digest history.

Why:

- Future Codex sessions and developers need a reliable handoff without reconstructing everything from chat history.

Result:

- `PROJECT_TRANSFER.md` is now the operational reference.
- This file is the chronological implementation history.

## 18. Localhost / 1C Connectivity Understanding

Goal:

- Clarify how local ServerPal, local 1C, ports, and router forwarding interact.

Important conclusions:

- `127.0.0.1` means "this same computer only".
- `192.168.x.x` means the PC's LAN address.
- `0.0.0.0` means "listen on all interfaces" and is not a URL clients connect to.
- If ServerPal and 1C/Apache run on the same PC, a local 1C URL can be:

```text
http://127.0.0.1/Eu
http://127.0.0.1:8080/Eu
https://127.0.0.1:8443/Eu
```

- If VPS or another computer must reach 1C, Apache must listen on a LAN/external interface, such as `192.168.x.x:<port>` or `0.0.0.0:<port>`.
- Router port forwarding targets the PC's LAN IP, not `127.0.0.1`.

Why this matters:

- Local-only development can work without port forwarding.
- External VPS access requires HTTPS/public routing/allowlist/VPN/tunnel.

## 19. Backup And Rebuild Lessons

Goal:

- Understand what can be restored from git and what must be backed up separately.

Git restores:

- Source code.
- Templates.
- Docker compose files.
- Scripts.
- `.env.example`.

Git does not restore:

- Real `.env`.
- Dashboard SQLite (`users.db` or `/data/users.db`).
- Docker volumes.
- TLS certificates.
- Runtime `data/`.
- Logs and backups.

Critical production state:

```text
/opt/serverpal/.env
Docker volume: serverpal_dashboard_data
/etc/letsencrypt
```

Critical local state if preserving users/history:

```text
.env
Server_fastapi_1c-main/Server_fastapi_1c-main/users.db
server_ai-main/server_ai-main/data/
server_digest_ai-main/server_digest_ai-main/data/
```

Important rule:

- If keeping an old `users.db`, keep the same `ENCRYPTION_KEY`.
- If starting from a clean DB, a new `ENCRYPTION_KEY` is acceptable.

## 20. Current Technical Debt And Direction

Main current risk:

- Heavy OData pages are too slow with file 1C over the internet.

Observed timings:

```text
/price-list: about 448-463 seconds
/report/sales: about 166 seconds
```

Findings:

- VPS CPU/RAM are not the main bottleneck.
- Dashboard network I/O reached hundreds of MB.
- File 1C over home/office internet is expected to be slow.

Next engineering priorities:

1. Add detailed timing and payload-size logging around every OData request.
2. Optimize `/price-list` first.
3. Cache catalogs/dictionaries aggressively.
4. Add filters, pagination, and incremental loading.
5. Add cache warming before demos.
6. Add account UI to edit saved 1C URL without SQLite commands.
7. Add `/admin` for registration/user management.
8. Add real anomaly calculations for the right panel.
9. Add a multi-thread digest conversation archive if needed.
10. Add production backup timer and restore drill.

Do not break:

- `/api/chat`, `/ws/chat`, and AI Bridge `/chat/ws`.
- Internal `SERVICE_API_KEY` enforcement.
- Local non-Docker workflow.
- Production public ingress only through Nginx `80/443`.
- 1C publication protection by IP allowlist.
- Digest history scoped to authenticated user.
- Static UI shell availability at `/static/app-shell.css` and `/static/app-shell.js`.

## 21. Local Windows Development Run In `C:\Users\klodc\Desktop\SP`

Goal:

- Start the current local working copy without Docker while 1C/Apache runs on the same Windows PC.

What was done:

- Created local `.venv`.
- Installed `requirements-all.txt`.
- Created a local root `.env` for development only.
- Set local registration open so a user can be created through:

```text
http://127.0.0.1:9001/register
```

- Verified health endpoints:

```text
http://127.0.0.1:8001/health
http://127.0.0.1:8002/health
http://127.0.0.1:9001/health
```

Important local 1C URL:

```text
http://127.0.0.1/Eu
```

Do not enter the full `/odata/standard.odata` URL for Dashboard registration unless the Dashboard URL builder is updated.

Apache change for local work:

- `C:\Apache24\conf\httpd.conf` previously allowed only the VPS IP for `/Eu`.
- Added `Require local` while keeping `Require ip 194.147.215.155`.
- Backup file created:

```text
C:\Apache24\conf\httpd.conf.serverpal-local.bak
```

Validation:

```powershell
curl.exe -k -I --max-time 5 http://127.0.0.1/Eu/odata/standard.odata/
```

Expected:

```text
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="1C:Enterprise 8.3"
```

Fix discovered during local startup:

- AI Bridge crashed on a clean checkout because `logging.FileHandler(settings.logs_dir / "app.log")` ran before the `logs/` directory existed.
- `server_ai-main/server_ai-main/app/main.py` now creates `settings.data_dir` and `settings.logs_dir` before logging setup.

## 22. Price List Diagnostic Logging

Goal:

- Measure why `/price-list` is slow before redesigning it.

What was added:

- `Server_fastapi_1c-main/Server_fastapi_1c-main/services/onec_client.py`
  logs every Dashboard OData request:
  - operation name;
  - entity path;
  - HTTP status;
  - row count;
  - response byte size;
  - request duration.

- `Server_fastapi_1c-main/Server_fastapi_1c-main/main.py`
  logs `/price-list` stages:
  - cache hit;
  - OData fetch summary;
  - Python build duration;
  - JSON payload sizes;
  - final HTML size and total duration.

Next step for the following session:

1. Open:

```text
http://127.0.0.1:9001/price-list
```

2. Read:

```powershell
Get-Content Server_fastapi_1c-main\Server_fastapi_1c-main\logs\dashboard.log -Tail 80
```

3. Decide whether to prioritize OData filtering/caching or the UI/API rewrite.

Likely next implementation:

- Make `/price-list` a lightweight HTML page.
- Add `/api/price-list` with pagination, search, and later local SQLite/cache snapshots.
