from __future__ import annotations

from typing import cast

from api.ai import get_rag_response
from logging_utils import get_logger
from models import Message, Usage

from .base import Context

log = get_logger(__name__)


class AiHandler:
    async def handle(self, ctx: Context) -> bool:
        try:
            response = await get_rag_response(
                db=ctx["db"],
                tenant_id=ctx["tenant_id"],
                user_query=ctx["text"],
                system_prompt=cast(str, ctx["tenant"].get("system_prompt")),
            )
        except Exception as exc:
            log.error(
                "Error processing message response",
                extra={"tenant_id": ctx["tenant_id"], "error": str(exc)},
                exc_info=True,
            )
            return False

        answer = response["answer"]
        token_count = response.get("token_count", 0)

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
