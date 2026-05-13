# ServerPal Deployment

This document describes local development, VPS deployment with Docker Compose, Nginx/HTTPS, backups, and 1C connectivity options.

## Local Development

Use one root virtual environment for all three local services:

```powershell
cd "C:\Users\klodc\Desktop\Serverpal — копия"
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements-all.txt
copy .env.example .env
python run_all.py
```

Local ports:

- Dashboard: `http://127.0.0.1:9001`
- AI Bridge: `http://127.0.0.1:8001`
- Digest API: `http://127.0.0.1:8002`

For local development, keep:

```env
AI_SERVICE_URL=http://127.0.0.1:8001
DIGEST_SERVICE_URL=http://127.0.0.1:8002
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
REGISTRATION_ENABLED=false
```

## VPS Architecture

Production uses Docker Compose with an override file:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Only Nginx is public:

```text
Internet -> Nginx :80/:443 -> dashboard:9001
dashboard -> ai-bridge:8001
dashboard -> digest-api:8002
dashboard/digest-api -> client 1C OData URL
```

Do not publish AI Bridge or Digest API directly to the internet. They are internal service APIs and are protected by `SERVICE_API_KEY`, but they do not need public ingress.

## VPS Prerequisites

- Ubuntu 22.04/24.04 or similar Linux VPS.
- Docker Engine and Docker Compose plugin.
- Domain A-record pointed to the VPS public IP.
- Open firewall ports: `80/tcp`, `443/tcp`.
- Outbound HTTP/HTTPS from the VPS to customer 1C OData endpoints.

## Production `.env`

Create `.env` from `.env.example` and set production values:

```env
SERVERPAL_DOMAIN=serverpal.example.com
SERVERPAL_TLS_CERT_PATH=/etc/letsencrypt/live/serverpal.example.com/fullchain.pem
SERVERPAL_TLS_KEY_PATH=/etc/letsencrypt/live/serverpal.example.com/privkey.pem

SECRET_KEY=<long-random-string>
ENCRYPTION_KEY=<valid-fernet-key>
SERVICE_API_KEY=<long-random-service-key>

AI_SERVICE_URL=http://ai-bridge:8001
DIGEST_SERVICE_URL=http://digest-api:8002
ALLOWED_ORIGINS=https://serverpal.example.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
REGISTRATION_ENABLED=false

OPENAI_API_KEY=<ai-bridge-key-or-compatible-key>
OPENAI_BASE_URL=<openai-compatible-url>
OPENAI_MODEL=<model-name>

DIGEST_OPENAI_API_KEY=<digest-provider-key>
DIGEST_OPENAI_BASE_URL=https://api.hydraai.ru/v1
DIGEST_OPENAI_MODEL=gpt-4o
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
LMSTUDIO_MODEL=<local-model-name>
```

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Validate production settings before deploy:

```bash
python scripts/prod_check.py --prod
```

## HTTPS and Nginx

The production override mounts host TLS files into the Nginx container. The recommended setup is host-level Certbot:

```bash
sudo apt-get update
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d serverpal.example.com
```

Then set:

```env
SERVERPAL_TLS_CERT_PATH=/etc/letsencrypt/live/serverpal.example.com/fullchain.pem
SERVERPAL_TLS_KEY_PATH=/etc/letsencrypt/live/serverpal.example.com/privkey.pem
```

Nginx config is in `deploy/nginx/templates/serverpal.conf.template`. It redirects HTTP to HTTPS, proxies Dashboard, and includes WebSocket headers for `/ws/chat`.

After certificate renewal, reload Nginx:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload
```

## Volumes

Runtime state is stored in Docker volumes:

- `dashboard_data`: Dashboard SQLite DB at `/data/users.db`.
- `dashboard_logs`: Dashboard logs.
- `ai_data`: AI Bridge connected-base data.
- `ai_logs`: AI Bridge logs.
- `digest_data`: Digest generated data/runs/context.
- `digest_logs`: Digest logs.

Keep these volumes across deploys. Do not run `docker compose down -v` on production unless you intentionally want to delete data.

## Backup and Restore

Use host-level backups for VPS volumes. Do not rely only on local zip scripts for production.

Recommended retention:

- daily backups: 7 days;
- weekly backups: 4 weeks;
- monthly backups: 3 months.

Do not include `.env` in routine backups by default. Store `.env` separately in a protected password manager or encrypted vault.

Example host backup script:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=/opt/serverpal
BACKUP_DIR=/var/backups/serverpal
STAMP=$(date +%Y%m%d-%H%M%S)
ARCHIVE="$BACKUP_DIR/serverpal-$STAMP.tar.gz"

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"

docker compose -f docker-compose.yml -f docker-compose.prod.yml stop dashboard ai-bridge digest-api
tar -czf "$ARCHIVE" \
  /var/lib/docker/volumes/serverpal_dashboard_data/_data \
  /var/lib/docker/volumes/serverpal_dashboard_logs/_data \
  /var/lib/docker/volumes/serverpal_ai_data/_data \
  /var/lib/docker/volumes/serverpal_ai_logs/_data \
  /var/lib/docker/volumes/serverpal_digest_data/_data \
  /var/lib/docker/volumes/serverpal_digest_logs/_data
docker compose -f docker-compose.yml -f docker-compose.prod.yml start dashboard ai-bridge digest-api

find "$BACKUP_DIR" -name "serverpal-*.tar.gz" -mtime +90 -delete
```

Adjust volume names after checking:

```bash
docker volume ls | grep serverpal
```

Restore drill:

1. Stop production services.
2. Restore archive into matching Docker volume `_data` directories or onto a test VPS.
3. Start services.
4. Verify login, prompts, account settings, chat, digest, and reports.

Run at least one restore drill before relying on the backup policy.

## 1C Connectivity Options

ServerPal needs an OData HTTP endpoint reachable from the VPS backend containers.

Preferred order:

1. **1C Fresh OData**: best option when the customer database is in Fresh and provides OData URL plus user/password.
2. **1C Link**: use only after manually checking that the exact OData path is reachable through the link domain:
   `https://<name>.link.1c.ru/<base>/odata/standard.odata/`
3. **VPN/Tailscale/WireGuard**: recommended for local customer databases without public exposure.
4. **White IP + port forwarding**: use only with HTTPS, IP allowlist for the VPS IP, and a read-only 1C user.

Browser access to Dashboard does not need direct access to 1C. OData requests are server-side outbound requests from the VPS.

## Deployment Checklist

Before first production launch:

```bash
python scripts/prod_check.py --prod
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Verify:

- `https://<domain>/health` returns Dashboard health.
- Registration is disabled unless intentionally enabled.
- Login works with a configured 1C account.
- `/ws/chat` works through the browser.
- `/api/digest/providers` reports the intended provider as available.
- Digest works with external provider.
- OData URL is reachable from the VPS.
- Public internet cannot reach ports `8001` and `8002`.
- Services restart after `docker compose restart`.
- Services start after VPS reboot.

## Updates

```bash
cd /opt/serverpal
git pull
python scripts/prod_check.py --prod
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

