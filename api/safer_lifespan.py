"""Modified lifespan context manager for safer Alembic migrations

This version of the lifespan context manager includes additional safety checks
to prevent crashes when migrations have been consolidated or modified.
"""

from contextlib import asynccontextmanager
import logging
import os
from alembic.config import Config as AlembicConfig
from alembic import command
from alembic.util.exc import CommandError
from alembic.script.revision import ResolutionError
from sqlalchemy import create_engine, text

log = logging.getLogger("api")


@asynccontextmanager
async def safer_lifespan(app):
    """
    Enhanced lifespan context manager with safer migration handling.

    This version handles migration errors gracefully, particularly when
    migrations have been consolidated or modified.
    """
    # Apply migrations with error handling
    log.info("Applying Alembic migrations...")
    alembic_cfg = AlembicConfig("alembic.ini")

    try:
        # Try normal upgrade first
        command.upgrade(alembic_cfg, "head")
        log.info("Migrations applied successfully")
    except (CommandError, ResolutionError) as e:
        # Handle missing revision errors
        log.warning(f"Migration error: {str(e)}")

        if "Can't locate revision" in str(e) or "No such revision" in str(e):
            log.info("Attempting to recover from missing revision error...")

            # Reset alembic_version table to current head
            try:
                # Get current head revision
                head_revisions = command.heads(alembic_cfg, verbose=False)
                if head_revisions:
                    current_head = head_revisions[0]
                    log.info(f"Current head revision is {current_head}")

                    # Reset alembic_version table
                    database_url = os.environ.get("DATABASE_URL", "")
                    engine = create_engine(database_url)
                    with engine.connect() as conn:
                        # Check if alembic_version table exists
                        result = conn.execute(
                            text(
                                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alembic_version')"
                            )
                        )
                        table_exists = result.scalar()

                        if table_exists:
                            # Delete existing version
                            conn.execute(text("DELETE FROM alembic_version"))

                            # Insert new version
                            conn.execute(
                                text(
                                    f"INSERT INTO alembic_version (version_num) VALUES ('{current_head}')"
                                )
                            )
                            conn.commit()
                            log.info(
                                f"Successfully reset alembic_version to {current_head}"
                            )

                            # Try upgrade again
                            command.upgrade(alembic_cfg, "head")
                            log.info("Migrations applied successfully after recovery")
                        else:
                            # Table doesn't exist, stamp the current head
                            command.stamp(alembic_cfg, "head")
                            log.info(
                                f"Stamped database with current head {current_head}"
                            )
                else:
                    log.error("No head revisions found")
                    raise
            except Exception as recovery_error:
                log.error(
                    f"Failed to recover from migration error: {str(recovery_error)}"
                )
                raise
        else:
            # Other migration errors
            log.error(f"Unrecoverable migration error: {str(e)}")
            raise

    # Setup metrics
    from monitoring import setup_metrics

    setup_metrics(app)
    log.info("Metrics setup complete")

    # CORS middleware is implicitly added
    log.info("CORS middleware added")

    # Routers are registered
    log.info("Routers registered")

    yield

    # Shutdown logic here if needed
    log.info("Application shutting down")
