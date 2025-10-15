# Project lumi-v3-stella: A Guide for AI Agents

**Version:** 2.0
**Last Updated:** October 15, 2025

## 1. Mission Statement

Our primary objective is to ship high-quality, production-ready code for the `lumi-v3-stella` backend. This involves not only implementing new features but also preserving the existing architecture and ensuring the stability and performance of the application. Key upcoming features to anticipate include integrations with Telegram, Instagram, and a calendar service.

### Core Directives:

*   **Zero Runtime Errors:** All code must be robust and handle exceptions gracefully.
*   **No Interface Regressions:** Changes should not break existing API contracts or functionality.
*   **Clean and Coherent Diffs:** Commits should be atomic, well-documented, and easy to review.

## 2. Reference Architecture

The project follows a modular architecture that must be maintained. All new code should be placed in the appropriate directory to ensure consistency and prevent circular dependencies.

```bash
api/
 ├─ main.py           # FastAPI entry point, environment validation, Alembic migrations, and scheduler setup
 ├─ models.py         # SQLAlchemy ORM models (e.g., Tenant, Message, Appointment)
 ├─ routers/          # API routers for different resources (e.g., webhook.py, admin.py)
 ├─ services/         # Business logic and integrations with external services (e.g., WhatsApp, Google Calendar)
 ├─ utils/            # Utility functions and helpers (e.g., logging, internationalization)
 ├─ jobs/             # Asynchronous background jobs (e.g., sending reminders)
 └─ tasks.py          # Celery/async task definitions
alembic/
 └─ versions/         # Alembic migration scripts (e.g., 001_initial_schema.py)
site/                  # Frontend application code (no backend code here)
```

### Upcoming Modules:

*   `services/telegram.py`
*   `services/instagram.py`
*   `services/calendar.py`

## 3. Workflow Checklist

To ensure code quality and consistency, every contribution must follow this workflow:

| Step | Action                                                                 |
| :--- | :--------------------------------------------------------------------- |
| 1    | Pull the latest `main` branch. Your local branch must be up-to-date.     |
| 2    | Run `ruff --fix .` and `black .` to format the code.                     |
| 3    | Perform static type checking with `pyright`. Ensure no `NameError` or `Any` types. |
| 4    | Verify Alembic migrations: `alembic upgrade head` and `alembic downgrade -1` must pass without errors. |
| 5    | Launch the application locally (e.g., `hypercorn main:app -k asyncio`). Ensure no tracebacks on startup. |
| 6    | Smoke-test the critical API routes that have been modified.              |
| 7    | Commit the full files, keeping the diff minimal and focused.             |
| 8    | Update `requirements.txt` and environment variable documentation when adding new libraries. |
| 9    | Document the reasoning for your changes in `EXPLANATIONS.md` (max 200 words). |

## 4. Coding Standards

*   **Imports:** All imports must be sorted using `ruff-isort`.
*   **Type Hinting:** Type hints are mandatory for all functions and variables, except for trivial lambdas.
*   **Constants:** All constants should be defined in `api/constants.py` to avoid magic strings.
*   **Logging:** Use the `logging_utils.get_logger()` utility for all logging. Do not use `print()`.
*   **Database Enums:** When updating a database enum, you must update both the Alembic migration and the SQLAlchemy ORM model.
*   **External Calls:** All external API calls must be wrapped with `tenacity` for retries, using an exponential back-off strategy (e.g., 0.5s to 8s).
*   **Background Jobs:** Each background job should run in its own database session and must always commit or roll back the session.

## 5. Alembic Migration Policy

The previous policy of maintaining a single migration file has been identified as the root cause of persistent and critical migration failures. This policy is now deprecated and must not be followed.

### New Migration Policy:

*   **Create New Migration Files for Every Change:** For any and all schema modifications, a new Alembic migration file must be generated using the `alembic revision -m "<description>"` command. **Do not, under any circumstances, modify existing migration files.**
*   **Write Idempotent Migrations:** All `upgrade` and `downgrade` functions should be written to be idempotent (i.e., they can be run multiple times without causing errors). Use `inspector.has_table()` and similar checks to ensure that operations are only performed if necessary.
*   **Maintain a Clean Migration Chain:** The migration history must be a clean, linear sequence of changes. Each migration file should represent a single, atomic change to the database schema.

## 6. Guardrails for Consistency

| Problem Class             | Guard                                                                 |
| :------------------------ | :-------------------------------------------------------------------- |
| Undefined Symbol          | Static type checking with `pyright` (Workflow Step #3).               |
| Enum Mismatch             | Synchronize the Alembic enum with the ORM `Enum`.                     |
| Missing Credentials       | Raise a clear `RuntimeError` if a required environment variable is missing. |
| Timezone Drift            | Store all timestamps as `TIMESTAMPTZ` and only convert on output.      |
| Spaghetti Code            | Place new code in the correct folder as per the architecture. No circular imports. |

## 7. Performance & Observability

*   **API Latency:** The target for API latency is < 200 ms at the 95th percentile (p95).
*   **Database Queries:** Ensure that appropriate indexes are in place before adding queries that use `ILIKE` or other potentially slow operations.
*   **Monitoring:** When adding new routers, expose relevant counters via `monitoring.py` using the `PROMETHEUS_PORT` environment variable.

## 8. Upcoming Feature Awareness

When implementing new features, be mindful of the upcoming integrations:

*   **Telegram:** `services/telegram.py`, `/telegram_webhook` router.
*   **Instagram:** `services/instagram.py`, `/instagram_webhook` router.
*   **Calendar:** `services/calendar.py`, re-using the `Appointment.google_event_id` field.

Avoid hard-coding channel-specific logic in the core application. Instead, use a façade like `send_text(channel, ...)` to abstract the communication channels.

## 9. Commit Etiquette

*   **Commit Messages:** Prefix all commit messages with `[Fix]`, `[Feat]`, `[Refactor]`, or `[Docs]`.
*   **Branch Protection:** If branch protection rules block a merge, request a review. Do not push directly to `main`.

## 10. Fallback Language

*   The main client-facing language is French, BUT bot has to respond using the language of the clients, any available for ChatGPT language
*   Use the `utils/i18n.py::tr()` function to localize all user-facing replies. If a translation is not present, add it.

