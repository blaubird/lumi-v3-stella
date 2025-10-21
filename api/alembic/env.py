"""Alembic environment configuration for Lumi."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

import sqlalchemy as sa
from alembic import context
from logging_utils import get_logger
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

logger = get_logger("alembic.env")

config = context.config


def _resolve_database_url() -> str:
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        message = (
            "DATABASE_URL is required to run Alembic migrations. "
            "Set it to a PostgreSQL connection string (postgresql://)."
        )
        logger.error(message)
        raise RuntimeError(message)

    try:
        parsed_url: URL = make_url(raw_url)
    except ArgumentError as exc:  # pragma: no cover - defensive guard
        message = "DATABASE_URL is not a valid SQLAlchemy URL."
        logger.error(message, extra={"error": str(exc)})
        raise RuntimeError(f"{message} ({exc})") from exc

    if parsed_url.get_backend_name() != "postgresql":
        message = (
            "DATABASE_URL must use the 'postgresql' scheme. "
            f"Received '{parsed_url.drivername}'."
        )
        logger.error(message)
        raise RuntimeError(message)

    logger.info(
        "Resolved DATABASE_URL for Alembic",
        extra={"url": parsed_url.render_as_string(hide_password=True)},
    )
    return raw_url


DATABASE_URL = _resolve_database_url()
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

try:
    from database import Base
    import models  # noqa: F401  # Import side effects so metadata is populated
except Exception as exc:  # pragma: no cover - defensive guard
    logger.error(
        "Failed to import application metadata for Alembic.",
        extra={"error": str(exc)},
        exc_info=exc,
    )
    raise


target_metadata = Base.metadata
DEFAULT_SCHEMA = "public"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    logger.info("Running Alembic migrations (offline mode)")
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=DEFAULT_SCHEMA,
    )

    with context.begin_transaction():
        logger.info("Applying migrations", extra={"mode": "offline"})
        context.run_migrations()
        logger.info("Migrations applied", extra={"mode": "offline"})


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    logger.info("Running Alembic migrations (online mode)")
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(sa.text(f"SET search_path TO {DEFAULT_SCHEMA}"))

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=DEFAULT_SCHEMA,
        )

        with context.begin_transaction():
            logger.info("Applying migrations", extra={"mode": "online"})
            context.run_migrations()
            logger.info("Migrations applied", extra={"mode": "online"})


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
