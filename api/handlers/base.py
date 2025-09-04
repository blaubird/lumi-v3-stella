from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, TypedDict

from redis.asyncio import Redis
from sqlalchemy.orm import Session

from models import Message, Usage


class Context(TypedDict):
    message: Dict[str, Any]
    text: str
    tenant_id: str
    db: Session
    redis: Redis
    from_number: str
    ts: datetime
    lang: str
    reply: Optional[str]
    attachment: Optional[bytes]
    tenant: Dict[str, Any]
    user_message: Message
    inbound_usage: Usage


class Handler(Protocol):
    async def handle(self, ctx: Context) -> bool: ...


async def run_pipeline(ctx: Context, handlers: List[Handler]) -> bool:
    for handler in handlers:
        if await handler.handle(ctx):
            return True
    return False
