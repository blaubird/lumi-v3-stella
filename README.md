# Lumi v3 Stella

This repository contains the FastAPI backend for Lumi's multi-channel assistant. It exposes webhook handlers, admin tooling, and retrieval-augmented generation (RAG) endpoints backed by PostgreSQL and Redis.

## Owner How-To

Owners can now schedule vacation blocks directly in chat—no admin panel or API calls required. The assistant mirrors the language of the incoming message at every step, so **write in your own language and Lumi will answer in that language**.

Steps:

1. Send a single-word "Vacation" trigger (e.g. `Vacances`, `Vacation`, `Отпуск`, `Urlaub`).
2. Reply with the start date when prompted.
3. Reply with the end date.
4. Confirm with ✅ to save or ❌ to cancel.

Example conversation (French):

```
👤 Vacances
🤖 Quelle est la date de début de vos congés ?
👤 24/12/2024
🤖 Parfait. Et quand se termine-t-il ?
👤 08/01/2025
🤖 Merci de confirmer : du 2024-12-24 au 2025-01-08 (✅ pour enregistrer, ❌ pour annuler).
👤 ✅
🤖 Enregistré ! Profitez de vos congés.
```

## Redis configuration

Provide Redis connectivity through environment variables. `REDIS_URL` is optional at startup—when omitted the API falls back to database reads without caching.

Example connection strings:

- `redis://default:PASS@host:port/0`
- `rediss://default:PASS@host:port/0?ssl_cert_reqs=none`

Optional knobs:

- `REDIS_DB`: overrides the logical database when the URL omits it.
- `REDIS_PREFIX`: namespace prefix for cache keys (default `lumi`).
- `REDIS_CONNECT_TIMEOUT_MS`, `REDIS_HEALTHCHECK_SECONDS`: tune connection behaviour.
- `CACHE_TTL_CONFIG_SEC`, `CACHE_TTL_FAQS_SEC`: tenant config/FAQ cache TTL in seconds.
- `REDIS_METRICS`: enable detailed cache hit/miss logging.

Use `scripts/smoke_redis.sh http://localhost:8000` to verify `/healthz` reports Redis as healthy after deployment.

### 🐳 Local Docker run
```bash
docker compose up --build api       # first build caches deps layer
docker compose up api               # subsequent runs are fast
```
The multi-stage Dockerfile installs Python deps once (layer cache) and copies source separately, so code-only edits rebuild in seconds.

## Dev baseline reset

- The shared dev database was reset and now boots from the squashed Alembic baseline `001_initial_squashed`.
- To recreate the schema locally, export `DATABASE_URL` with the dev connection string and run `alembic -c api/alembic.ini upgrade head`.
- For any future schema change, add a brand-new Alembic revision—never edit or replace `001_initial_squashed`.

## Database migrations

- Alembic lives under `api/alembic/` with the entry configuration at `api/alembic.ini` and migrations in `api/alembic/versions/`.
- `DATABASE_URL` must point to PostgreSQL (e.g. `postgresql://...`). Alembic and the app will fail fast if the URL is missing or uses another dialect.
- Run migrations locally with:

  ```bash
  export DATABASE_URL=postgresql://...  # Postgres only
  alembic -c api/alembic.ini upgrade head
  ```

- Railway one-off deploys can apply migrations via:

  ```bash
  railway run --service api "alembic -c api/alembic.ini upgrade head"
  ```

- The API no longer runs Alembic automatically. Set `RUN_MIGRATIONS_ON_STARTUP` to `1`, `true`, or `yes` to opt-in to running `alembic upgrade head` on startup; omit the variable or set it to `0`, `false`, or `no` to skip (default is `false`).
- CI keeps the dev database up to date through `.github/workflows/migrate-dev.yml`, which validates `secrets.DEV_DATABASE_URL` and runs `alembic -c api/alembic.ini upgrade head` on every push to `dev` or manual dispatch.
