from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from logging_utils import get_logger
from models import FAQ, Tenant
from redis_client import cached_json, ns_key

logger = get_logger(__name__)


def tenant_config_key(tenant_id: str) -> str:
    return ns_key(f"tenant:{tenant_id}:config:v1")


def tenant_faqs_key(tenant_id: str) -> str:
    return ns_key(f"tenant:{tenant_id}:faqs:v1")


async def get_tenant_config(
    db: Session, tenant_id: str, ttl: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    cache_ttl = settings.CACHE_TTL_CONFIG_SEC if ttl is None else ttl

    async def _loader() -> Optional[Dict[str, Any]]:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant is None:
            logger.debug("Tenant config not found", extra={"tenant_id": tenant_id})
            return None
        return {
            "id": tenant.id,
            "phone_id": tenant.phone_id,
            "wh_token": tenant.wh_token,
            "system_prompt": tenant.system_prompt,
        }

    return await cached_json(tenant_config_key(tenant_id), cache_ttl, _loader)


async def get_tenant_faqs(
    db: Session, tenant_id: str, ttl: Optional[int] = None
) -> List[Dict[str, Any]]:
    cache_ttl = settings.CACHE_TTL_FAQS_SEC if ttl is None else ttl

    async def _loader() -> List[Dict[str, Any]]:
        rows = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
        return [
            {
                "id": faq.id,
                "question": faq.question,
                "answer": faq.answer,
            }
            for faq in rows
        ]

    cached = await cached_json(tenant_faqs_key(tenant_id), cache_ttl, _loader)
    return cached or []


__all__ = [
    "get_tenant_config",
    "get_tenant_faqs",
    "tenant_config_key",
    "tenant_faqs_key",
]
