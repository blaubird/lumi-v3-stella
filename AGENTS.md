1 · Mission Statement
Ship production-ready code for the lumi-v3-stella backend while preserving existing architecture and anticipating upcoming features (Telegram, Instagram, calendar).
– No runtime errors.
– No interface regressions.
– Clean, coherent diffs only.

2 · Reference Architecture (must stay intact)
bash
Copy
Edit
api/
 ├─ main.py           # FastAPI entry, env validation, migrations, scheduler
 ├─ models.py         # ORM: Tenant, Message, FAQ, Usage, Appointment, …
 ├─ routers/          # webhook.py, admin.py, rag.py (per resource)
 ├─ services/         # whatsapp.py (+future telegram.py, instagram.py, calendar.py)
 ├─ utils/            # helpers (logging, i18n, ics_generator, …)
 ├─ jobs/             # background jobs (confirm_pending, send_reminders, …)
 └─ tasks.py          # Celery/async tasks
alembic/               # 001_initial_schema.py ONLY
site/                  # frontend (no backend code here)
Upcoming modules (placeholders exist in Upcoming Features.md):
services/telegram.py, services/instagram.py, services/calendar.py.

3 · Workflow Checklist (must follow)
#	Action
1	Pull latest main. Fail if local branch is behind.
2	Run ruff --fix + black ..
3	Type-check: pyright (no NameError, no Any).
4	alembic upgrade head && alembic downgrade -1 must pass.
5	Launch with hypercorn main:app -k asyncio … — no tracebacks.
6	Smoke-test critical route(s) changed.
7	Commit full files, keep diff minimal.
8	Update requirements.txt & env-var docs when importing new libs.
9	Record reasoning in EXPLANATIONS.md—max 200 words.

4 · Coding Standards
Imports sorted by ruff-isort.

Type hints everywhere except trivial lambdas.

Constants in api/constants.py; no magic strings.

Logging via logging_utils.get_logger(); never print().

DB enums: always update both Alembic & ORM.

Retry external calls with tenacity (0.5 → 8 s back-off).

Background jobs: new session per run, always commit/rollback.

5 · Files & Migration Policy
Migrations: modify alembic/versions/001_initial_schema.py; keep a single migration file.

Models: update __all__ list.

Routers: plural paths (/messages, /appointments).

Services: wrap API logic; no DB code inside.

Jobs: one job = one file; idempotent.

6 · Guardrails for Consistency
Problem class	Guard
Undefined symbol	Static type check step (#3).
Enum mismatch	Sync Alembic enum + ORM Enum.
Calendar / external creds	Raise clear RuntimeError if env missing.
Timezone drift	Store TIMESTAMPTZ; convert on output only.
Growth of spaghetti	Place new code in correct folder; no circular imports.

7 · Performance & Observability
API latency target: < 200 ms p95.

DB: ensure indices before adding ILIKE queries.

Prometheus: expose new counters via monitoring.py if adding routers.

Use PROMETHEUS_PORT env var.

8 · Upcoming Feature Awareness
Leave extension points:

Telegram → services/telegram.py, /telegram_webhook router.

Instagram → services/instagram.py, /instagram_webhook.

Calendar → functions in services/calendar.py, re-use Appointment.google_event_id.

Do not bake hard-coded channel logic in core; route through send_text(channel, …) façade.

9 · Commit Etiquette
Message prefix [Fix], [Feat], [Refactor], [Docs].

If branch protection blocks merge, request review—no direct push to main.

10 · Fallback Language
Client-facing default French; fallback English.

Use utils/i18n.py::tr() to localise replies (already present or create).

End of agents.md
