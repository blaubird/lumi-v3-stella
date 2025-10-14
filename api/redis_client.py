from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Awaitable, Callable, Optional, TypeVar
from urllib.parse import urlparse

from redis import asyncio as aioredis
from redis.exceptions import RedisError

from config import settings
from logging_utils import get_logger

T = TypeVar("T")

logger = get_logger(__name__)

_METRICS_ENABLED = bool(getattr(settings, "REDIS_METRICS", False))


def _hashed_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


class RedisWrapper:
    client: aioredis.Redis | None
    ok: bool
    last_latency_ms: float | None

    def __init__(self) -> None:
        self.client = None
        self.ok = False
        self.last_latency_ms = None
        self._init_lock = asyncio.Lock()

    async def init(self) -> None:
        async with self._init_lock:
            if self.client is not None:
                await self.close()

            redis_url = getattr(settings, "REDIS_URL", None)
            if not redis_url:
                logger.info("Redis disabled: REDIS_URL not configured")
                self.ok = False
                self.last_latency_ms = None
                self.client = None
                return

            kwargs: dict[str, Any] = {
                "decode_responses": True,
                "client_name": "lumi-v3-stella",
                "health_check_interval": getattr(
                    settings, "REDIS_HEALTHCHECK_SECONDS", 30
                ),
            }

            connect_timeout_ms = getattr(settings, "REDIS_CONNECT_TIMEOUT_MS", 500)
            if connect_timeout_ms:
                kwargs["socket_connect_timeout"] = connect_timeout_ms / 1000.0

            redis_db = getattr(settings, "REDIS_DB", None)
            try:
                parsed = urlparse(redis_url)
                has_db_in_url = bool(parsed.path and parsed.path.strip("/"))
            except ValueError:
                has_db_in_url = False

            if redis_db is not None and not has_db_in_url:
                kwargs["db"] = redis_db

            try:
                client = aioredis.from_url(redis_url, **kwargs)
            except Exception as exc:  # pragma: no cover - constructor errors rare
                logger.warning(
                    "Failed to construct Redis client",
                    extra={"error": str(exc)},
                )
                self.ok = False
                self.last_latency_ms = None
                self.client = None
                return

            self.client = client
            await self._refresh_health()
            if _METRICS_ENABLED and self.ok:
                logger.info(
                    "Redis connection healthy",
                    extra={"redis_latency_ms": self.last_latency_ms},
                )

    async def _refresh_health(self) -> None:
        if self.client is None:
            self.ok = False
            self.last_latency_ms = None
            return

        try:
            start = time.perf_counter()
            await self.client.ping()
            latency = (time.perf_counter() - start) * 1000
            self.last_latency_ms = round(latency, 2)
            await self.client.setex(ns_key("healthz:ping"), 30, "ok")
            self.ok = True
        except Exception as exc:  # pragma: no cover - network failures nondeterministic
            self.ok = False
            self.last_latency_ms = None
            logger.warning(
                "Redis health check failed",
                extra={"error": str(exc)},
            )

    async def ping(self) -> bool:
        await self._refresh_health()
        return self.ok

    async def close(self) -> None:
        if self.client is None:
            return
        try:
            await self.client.aclose()
        except Exception as exc:  # pragma: no cover - close errors rare
            logger.debug(
                "Error closing Redis client",
                extra={"error": str(exc)},
            )
        finally:
            self.client = None
            self.ok = False
            self.last_latency_ms = None


redis_wrapper = RedisWrapper()


def ns_key(raw: str) -> str:
    prefix = getattr(settings, "REDIS_PREFIX", "") or "lumi"
    if raw.startswith(":"):
        raw = raw[1:]
    return f"{prefix}:{raw}"


async def cached_json(
    key: str, ttl: int, loader_async_fn: Callable[[], Awaitable[T]]
) -> Optional[T]:
    value: Optional[T]
    client = redis_wrapper.client

    if client is None:
        if _METRICS_ENABLED:
            logger.debug(
                "Redis bypassed (no client)", extra={"cache_key": _hashed_key(key)}
            )
        return await loader_async_fn()

    try:
        cached = await client.get(key)
    except RedisError as exc:
        if _METRICS_ENABLED:
            logger.debug(
                "Redis cache read error",
                extra={"cache_key": _hashed_key(key), "error": str(exc)},
            )
        return await loader_async_fn()

    if cached is not None:
        try:
            value = json.loads(cached)
        except json.JSONDecodeError:
            if _METRICS_ENABLED:
                logger.debug(
                    "Redis cache decode error",
                    extra={"cache_key": _hashed_key(key)},
                )
        else:
            if _METRICS_ENABLED:
                logger.debug("Redis cache hit", extra={"cache_key": _hashed_key(key)})
            return value

    if _METRICS_ENABLED:
        logger.debug("Redis cache miss", extra={"cache_key": _hashed_key(key)})

    value = await loader_async_fn()
    if value is None or ttl <= 0:
        return value

    try:
        payload = json.dumps(value, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        if _METRICS_ENABLED:
            logger.debug(
                "Redis cache serialization error",
                extra={"cache_key": _hashed_key(key), "error": str(exc)},
            )
        return value

    try:
        await client.setex(key, ttl, payload)
    except RedisError as exc:
        if _METRICS_ENABLED:
            logger.debug(
                "Redis cache write error",
                extra={"cache_key": _hashed_key(key), "error": str(exc)},
            )
    return value


__all__ = [
    "RedisWrapper",
    "cached_json",
    "ns_key",
    "redis_wrapper",
]
