"""Centralised constants shared across the API."""

from __future__ import annotations

from typing import Final, FrozenSet

RUN_MIGRATIONS_ON_STARTUP_ENV_VAR: Final[str] = "RUN_MIGRATIONS_ON_STARTUP"
TRUTHY_ENV_VALUES: Final[FrozenSet[str]] = frozenset({"1", "true", "yes"})
FALSY_ENV_VALUES: Final[FrozenSet[str]] = frozenset({"0", "false", "no"})
