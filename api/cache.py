from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy.orm import Session

from services.tenant_config import get_tenant_config, get_tenant_faqs


async def get_cached_tenant(
    _redis: Any, db: Session, tenant_id: str
) -> Optional[dict[str, Any]]:
    return await get_tenant_config(db, tenant_id)


async def get_cached_faqs(
    _redis: Any, db: Session, tenant_id: str
) -> List[dict[str, Any]]:
    return await get_tenant_faqs(db, tenant_id)


__all__ = ["get_cached_tenant", "get_cached_faqs"]
