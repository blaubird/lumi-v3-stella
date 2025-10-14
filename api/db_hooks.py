from __future__ import annotations

import asyncio
from typing import Any, Iterable, Set

from sqlalchemy import event
from sqlalchemy.orm import Session

from logging_utils import get_logger
from models import Appointment, FAQ, Message, Tenant, Usage
from services.cache_invalidate import invalidate_tenant_namespace

logger = get_logger(__name__)

_TRACKED_MODELS: tuple[type[Any], ...] = (Tenant, Message, FAQ, Usage, Appointment)
_SESSION_KEY = "_cache_invalidation_tenant_ids"


def _extract_tenant_id(obj: Any) -> str | None:
    if isinstance(obj, Tenant):
        return str(obj.id)
    tenant_id = getattr(obj, "tenant_id", None)
    if tenant_id is None:
        return None
    return str(tenant_id)


def _iter_tracked(session: Session) -> Iterable[Any]:
    for collection in (session.new, session.dirty, session.deleted):
        for obj in collection:
            if isinstance(obj, _TRACKED_MODELS):
                yield obj


@event.listens_for(Session, "after_flush")
def collect_tenant_ids(session: Session, _flush_context) -> None:  # type: ignore[override]
    tenant_ids: Set[str] = session.info.setdefault(_SESSION_KEY, set())
    for obj in _iter_tracked(session):
        tenant_id = _extract_tenant_id(obj)
        if tenant_id:
            tenant_ids.add(tenant_id)


@event.listens_for(Session, "after_commit")
def schedule_tenant_cache_invalidation(session: Session) -> None:
    tenant_ids: Set[str] = session.info.pop(_SESSION_KEY, set())
    if not tenant_ids:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "No running event loop for cache invalidation",
            extra={"tenant_ids": list(tenant_ids)},
        )
        return

    for tenant_id in tenant_ids:
        loop.create_task(invalidate_tenant_namespace(tenant_id))
        logger.debug(
            "Scheduled tenant cache invalidation",
            extra={"tenant_id": tenant_id},
        )
