# ServerPal Project Transfer

Canonical handoff/status file for future Codex/GPT sessions and developers. Keep this file current whenever architecture, startup, env, deployment, security, 1C connectivity, or operational flow changes. Keep `README.md` short; this file is the detailed operational handoff.

## Executive Summary

ServerPal is an AI finance assistant for 1C:UNF 3.0. It connects to 1C through OData, builds dashboard/report data, sends compact context to LLM services, and exposes a web UI for executives.

Current production-like state:

- ServerPal runs on a VPS at `https://1rpanel.fun`.
- VPS uses Docker Compose with three internal app services plus an Nginx reverse proxy.
- Public ingress is only `80/443` on Nginx.
- Dashboard, AI Bridge, and Digest API are internal Docker services.
- Test 1C file database is published from a Windows PC through Apache HTTPS:
  `https://client1.1rpanel.fun:8443/Eu`.
- Apache allowlist permits the 1C publication only from the VPS IP `194.147.215.155`.
- OData endpoint from VPS returns `401 Unauthorized`, which is correct because 1C is reachable and asking for credentials.

Current biggest product/tech risk:

- Heavy pages are slow because Dashboard downloads large OData payloads from a file 1C database over the internet. Example observed timings:
  - `/price-list`: about 448-463 seconds.
  - `/report/sales`: about 166 seconds.
- VPS CPU/RAM are not currently the primary bottleneck. Dashboard network I/O reached hundreds of MB.

## Architecture

| Component | Path / Host | Port | Responsibility |
|---|---|---:|---|
| Dashboard | `Server_fastapi_1c-main/Server_fastapi_1c-main` | 9001 internal | UI, login/register, SQLite users/prompts/settings, report pages, proxy to AI/Digest |
| AI Bridge | `server_ai-main/server_ai-main` | 8001 internal | Chat, OpenAI-compatible LLM access, function/tool flow, 1C query proxy |
| Digest API | `server_digest_ai-main/server_digest_ai-main` | 8002 internal | OData blocks, aggregation, digest generation, digest Q&A |
| Nginx on VPS | Docker image `nginx:1.27-alpine` | 80/443 public | HTTPS termination and reverse proxy to Dashboard |
| Test 1C Apache | Windows PC | 443 internal, 8443 external | HTTPS publication of 1C `/Eu` and OData |
| 1C file DB | Windows PC | behind Apache | Test data source |

Runtime request flow:

```text
Browser
  -> https://1rpanel.fun
  -> VPS Nginx
  -> dashboard:9001
  -> ai-bridge:8001 / digest-api:8002
  -> https://client1.1rpanel.fun:8443/Eu/odata/standard.odata
  -> Windows Apache
  -> 1C publication /Eu
```

Important distinction:

- Browser never talks directly to AI Bridge or Digest API.
- Browser should not need direct access to the customer 1C endpoint.
- OData requests are server-side outbound requests from VPS containers.

## Repository And Deployment Locations

Local working copy:

```text
C:\Users\klodc\Desktop\Serverpal — копия
```

VPS working copy:

```text
/opt/serverpal
```

GitHub repository:

```text
https://github.com/theclaudman/Serverpal
```

VPS:

```text
OS: Ubuntu 22.04
CPU/RAM: 1 CPU / 2048 MB RAM
Disk: 15 GB NVMe
Docker: installed and working
Docker Compose: installed and working
Public IP: 194.147.215.155
Primary domain: 1rpanel.fun
```

Current VPS compose mode:

```bash
cd /opt/serverpal
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Services And Entrypoints

Local non-Docker startup:

```powershell
cd "C:\Users\klodc\Desktop\Serverpal — копия"
python -m pip install -r requirements-all.txt
python run_all.py
```

`run_all.py` starts:

- Digest API at `127.0.0.1:8002`.
- AI Bridge at `127.0.0.1:8001`.
- Dashboard at `0.0.0.0:9001`.

Direct AI Bridge startup is aligned with `run_all.py`:

```python
uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=False)
```

Docker startup:

- `docker-compose.yml` is base/local/simple compose.
- `docker-compose.prod.yml` is production override.
- Keep both files. This is intentional:
  - base compose can expose Dashboard on `:9001` for temporary IP testing;
  - prod override adds Nginx/HTTPS and removes public `9001`.

Do not collapse into one compose file unless there is a clear replacement design.

## Current Production Deployment

VPS production command:

```bash
cd /opt/serverpal
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Expected `docker compose ps` shape:

```text
serverpal-nginx-1        Up      0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
serverpal-dashboard-1    healthy 9001/tcp
serverpal-ai-bridge-1    healthy 8001/tcp
serverpal-digest-api-1   healthy 8002/tcp
```

Important: Dashboard/AI/Digest may show `9001/tcp`, `8001/tcp`, `8002/tcp` in Docker output, but they must not show `0.0.0.0:9001->9001`, `0.0.0.0:8001->8001`, or `0.0.0.0:8002->8002` in production.

Health check:

```bash
curl https://1rpanel.fun/health
```

Expected:

```json
{"status":"ok","services":{"dashboard":true,"ai_bridge":true,"digest_api":true}}
```

HTTP redirect check:

```bash
curl -I http://1rpanel.fun
```

Expected:

```text
HTTP/1.1 301 Moved Permanently
Location: https://1rpanel.fun/
```

Do not use `curl -I https://1rpanel.fun/health` as the only check: `-I` sends `HEAD`, and FastAPI may return `405 Method Not Allowed`. Use plain `curl`.

## VPS TLS / Nginx

VPS domain:

```text
1rpanel.fun -> 194.147.215.155
```

Let’s Encrypt certificate was issued on VPS. Certbot created the active lineage with suffix:

```text
/etc/letsencrypt/live/1rpanel.fun-0001/fullchain.pem
/etc/letsencrypt/live/1rpanel.fun-0001/privkey.pem
```

The original `/etc/letsencrypt/live/1rpanel.fun` lineage had invalid/non-certificate content and caused Nginx errors:

```text
cannot load certificate "/etc/nginx/certs/fullchain.pem":
PEM_read_bio_X509_AUX() failed
```

Use the `-0001` paths unless the lineage is later cleaned up.

Relevant `.env` values on VPS:

```env
SERVERPAL_DOMAIN=1rpanel.fun
SERVERPAL_TLS_CERT_PATH=/etc/letsencrypt/live/1rpanel.fun-0001/fullchain.pem
SERVERPAL_TLS_KEY_PATH=/etc/letsencrypt/live/1rpanel.fun-0001/privkey.pem
ALLOWED_ORIGINS=https://1rpanel.fun
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
```

Nginx template:

```text
deploy/nginx/templates/serverpal.conf.template
```

Nginx responsibilities:

- redirect HTTP to HTTPS;
- proxy all regular traffic to `dashboard:9001`;
- proxy `/ws/chat` with WebSocket headers;
- set `Host`, `X-Real-IP`, `X-Forwarded-*`;
- use longer proxy timeouts for chat/digest/report flows.

## Environment Policy

Use root `.env`. Never commit real `.env`.

Important variables:

```env
SECRET_KEY=<long random string>
ENCRYPTION_KEY=<valid Fernet key>
SERVICE_API_KEY=<long random internal shared key>

AI_SERVICE_URL=http://ai-bridge:8001
DIGEST_SERVICE_URL=http://digest-api:8002

OPENAI_API_KEY=<AI Bridge OpenAI-compatible key>
OPENAI_BASE_URL=https://api.hydraai.ru/v1
OPENAI_MODEL=<working model>

DIGEST_OPENAI_API_KEY=<Digest external LLM key>
DIGEST_OPENAI_BASE_URL=https://api.hydraai.ru/v1
DIGEST_OPENAI_MODEL=gpt-4o

LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
LMSTUDIO_MODEL=<local model, only if using LM Studio>

COOKIE_SECURE=true
COOKIE_SAMESITE=lax
REGISTRATION_ENABLED=false
REGISTRATION_TOKEN=
```

Generate Fernet key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Generate random secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Validate production env:

```bash
python3 scripts/prod_check.py --prod
```

Known nuance:

- `docker-compose.prod.yml` should not hardcode `REGISTRATION_ENABLED=false`.
- It should use:

```yaml
REGISTRATION_ENABLED: ${REGISTRATION_ENABLED:-false}
```

This was changed and pulled on VPS.

## Registration Flow

Registration is currently controlled by `.env`:

```env
REGISTRATION_ENABLED=true
```

Apply:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Register:

```text
https://1rpanel.fun/register
```

After creating users, close registration:

```env
REGISTRATION_ENABLED=false
```

Apply again:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Check what the Dashboard container sees:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec dashboard env | grep REGISTRATION_ENABLED
```

Recommended future improvement:

- Add `/admin` panel and move registration toggle from env to DB-backed system settings.
- Keep env as bootstrap/default only.

## Proposed Admin Panel

Recommended MVP URL:

```text
https://1rpanel.fun/admin
```

Do not start with a separate `admin.1rpanel.fun` subdomain. Same domain is simpler because session/cookies and Nginx routing already work.

Recommended admin features:

- Toggle registration on/off without Docker restart.
- Manage registration token.
- List users.
- Block/unblock users.
- Promote/demote admin users.
- View 1C connection settings without showing stored password.
- Reset per-user 1C settings.
- View AI Bridge/Digest health.
- Test OData connection for a selected user.
- View last Dashboard/Digest errors.
- Show SQLite DB path and backup status.

Do not put these into the first admin version:

- editing `.env`;
- showing API keys/secrets;
- shell commands;
- TLS/Nginx management.

Recommended implementation:

- Add a DB table such as `system_settings`.
- Add `is_admin` to users or a separate user role field.
- Make `REGISTRATION_ENABLED` env only a bootstrap fallback if no DB setting exists.

## Docker Config Bug Fixed

Docker services originally crashed because code tried to locate root `.env` by searching for `run_all.py`. Docker images do not contain `run_all.py`, so AI Bridge and Digest failed on startup:

```text
RuntimeError: Не удалось найти корень проекта ServerPal
```

Fix applied:

- `get_env_file()` returns `None` when root project is not found.
- Pydantic settings then read real environment variables injected by Compose.
- Digest `server.py` and `lm_client.py` only call `load_dotenv()` if an env file exists.

Touched files:

```text
Server_fastapi_1c-main/Server_fastapi_1c-main/config.py
server_ai-main/server_ai-main/app/core/config.py
server_digest_ai-main/server_digest_ai-main/server.py
server_digest_ai-main/server_digest_ai-main/lm_client.py
```

This fix is required for Docker.

## 1C Connectivity Strategy

Supported/recommended production options:

1. **1C Fresh OData**  
   Best SaaS-like option when client uses Fresh and can provide OData URL + credentials.

2. **Customer web server publication + HTTPS + IP allowlist**  
   Normal on-prem production pattern:
   ```text
   ServerPal VPS -> HTTPS -> customer web server -> 1C OData
   ```
   The customer web server/firewall allows only the ServerPal VPS IP.

3. **Private VPN / WireGuard**  
   Good for local/private customer servers without exposing OData publicly.

4. **1C Link**  
   Use only after verifying that the exact OData path works through the Link URL:
   ```text
   https://<name>.link.1c.ru/<base>/odata/standard.odata/
   ```

5. **White IP + port forwarding**  
   Acceptable only with HTTPS, allowlist, and a low-privilege 1C user.

Avoid long-running plain HTTP for OData credentials.

## Current Test 1C Publication

Test PC/publication:

```text
Subdomain: client1.1rpanel.fun
1C publication name: /Eu
OData: /Eu/odata/standard.odata/
Windows PC LAN IP: 192.168.1.102
Router: Keenetic
Apache: Apache/2.4.66 (Win64) OpenSSL/3.6.1
```

Router forwarding:

```text
external TCP 8443 -> 192.168.1.102:443
```

Temporary HTTP forwarding was used for Let’s Encrypt validation:

```text
external TCP 80 -> 192.168.1.102:80
```

Port `80` can be closed after certificate issuance, but win-acme HTTP-01 auto-renewal will need it open again. Certificate expiry observed:

```text
2026-08-12
```

Recommended operational note:

- Keep only `8443 -> 443` open for normal operation.
- Re-open `80 -> 80` manually before renewal or later implement DNS-01.

## Windows Apache 1C Publication

Publication block in:

```text
C:\Apache24\conf\httpd.conf
```

Current intended block:

```apache
# 1c publication
Alias "/Eu" "C:/Users/klodc/Documents/Eu/"
<Directory "C:/Users/klodc/Documents/Eu/">
    AllowOverride All
    Options None
    Require ip 194.147.215.155
    SetHandler 1c-application
    ManagedApplicationDescriptor "C:/Users/klodc/Documents/Eu/default.vrd"
</Directory>
```

This allowlist is critical. It means only VPS IP can access the 1C publication.

Validation:

- From random browser/mobile internet: should return `403 Forbidden`.
- From VPS:

```bash
curl -I https://client1.1rpanel.fun:8443/Eu/odata/standard.odata/
```

Expected:

```text
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="1C:Enterprise 8.3"
```

`401` is correct: endpoint is reachable and asks for 1C credentials.

## Windows Apache TLS / win-acme

Certificate for `client1.1rpanel.fun` was issued on Windows using win-acme.

win-acme flow used:

- Run `C:\win-acme\wacs.exe` as Administrator.
- `M`: full options.
- `2`: manual input.
- Domain: `client1.1rpanel.fun`.
- Split: `4` single certificate.
- Validation: `1` HTTP file system.
- Webroot: `C:\Apache24\htdocs`.
- Key: RSA.
- Store: PEM files.
- PEM folder:

```text
C:\Apache24\conf\ssl\client1.1rpanel.fun
```

Generated files:

```text
client1.1rpanel.fun-chain.pem
client1.1rpanel.fun-chain-only.pem
client1.1rpanel.fun-crt.pem
client1.1rpanel.fun-key.pem
```

Apache SSL config:

```text
C:\Apache24\conf\extra\httpd-ssl.conf
```

Relevant directives inside the existing `<VirtualHost ...:443>`:

```apache
ServerName client1.1rpanel.fun:443

SSLCertificateFile "C:/Apache24/conf/ssl/client1.1rpanel.fun/client1.1rpanel.fun-crt.pem"
SSLCertificateKeyFile "C:/Apache24/conf/ssl/client1.1rpanel.fun/client1.1rpanel.fun-key.pem"
SSLCertificateChainFile "C:/Apache24/conf/ssl/client1.1rpanel.fun/client1.1rpanel.fun-chain.pem"
```

Old default certificate lines such as these must be commented or removed:

```apache
SSLCertificateFile "C:/server.crt"
SSLCertificateKeyFile "C:/server.key"
```

Apache config test:

```powershell
C:\Apache24\bin\httpd.exe -t
```

Expected:

```text
Syntax OK
```

Restart Apache:

```powershell
Restart-Service Apache2.4
```

If service name differs:

```powershell
Get-Service *apache*
```

## Correct 1C URL In ServerPal

Use this in ServerPal:

```text
https://client1.1rpanel.fun:8443/Eu
```

Or full OData URL:

```text
https://client1.1rpanel.fun:8443/Eu/odata/standard.odata
```

Prefer the short base publication URL:

```text
https://client1.1rpanel.fun:8443/Eu
```

Important bug/behavior observed:

- One saved user still had old HTTP URL:

```text
http://client1.1rpanel.fun/Eu
```

Dashboard logs confirmed requests still using HTTP:

```text
GET http://client1.1rpanel.fun/Eu/odata/standard.odata/...
```

Fix by:

- creating a new user with the correct HTTPS URL; or
- updating the existing SQLite user record; or
- adding/editing UI for connection settings if available.

Avoid entering a URL that already ends with `/odata/standard.odata` if code later appends it again. A previous failure showed duplicated path:

```text
/odata/standard.odata/odata/standard.odata/
```

The client helper is supposed to detect existing `/odata/standard.odata`, but if errors appear, prefer the short base URL.

## Performance Findings

Observed with `docker stats` during slow page loads:

```text
dashboard NET I/O: 195MB+, later 231MB+
dashboard RAM: about 450-470 MiB
dashboard CPU: about 7-16%
digest CPU: briefly about 60%, then idle
total RAM: not close to 2 GB limit
```

Observed Dashboard logs:

```text
GET /price-list -> 200 (463.533s)
GET /price-list -> 200 (448.297s)
GET /report/sales -> 200 (166.052s)
```

Conclusion:

- Current VPS is minimal but not saturated.
- Main issue is large OData data transfer and processing.
- File 1C database on a PC over the internet is expected to be slow.
- Repeated clicks can start duplicate heavy requests; avoid clicking the same heavy page repeatedly.

Likely heavy calls include:

- prices register `InformationRegister_ЦеныНоменклатуры/SliceLast`;
- counterparties catalog;
- employees catalog;
- customer orders;
- revenues/cost turnovers;
- sales documents for broad date ranges.

Optimization roadmap:

1. Add detailed timing around each OData request in `services/onec_client.py`.
2. Log payload sizes/counts per endpoint.
3. Cache dictionaries/catalogs aggressively.
4. Add date filters everywhere possible.
5. Reduce default periods for demo pages.
6. Avoid loading whole tabular sections when not needed.
7. Add pagination or incremental loading for price list.
8. Warm cache before demo.
9. Prefer server/Fresh 1C for production demo, not file DB over home internet.

## Git / VPS Update Workflow

Check if GitHub has new commits:

```bash
cd /opt/serverpal
git fetch
git status
git log --oneline HEAD..origin/main
```

Update VPS:

```bash
cd /opt/serverpal
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

GitHub HTTPS auth note:

- GitHub does not accept account password for Git operations.
- Use a Personal Access Token or SSH.
- At one point `git pull` succeeded over HTTPS after credentials/token were accepted.

If auth breaks again, recommended SSH setup:

```bash
ssh-keygen -t ed25519 -C "serverpal-vps"
cat ~/.ssh/id_ed25519.pub
```

Add public key to GitHub, then:

```bash
cd /opt/serverpal
git remote set-url origin git@github.com:theclaudman/Serverpal.git
ssh -T git@github.com
git pull
```

## Useful VPS Commands

Status:

```bash
cd /opt/serverpal
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 120 dashboard
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 120 ai-bridge
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 120 digest-api
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 120 nginx
```

Follow logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f dashboard
```

Resource usage:

```bash
docker stats
nproc
free -h
df -h
```

Restart production:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Rebuild production:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Stop production:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

Validate compose:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

## Useful Windows / Apache Commands

Find 1C publication:

```powershell
Select-String -Path "C:\Apache24\conf\*.conf","C:\Apache24\conf\extra\*.conf" -Pattern "Eu","1cv8","Alias" -CaseSensitive:$false
```

Test Apache config:

```powershell
C:\Apache24\bin\httpd.exe -t
```

Restart Apache:

```powershell
Restart-Service Apache2.4
```

Find Apache service:

```powershell
Get-Service *apache*
```

Show recent Apache access log:

```powershell
Get-Content C:\Apache24\logs\access.log -Tail 20
```

Check local IP:

```powershell
ipconfig
```

## OData Checks

From VPS, check publication:

```bash
curl -I https://client1.1rpanel.fun:8443/Eu
```

Check OData:

```bash
curl -I https://client1.1rpanel.fun:8443/Eu/odata/standard.odata/
```

Expected from VPS:

```text
401 Unauthorized
WWW-Authenticate: Basic realm="1C:Enterprise 8.3"
```

Check with credentials:

```bash
time curl -u 'LOGIN:PASSWORD' \
  'https://client1.1rpanel.fun:8443/Eu/odata/standard.odata/Catalog_Сотрудники?$format=json' \
  -o /dev/null
```

Use this to separate OData slowness from Dashboard slowness.

## Backup / Restore

Local scripts exist:

```bash
python scripts/backup.py
python scripts/restore.py backups/serverpal-backup-YYYYMMDD-HHMMSS.zip --yes
```

For VPS, prefer host-level backup of Docker volumes. Current volume names:

```text
serverpal_dashboard_data
serverpal_dashboard_logs
serverpal_ai_data
serverpal_ai_logs
serverpal_digest_data
serverpal_digest_logs
```

Check:

```bash
docker volume ls | grep serverpal
```

Do not include `.env` in routine backups by default. Store `.env` separately in a secure place.

Recommended retention:

- daily: 7 days;
- weekly: 4 weeks;
- monthly: 3 months.

Still needed:

- implement real VPS backup script/timer;
- perform restore drill on test directory or test VPS.

## Security Notes

Current good state:

- ServerPal main site uses HTTPS.
- AI Bridge and Digest API are internal-only in production.
- 1C test publication uses HTTPS on `8443`.
- Apache `/Eu` publication allows only VPS IP `194.147.215.155`.
- 1C endpoint returns `401` from VPS, indicating credentials are required.

Still important:

- Do not use 1C Administrator account for production.
- Use a separate low-privilege/read-only 1C user.
- Close external port 80 on the PC after certificate issuance unless renewal needs it.
- Rotate any 1C password that was sent over HTTP before TLS was configured.
- Keep `REGISTRATION_ENABLED=false` outside onboarding windows.
- Do not expose `9001`, `8001`, or `8002` publicly in production.

## Known Issues / Technical Debt

- Heavy pages are too slow on file 1C over internet.
- OData URL for at least one user may still be stored as old HTTP URL.
- No admin panel yet for registration toggle/user management.
- Dashboard templates use string replacement rather than Jinja2.
- Some comments/messages may show mojibake in PowerShell; only fix real file corruption visible in browser/logs/prompts.
- Digest context cache is in-memory.
- `knowledge_base.txt` is loaded broadly; eventually needs RAG/filtering.
- Backup policy is documented but not fully automated on VPS.
- Certificate renewal for Windows Apache needs a plan if port 80 remains closed.

## Recommended Next Steps

Immediate:

1. Update/create ServerPal user with correct 1C URL:

```text
https://client1.1rpanel.fun:8443/Eu
```

2. Confirm full login/registration flow with the HTTPS OData URL.
3. Close `REGISTRATION_ENABLED=false` after user creation.
4. Close PC external port 80 if not needed immediately.
5. Verify from non-VPS network that `client1.1rpanel.fun:8443/Eu/...` is forbidden.

Near-term engineering:

1. Add `/admin` panel with registration toggle and user management.
2. Add timing/size logging for every OData request.
3. Optimize `/price-list` first; it currently takes about 7.5 minutes.
4. Add cache warming for demo.
5. Add account/connection settings UI to edit saved 1C base URL without recreating user.
6. Add a safer first-admin bootstrap command/script.
7. Add VPS backup timer and restore drill.

Product/deployment:

1. Prepare client-facing docs for 1C access options:
   - 1C Fresh OData;
   - client web publication + HTTPS + IP allowlist;
   - WireGuard/VPN;
   - 1C Link only if OData works.
2. Prepare a “client server requirements” checklist.
3. Consider a larger VPS for production demos:
   - current: 1 CPU / 2 GB RAM;
   - recommended next: 2 CPU / 4 GB RAM / 30+ GB NVMe;
   - however, OData optimization is higher priority than VPS upgrade.

## Do Not Break

- Keep `/api/chat`, `/ws/chat`, and AI Bridge `/chat/ws` compatible.
- Keep POST fallback for chat.
- Keep Docker services reading environment variables without needing root `run_all.py` inside containers.
- Keep `SERVICE_API_KEY` enforcement on internal AI Bridge and Digest routes.
- Keep read-only validation before LLM-generated 1C queries.
- Keep registration closed by default.
- Keep local no-Docker workflow working.
- Keep production public ingress limited to Nginx `80/443`.
- Keep 1C publication protected by IP allowlist.

