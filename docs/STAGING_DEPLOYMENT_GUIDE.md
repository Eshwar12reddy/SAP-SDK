# Staging Deployment Guide (Ubuntu VPS)

Stack: Caddy (HTTPS, static React build, reverse proxy) → FastAPI → PostgreSQL, all via Docker Compose
(`docker-compose.staging.yml`). Only ports 80/443 are published. PostgreSQL and FastAPI are reachable
only on private Docker networks.

## 0. Prerequisites

- Ubuntu 22.04/24.04 VPS, a DNS **A/AAAA record** for your staging hostname pointing at it
  (Let's Encrypt cannot issue certificates for a bare IP).
- OpenRouter API key.

## 1. Server setup

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git ufw openssl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker
docker --version && docker compose version

# Firewall: SSH + web only (Docker bypasses ufw for published ports, so we only publish 80/443 anyway)
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp
sudo ufw --force enable
```

## 2. Get the code and configure

```bash
git clone <your-repo-url> sap-sdk && cd sap-sdk
cp .env.staging.example .env.staging && chmod 600 .env.staging

# Generate secrets (hex = URL-safe, required for the DB password because it is embedded in DATABASE_URL)
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env.staging
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(openssl rand -hex 32)|" .env.staging
nano .env.staging          # set SITE_ADDRESS and OPENROUTER_API_KEY
```

Compose refuses to start if `SITE_ADDRESS`, `POSTGRES_*` or `JWT_SECRET` are missing, and the API
refuses to start with a JWT secret shorter than 32 characters. Never commit `.env.staging`.

## 3. Build, migrate, start

```bash
export DC="docker compose --env-file .env.staging -f docker-compose.staging.yml"
$DC config -q && echo "compose OK"
$DC build

# First deploy (empty DB) OR upgrade of an existing DB. Backs up automatically if data exists.
./scripts/migrate_staging.sh

$DC up -d
$DC ps
```

`migrate` also runs automatically as a one-shot service before `backend` on every `up`
(idempotent). The app never creates tables itself in staging (`AUTO_CREATE_SCHEMA=false`).

### Migrating a database that predates Alembic
`scripts/migrate.py` detects tables without `alembic_version`, compares the live schema with the
baseline, and **stamps** revision `0001` only if they are identical (no DDL executed). If they differ
it exits with code 2, prints the differences and changes nothing; do not force it, report it.

## 4. Verify

```bash
SITE=$(grep ^SITE_ADDRESS .env.staging | cut -d= -f2)
curl -s https://$SITE/api/health/live            # {"status":"ok"}
curl -s https://$SITE/api/health/ready           # database + migrations
curl -sI https://$SITE/ | head -1                # HTTP/2 200
curl -sI https://$SITE/some/deep/link | head -1  # 200 (SPA fallback)
$DC ps                                           # all (healthy); migrate "Exited (0)"
ss -tlnp | grep -E ':(5432|8000)\b' || echo "5432/8000 not published (good)"
```

Then open `https://<SITE>` and register, sign in, and send a chat message.

## 5. Logs

```bash
$DC logs -f --tail=100 backend
$DC logs --tail=100 web        # Caddy: certificate issuance, access log (Authorization/Cookie removed)
$DC logs migrate
$DC logs postgres
```
Logs rotate automatically (10 MB × 5 per container).

## 6. Backup and restore

```bash
./scripts/db_backup.sh                     # -> backups/<db>_<UTC timestamp>.dump (verified, chmod 600)
# schedule nightly:  0 2 * * * cd /home/ubuntu/sap-sdk && ./scripts/db_backup.sh >> backups/backup.log 2>&1
```

Restore **never overwrites the live database**. It creates a new database and loads the dump into it:

```bash
./scripts/db_restore.sh backups/<file>.dump              # -> <db>_restore_<timestamp>
./scripts/db_restore.sh backups/<file>.dump sapsdk_rec1  # or choose the name
```

To cut the application over to a restored copy (after inspecting it):

```bash
$DC stop backend web
sed -i 's|^POSTGRES_DB=.*|POSTGRES_DB=sapsdk_rec1|' .env.staging   # DATABASE_URL is derived from this
$DC up -d
```
The previous database stays untouched in the volume, so you can switch back the same way. Copy
`backups/` off the server regularly (`scp`/`rclone`); a backup on the same disk is not disaster recovery.

## 7. Updating / rollback

```bash
git pull
./scripts/migrate_staging.sh      # backs up first, then migrates
$DC up -d --build
```

Rollback of code (migrations are additive; the baseline migration deliberately refuses to downgrade):

```bash
git log --oneline -5
git checkout <previous-good-commit>
$DC up -d --build
```
If a later migration was applied and the old code is incompatible, restore the pre-migration backup
into a new database and cut over (section 6) rather than downgrading in place.

## 8. Operations

```bash
$DC restart backend                       # restart one service
$DC stop && $DC up -d                     # full restart (data persists in the postgres_data volume)
docker volume ls | grep sapsdk-staging    # postgres_data, caddy_data (certificates), caddy_config
```
**Do not** run `docker compose down -v`, `docker volume rm`, or `DROP DATABASE` on staging; they
destroy user data or certificates.

## 9. Local development (unchanged workflow)

`docker-compose.yml` (dev) and `npm run dev` still work. Set `JWT_SECRET` (≥32 chars) and
`AUTO_CREATE_SCHEMA=true` in `.env`. The Vite dev server proxies `/api` to `http://localhost:8000`
(`VITE_DEV_API_TARGET` overrides it).

## 10. Test commands

```bash
# Backend (from backend/)
python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
pytest -q
TEST_POSTGRES_URL=postgresql://user:pw@127.0.0.1:5432/disposable pytest -q   # also runs migration tests; DROPS the public schema of that DB, use a throwaway one

# Frontend (from frontend/)
npm ci && npm run build && npm test
```
