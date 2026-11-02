# Staging Deployment Readiness Audit

Date: 2026-11-02. Environment used for verification: Windows 11 + Docker Desktop (Docker 29.8.2),
Python 3.13 (venv), Node 24 / npm 11. Images target Linux (python:3.12-slim, node:22-alpine, caddy:2-alpine, postgres:16-alpine).

**Decision: CONDITIONAL GO: not fully verified.** No unresolved critical security or data-loss risk was
found, images build, migrations and persistence were verified on real PostgreSQL in Docker. Three checks
could not be run here (see "NOT VERIFIED") and must be done on the VPS in the first deployment.
**Readiness score: 8 / 10.**

## Changes

| Area | Change |
|---|---|
| Secrets | `JWT_SECRET` has no default; <32 chars or placeholder values abort startup. `.env.staging*` git-ignored; compose uses `${VAR:?}` for required values. |
| CORS | Removed the permissive localhost/192.168.x regex; only `CORS_ORIGINS` (set to `https://$SITE_ADDRESS` in staging); explicit methods/headers. |
| Abuse limits | slowapi: `10/minute` per client IP on login and register (`AUTH_RATE_LIMIT`); Caddy caps `/api` bodies at 1 MB; schema caps chat messages at 12,000 chars. |
| Startup | `create_all` now opt-in (`AUTO_CREATE_SCHEMA`, default false); Alembic owns schema. |
| Health | `/api/health/live` (no deps), `/api/health/ready` (DB reachable + migrated; 503 otherwise; no connection details). Existing `/api/health` unchanged. |
| Bug fix | `PATCH /api/memory/{id}` failed with a lazy-load error after commit (server-side `updated_at`); fixed with `refresh`. Found by new tests. |
| Frontend | API base is same-origin `/api` (`src/services/api.ts`, `VITE_API_URL` override); Vite dev proxy for `/api`; removed `hostname:8000`. |
| Containers | Multi-stage backend image (non-root uid 10001, read-only rootfs, caps dropped, healthchecks); Caddy image with Vite build; private `internal` network for PostgreSQL; named volumes `postgres_data`, `caddy_data`, `caddy_config`; `restart: unless-stopped`; log rotation. |
| DB | Alembic baseline `0001` (generated from models, verified equivalent); `scripts/migrate.py` safe baseline/stamp logic; baseline downgrade refuses to run; backup / restore-to-new-DB scripts. |
| Dev compose | Postgres bound to 127.0.0.1; backend gets `AUTO_CREATE_SCHEMA=true`; Vite proxy target set. |
| Requirements | pytest/aiosqlite moved to `requirements-dev.txt`; `alembic` added to runtime. |

No indexes/constraints were added: every filtered/joined column (`owner_id`, `conversation_id`, `user_id`, `status`, FK sources, unique `email`) is already indexed.

## Verification results

### Tests
| Suite | Result |
|---|---|
| Backend, with disposable PostgreSQL (`TEST_POSTGRES_URL`) | **72 passed, 0 failed, 0 skipped** (32 pre-existing + 40 new) |
| Backend, without PostgreSQL | 70 passed, 0 failed, **2 skipped** (the PostgreSQL migration tests) |
| Frontend (vitest/jsdom) | **7 passed**, 0 failed (API routing, locale parity, login validation/server error/unreachable backend/token storage) |
| `tsc -b` | passed |
| `vite build` | passed (no `:8000` in bundle) |

New backend coverage: registration/login, duplicate/case-insensitive email, argon2 hashing, invalid input,
missing/malformed/expired/forged/`alg=none`/unknown-user tokens, rate limiting, weak-secret refusal, CORS,
conversation CRUD, cross-user isolation (conversations, messages, memory), chat persistence, SSE streaming,
provider error → 502 / in-band stream error with the user turn rolled back, edit/regenerate, memory API,
liveness/readiness (incl. no credential leakage), Alembic baseline == models, downgrade refusal,
migrate.py on empty / legacy-with-data / drifted schemas. Existing tests cover OpenRouter payload, timeouts, 400 handling and memory service.
AI calls are mocked; no real OpenRouter calls were made.

### Migrations (PostgreSQL 16 in Docker)
- Empty DB → baseline applied (also inside the staging `migrate` container): **PASS**
- Legacy `create_all` DB with rows → equivalence verified, stamped `0001`, rows intact (1 user, 1 conversation, 1 message): **PASS**
- Re-run is idempotent: **PASS**
- Drifted schema (column dropped) → aborts with exit 2, nothing changed, data intact: **PASS**
- Backup before migrate triggers automatically when data exists: **PASS**

### Docker / HTTPS (isolated project `sapsdk-itest`, ports 18080/18443)
- `docker compose config` valid; fails closed when required vars are missing: **PASS**
- Both images built; Caddyfile validated at build time: **PASS**
- Order: postgres healthy → migrate exit 0 → backend healthy → web healthy: **PASS**
- `/` and deep link `/some/deep/route` → 200 `text/html`; `/api/*` → FastAPI JSON; `/docs` not exposed: **PASS**
- HTTPS (TLS 1.3, Caddy local CA), HTTP → 308 redirect to HTTPS, HSTS/nosniff/frame/referrer headers: **PASS**
- SSE through Caddy (`text/event-stream`, tokens, `[DONE]`): **PASS** (greeting path; no model key)
- Register → login → authenticated conversation create/list → 401 without token: **PASS**
- 2 MB body → 413; 15 rapid bad logins → 429 after the limit: **PASS**
- Published ports: only `web` (80/443). `postgres` and `backend` show no host mapping; host connections to 5432/8000 refused; `private` network `internal=true`: **PASS**
- Backend runs as uid 10001, root filesystem read-only: **PASS**
- Data survives full stop/start (user, login, conversations, migrate re-run no-op): **PASS**
- Backup → restore into a new DB; row counts identical to live; restore refuses live/existing DB name: **PASS**
- Secrets: JWT secret and DB password not present in image metadata/history, image filesystems, container logs, or the frontend bundle: **PASS**

## NOT VERIFIED
1. **Real Let's Encrypt issuance** on the real domain/VPS (only Caddy's internal CA on `localhost` was tested). Needs DNS pointing at the VPS and ports 80/443 reachable.
2. **Real OpenRouter calls** (no key available here; provider behaviour verified with mocks and existing unit tests). Smoke-test one real chat after deploy.
3. **Ubuntu host specifics**: verified on Docker Desktop (Linux containers). Bash scripts were run under Git Bash; `.gitattributes` forces LF.
4. Persistence when the postgres *container is recreated* (only stop/start was run, container removal was not performed in this session); named volume semantics make this expected to work. Restore **cut-over** (switching `POSTGRES_DB`) is documented but was not executed.

## Residual risks (non-blocking for staging)
- Registration is open to anyone who can reach the site. Restrict by firewall/basic-auth or add an invite flow if staging is public.
- JWT lives in `localStorage`, 12 h expiry, no revocation/refresh (pre-existing design).
- Rate-limit state is in-process memory (correct for the single uvicorn worker used here; not shared across replicas).
- No Content-Security-Policy header (app uses inline styles/mermaid; adding CSP needs browser testing).
- `frontend/package.json` uses `latest` ranges; builds are reproducible only through `package-lock.json` (`npm ci`). `npm audit` reports advisories that were not triaged.
- Caddy runs as root inside its container (needed for 80/443 with default image) with all capabilities dropped except `NET_BIND_SERVICE`.
- Backups are local to the VPS until copied off-host.
