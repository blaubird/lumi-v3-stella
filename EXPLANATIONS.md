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
