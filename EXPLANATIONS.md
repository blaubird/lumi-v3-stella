Implemented appointment table and enum in migration with SQLite checks. Added Appointment model and exports. Created google calendar helper. Updated webhook with booking regex to store appointments and reply. Verified migrations and hypercorn startup.

## July 3 Hotfix
- **Root cause**: `FAQ` model wasn't imported in `api/ai.py`, causing a `NameError` during startup.
- **Fixes applied**:
  - Imported `FAQ` in `api/ai.py`.
  - Replaced stale imports from nonexistent `db` module with correct modules.
  - Converted stray `print` statements in `alembic_utils.py` to structured logging.
- **Other issues found**: updated internal docs and imports to avoid future unresolved-name errors.

yp1pcw-codex/fix-crash-related-to-pydantic-import

## July 4 Hotfix
- **Root cause**: Upgrading to pydantic 2 broke config loading since `BaseSettings` moved to `pydantic_settings`.
- **Fixes applied**: imported `BaseSettings` from the new package and added it to requirements. Adjusted f-string quoting in `main.py` and `webhook.py` to avoid syntax errors. Verified migrations and startup under Hypercorn.

## Multilingual & channel scaffold
- Added i18n templates with language detection and ICS generator
- Introduced Telegram/Instagram services and webhooks
- Added calendar wrapper and scheduled jobs for confirmations and reminders
- WhatsApp service now sends .ics attachments

## Crash fix July 3
- **Root cause**: migrating to Pydantic 2 removed `BaseSettings` from the main package.
- **Fixes applied**: switched imports to `pydantic-settings`, bumped FastAPI, added the new dependency, and corrected two f-string quotes.

 main

## Cleanup and typing hardening
- Removed committed bytecode and added `.gitignore` for caches and databases.
- Consolidated and pinned `requirements.txt` to ensure reproducible installs.
- Reworked logging to route everything through `logging_utils.get_logger`.
- Replaced root logger usage in `main.py`; added structured logging middleware.
- Introduced Outlook stub in `services/calendar.py` for future integration.
- Fixed lint warnings and unused imports via `ruff --fix` and formatted code with `black`.
- Resolved 63 pyright errors by casting SQLAlchemy columns, tightening config loading, and normalising message structures.
- Added extensive type hints and safe casts across jobs, routers and tasks.
- Attempted Hypercorn startup but it failed due to missing environment variables.

## Redis cache layer
- Added Redis dependency and REDIS_URL setting.
- Lifespan now opens a single async Redis client with graceful shutdown.
- Health endpoint checks Redis and reports degraded on failure.
- Introduced cache helpers for tenant config and FAQs with TTL and Prometheus hit/miss counters.
- Webhook message processing now retrieves tenant and FAQ data via Redis cache.

## Redis version bump
- Updated Redis dependency to 6.4.0 to track latest upstream fixes.

## Background task hardening
- Added missing FastAPI/SQLAlchemy imports in `deps.py` to restore admin auth guards.
- Ensured FAQ embedding tasks open their own sessions and always schedule when FAQ creation succeeds.
- Moved background embedding scheduling outside error paths and added defensive rollbacks/closures.

## Oct 8 2025 · RAG async pipeline
- Replaced the stubbed `get_rag_response` with an async RAG flow (pgvector retrieval, token-budgeted prompt, OpenAI retries, usage logging).
- Added pgvector retrieval helpers, token utilities, and fallback messaging covering disabled AI, empty context, and API failures.
- Extended `Usage` schema/migration for prompt/completion accounting and updated callers; added tiktoken dependency and config knobs for AI settings.

## Oct 12 2025 · Usage telemetry & tenant ID hardening
- Hardened the consolidated Alembic migration so it backfills missing usage token columns idempotently.
- Synced the ORM, admin schemas, and responses to expose `model` and token counters with nullable defaults.
- Standardised admin tenant identifiers as integer path params, coercing to string for persistence and keeping deprecated body tenant IDs compatible.

## Oct 19 2025 · Admin usage 500 fix
- **Root cause**: production usage table missed the new token/model columns so the admin usage query referenced non-existent fields.
- **Fixes**: guarded the consolidated migration to add/backfill the four columns idempotently, taught webhook writers to populate the token counters, and normalised the admin schema/serialiser so `model`, token tallies, and `trace_id` always appear.
- **Validation**: ran targeted Ruff/Black, verified Alembic upgrade logic for conditional column adds, and ensured responses coerce missing counters to zero for older rows.

## Oct 24 2025 · Tenant hard delete endpoint
- Added resolver that maps admin DELETE keys across id, slug, external_id, phone_id, and name, removing every matching tenant in one go.
- Wrapped cascading deletes for messages, FAQs, usage, and appointments inside a single SQLAlchemy transaction and logged outcomes.
- Added Redis eviction helper that scans `tenant:{id}:*` keys in batches, tolerating connectivity faults without aborting the purge.

## Oct 30 2025 · Tenant ID normalisation & usage telemetry fix
- Normalised admin + RAG tenant identifiers to canonical strings via a shared utility so both numeric and legacy IDs resolve consistently.
- Updated schemas, routers, and OpenAPI examples to surface tenant IDs as strings while still accepting integer inputs without 422 regressions.
- Hardened usage queries/serialisers after adding idempotent migration guards so the admin usage endpoint returns token/model data without 500s.

## Nov 3 2025 · Usage schema alignment & smoke runner
- Added Alembic revision `002_usage_alignment` that creates or amends `usage` to match ORM expectations (VARCHAR direction, nullable token counts, msg timestamp default, token column defaults) and seeds composite indexes for tenant lookups.
- Synced `Usage` ORM + admin response schema with the widened types/defaults to guarantee serialisation without 500s once the migration runs.
- Introduced `api/scripts/smoke_runner.sh` to hit health, tenant CRUD, and usage endpoints against a remote deployment with a PASS/FAIL summary for quick regression checks.

## Nov 13 2025 · Canonical + repair migrations
- Rebuilt `001` as a deterministic, schema-qualified bootstrap: creates enums, pgvector, and every table/index in `public` with the production `usage` shape from the outset.
- Reworked `002` into an idempotent fixer that adds/widens `usage` columns, cascades FK/index repairs, and leaves the canonical layout untouched on downgrades.
- Locked Alembic's runtime to the `public` schema (search_path + version table) to keep revisions and repair logic deterministic across environments.

## Nov 20 2025 · Usage repair consolidation
- Folded the standalone trace-ID migration into `002_usage_alignment`, deleting revision `003` while keeping upgrade paths idempotent for partially patched databases.
- Hardened the repair migration: guards every column add/widen (including `trace_id`), enforces token defaults with NULL backfill, preserves enum directions, and recreates the tenant usage indexes only when absent.
- Synced the ORM defaults with `server_default=text("0")` and refreshed docs/notes so operators just run `alembic upgrade head` to land the consolidated fix.

## Nov 24 2025 · Trace-ID column marker
- Added an inspector guard so the consolidated repair migration creates `public.usage.trace_id` when missing and annotates it with a reversible marker.
- Downgrade now inspects that marker before dropping the column, avoiding accidental deletion when environments already had `trace_id` pre-migration.

## Nov 25 2025 · Trace-ID VARCHAR enforcement
- Ensured the repair migration always materialises `trace_id` as `VARCHAR(255)` by widening existing `TEXT` columns and adding the field with the explicit type when missing.
- Guarded the widening logic against `NULL` length metadata so idempotent reruns don't raise when inspecting legacy column definitions.

## Dec 5 2025 · Redis cache & invalidation overhaul
- Wrapped Redis access in `redis_client.RedisWrapper` with lifespan-aware init/close, latency tracking, and quiet degradation when misconfigured.
- Introduced read-through cache helpers for tenant config/FAQs with namespaced keys, JSON storage, and hashed-key debug logging gated by `REDIS_METRICS`.
- Extended FastAPI lifespan to publish wrapper state, surface latency on `/healthz`, and added smoke script + README guidance for Redis deployments.
- Hooked SQLAlchemy sessions to enqueue namespace invalidation (SCAN + UNLINK) after commits and reused the helper in admin flows.

## Dec 12 2025 · Async RAG pipeline hardening
- Rebuilt `get_rag_response` to call a dedicated pgvector retrieval helper, enforce token budgets with `tiktoken`, and stream retries via `tenacity` with telemetry + Redis trace breadcrumbs.
- Added `api/retrieval.py` for embedding generation + cosine search, wired routers to pass Redis handles, and persisted usage records on both success and failure paths.
- Delivered an async CLI to backfill FAQ embeddings in batches so operations can heal legacy data purely through environment configuration.

## Dec 15 2025 · Vacation wizard migration follow-up
- Restored `001_initial_schema` to its canonical bootstrap so fresh databases stay deterministic.
- Added Alembic revision `003_vacation_wizard` that idempotently creates owner contact and unavailability tables plus indexes.
- Confirmed pytest vacation wizard suite passes against the new migration chain.

## Dec 16 2025 · Vacation wizard chain repair
- Verified the accidental edits were rolled back from `001_initial_schema`, keeping only the canonical bootstrap DDL.
- Hardened `003_vacation_wizard` so it alone provisions vacation-wizard tables, indexes, and exclusion constraint with inspector-based guards.
- Documented downgrade protections that drop objects only when present, keeping re-runs and partially applied upgrades safe.
