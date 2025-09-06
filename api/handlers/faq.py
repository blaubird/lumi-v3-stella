from __future__ import annotations

from typing import cast

from api.cache import get_cached_faqs
from api.logging_utils import get_logger
from api.models import Message, Usage

from .base import Context

log = get_logger(__name__)


class FaqHandler:
    async def handle(self, ctx: Context) -> bool:
        faqs = await get_cached_faqs(ctx["redis"], ctx["db"], ctx["tenant_id"])
        faq = next(
            (f for f in faqs if f["question"].lower() == ctx["text"].lower()),
            None,
        )
        if not faq:
            return False

        answer = cast(str, faq["answer"])
        token_count = 0

        bot_message = Message(
            tenant_id=ctx["tenant_id"],
            role="assistant",
            text=answer,
            tokens=token_count,
        )
        ctx["db"].add(bot_message)

        outbound_usage = Usage(
            tenant_id=ctx["tenant_id"],
            direction="outbound",
            tokens=token_count,
            msg_ts=ctx["ts"],
        )
        ctx["db"].add(outbound_usage)

        ctx["reply"] = answer
        return True
