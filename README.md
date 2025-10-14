# Lumi v3 Stella

This repository contains the FastAPI backend for Lumi's multi-channel assistant. It exposes webhook handlers, admin tooling, and retrieval-augmented generation (RAG) endpoints backed by PostgreSQL and Redis.

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
