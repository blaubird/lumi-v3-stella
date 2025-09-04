import os
import sys
import types
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("VERIFY_TOKEN", "test")
os.environ.setdefault("WH_TOKEN", "test")
os.environ.setdefault("WH_PHONE_ID", "1")
os.environ.setdefault("X_ADMIN_TOKEN", "test")


class FakeRedisClient:
    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass


def fake_from_url(*args: object, **kwargs: object) -> FakeRedisClient:
    return FakeRedisClient()


redis_module = cast(Any, types.ModuleType("redis.asyncio"))
redis_module.from_url = fake_from_url
redis_module.Redis = FakeRedisClient
sys.modules["redis.asyncio"] = redis_module

fake_gc = cast(Any, types.ModuleType("utils.google_calendar"))
fake_gc.create_event = lambda *args, **kwargs: ""
sys.modules["utils.google_calendar"] = fake_gc

sys.path.append("api")
from api.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_healthz() -> None:
    transport = ASGITransport(app=cast(Any, app))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert "status" in resp.json()
