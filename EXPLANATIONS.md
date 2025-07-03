Implemented appointment table and enum in migration with SQLite checks. Added Appointment model and exports. Created google calendar helper. Updated webhook with booking regex to store appointments and reply. Verified migrations and hypercorn startup.

## July 3 Hotfix
- **Root cause**: `FAQ` model wasn't imported in `api/ai.py`, causing a `NameError` during startup.
- **Fixes applied**:
  - Imported `FAQ` in `api/ai.py`.
  - Replaced stale imports from nonexistent `db` module with correct modules.
  - Converted stray `print` statements in `alembic_utils.py` to structured logging.
- **Other issues found**: updated internal docs and imports to avoid future unresolved-name errors.

## Additional Fix
- **Root cause**: `admin.py` imported `get_db` from `database`, which doesn't expose that helper, causing an ImportError on startup.
- **Fixes applied**:
  - Updated `admin.py` to import `get_db` from `deps`.
