from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import uuid4

from sqlalchemy.orm import Session

from ai import get_rag_response
from deps import get_db
from logging_utils import get_logger
from models import Message, Tenant
from redis_client import redis_wrapper
from services.whatsapp import send_whatsapp_message
from utils.i18n import detect_lang

logger = get_logger(__name__)


@contextmanager
def _session_scope() -> Iterator[Session]:
    """Provide a transactional scope around operations."""

    generator = get_db()
    db = next(generator)
    try:
        yield db
    finally:
        generator.close()


async def process_ai_reply(tenant_id: str, wa_msg_id: str, user_text: str) -> None:
    """Generate and dispatch an AI reply using the shared RAG pipeline."""

    logger.info(
        "Starting AI reply processing",
        extra={"tenant_id": tenant_id, "wa_msg_id": wa_msg_id, "text_length": len(user_text)},
    )

    trace_id = str(uuid4())

    try:
        with _session_scope() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant is None:
                logger.error("Tenant not found", extra={"tenant_id": tenant_id})
                return

            if not tenant.phone_id or not tenant.wh_token:
                logger.error(
                    "Tenant missing WhatsApp credentials",
                    extra={"tenant_id": tenant_id},
                )
                return

            lang = detect_lang(user_text)
            response = await get_rag_response(
                tenant_id=str(tenant.id),
                user_text=user_text,
                lang=lang,
                db=db,
                redis=redis_wrapper.client,
                trace_id=trace_id,
            )

            reply_text = response.get("text", "")
            total_tokens = int(response.get("total_tokens", 0))

            bot_message = Message(
                tenant_id=str(tenant.id),
                role="assistant",
                text=reply_text,
                tokens=total_tokens,
            )
            db.add(bot_message)
            db.commit()

            recipient = wa_msg_id.split(":")[0] if ":" in wa_msg_id else wa_msg_id

            await send_whatsapp_message(
                phone_id=str(tenant.phone_id),
                token=str(tenant.wh_token),
                recipient=recipient,
                message=reply_text,
            )

            logger.info(
                "WhatsApp message sent",
                extra={"tenant_id": tenant_id, "recipient": recipient, "tokens": total_tokens},
            )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "Error in process_ai_reply",
            extra={"tenant_id": tenant_id, "error": str(exc), "trace_id": trace_id},
            exc_info=exc,
        )
    finally:
        logger.info("AI reply processing completed", extra={"tenant_id": tenant_id, "trace_id": trace_id})
