"""Alembic migration helper utilities

This module provides helper functions for making Alembic migrations more robust,
particularly for handling migration consolidation and preventing common errors.
"""

import os
from sqlalchemy import create_engine, text
from alembic.config import Config as AlembicConfig
from alembic import command
from logging_utils import get_logger

logger = get_logger(__name__)


def reset_migration_history(database_url, revision):
    """
    Reset the alembic_version table to point to a specific revision.

    Args:
        database_url: Database connection URL
        revision: The revision identifier to set as current

    Returns:
        bool: True if successful, False otherwise
    """
    try:
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
                        f"INSERT INTO alembic_version (version_num) VALUES ('{revision}')"
                    )
                )
                conn.commit()
                return True
            else:
                # Table doesn't exist, likely first run
                return False
    except Exception as e:
        logger.error(
            "Error resetting migration history", extra={"error": str(e)}, exc_info=e
        )
        return False


def check_migration_consistency(alembic_ini_path):
    """
    Check if the migrations in the versions directory are consistent with the database.

    Args:
        alembic_ini_path: Path to alembic.ini file

    Returns:
        tuple: (is_consistent, current_head, db_version)
    """
    try:
        # Get current head revision
        alembic_cfg = AlembicConfig(alembic_ini_path)
        heads = command.heads(alembic_cfg, verbose=False)
        current_head = heads[0] if heads else None

        # Get database version
        engine = create_engine(os.environ.get("DATABASE_URL", ""))
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            db_version = result.scalar()

        return (current_head == db_version, current_head, db_version)
    except Exception as e:
        logger.error(
            "Error checking migration consistency", extra={"error": str(e)}, exc_info=e
        )
        return (False, None, None)


def safe_stamp_head(alembic_ini_path):
    """
    Safely stamp the database with the current head revision.

    Args:
        alembic_ini_path: Path to alembic.ini file

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        alembic_cfg = AlembicConfig(alembic_ini_path)
        command.stamp(alembic_cfg, "head")
        return True
    except Exception as e:
        logger.error("Error stamping head", extra={"error": str(e)}, exc_info=e)
        return False
