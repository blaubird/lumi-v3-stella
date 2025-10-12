from __future__ import annotations

from typing import Any


class TenantIdNormalizationError(ValueError):
    """Raised when a tenant identifier cannot be normalised."""


TENANT_ID_OPENAPI_EXAMPLES = ["1", "test_tenant_X"]


def normalize_tenant_id(value: Any, *, field_name: str | None = None) -> str:
    """Coerce inbound tenant identifiers to their canonical string form.

    Accepts values supplied as strings or integers and rejects boolean/null
    inputs which otherwise implicitly coerce to integers in Python.  Empty
    identifiers are disallowed so downstream code never queries with a blank
    key.
    """

    label = field_name or "tenant_id"

    if value is None:
        raise TenantIdNormalizationError(f"{label} is required")

    if isinstance(value, bool):
        raise TenantIdNormalizationError(f"{label} must be a string identifier")

    normalized = str(value).strip()

    if not normalized:
        raise TenantIdNormalizationError(f"{label} cannot be empty")

    return normalized
