import json
from typing import Any


from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from api.logging_utils import get_logger
from api.monitoring import CACHE_HIT, CACHE_MISS
from api.models import FAQ, Tenant

TENANT_TTL = 60
FAQ_TTL = 300

logger = get_logger(__name__)


async def cache_json_get(
    redis: Redis, key: str, bucket: str | None = None
) -> Any | None:
    try:
        raw = await redis.get(key)
    except RedisError as e:
        if bucket:
            CACHE_MISS.labels(bucket=bucket).inc()
        logger.warning("Redis get failed", extra={"key": key, "error": str(e)})
        return None
    if raw is None:
        if bucket:
            CACHE_MISS.labels(bucket=bucket).inc()
        return None
    if bucket:
        CACHE_HIT.labels(bucket=bucket).inc()
    return json.loads(raw)


async def cache_json_set(redis: Redis, key: str, value: Any, ttl: int) -> None:
    try:
        await redis.set(key, json.dumps(value, separators=(",", ":")), ex=ttl)
    except RedisError as e:
        logger.warning("Redis set failed", extra={"key": key, "error": str(e)})


async def get_cached_tenant(
    redis: Redis, db: Session, tenant_id: str
) -> dict[str, Any] | None:
    key = f"tenant:{tenant_id}:config"
    tenant = await cache_json_get(redis, key, "tenant")
    if tenant is not None:
        return tenant
    obj = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if obj is None:
        return None
    dto = {
        "id": obj.id,
        "phone_id": obj.phone_id,
        "wh_token": obj.wh_token,
        "system_prompt": obj.system_prompt,
    }
    await cache_json_set(redis, key, dto, TENANT_TTL)
    return dto


async def get_cached_faqs(
    redis: Redis, db: Session, tenant_id: str
) -> list[dict[str, Any]]:
    key = f"tenant:{tenant_id}:faq"
    faqs = await cache_json_get(redis, key, "faq")
    if faqs is not None:
        return faqs
    rows = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
    dto = [{"question": row.question, "answer": row.answer} for row in rows]
    await cache_json_set(redis, key, dto, FAQ_TTL)
    return dto
