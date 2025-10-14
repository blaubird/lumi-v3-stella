from __future__ import annotations

from redis.exceptions import RedisError

from config import settings
from logging_utils import get_logger
from redis_client import ns_key, redis_wrapper

logger = get_logger(__name__)


async def invalidate_tenant_namespace(tenant_id: str) -> None:
    client = redis_wrapper.client
    if client is None:
        logger.debug(
            "Redis client unavailable; skipping namespace invalidation",
            extra={"tenant_id": tenant_id},
        )
        return

    pattern = ns_key(f"tenant:{tenant_id}:*")
    scan_count = max(1, getattr(settings, "REDIS_SCAN_COUNT", 100))
    try:
        batch: list[str] = []
        async for key in client.scan_iter(match=pattern, count=scan_count):
            batch.append(key)
            if len(batch) >= scan_count:
                await client.unlink(*batch)
                batch.clear()
        if batch:
            await client.unlink(*batch)
    except RedisError as exc:
        logger.warning(
            "Failed to invalidate tenant cache namespace",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
    except Exception as exc:  # pragma: no cover - defensive catch
        logger.warning(
            "Unexpected error during tenant cache invalidation",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )


__all__ = ["invalidate_tenant_namespace"]
