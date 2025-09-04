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
