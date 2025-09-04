from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Generator, cast

from fastapi import APIRouter, Depends, Query, Request, Response
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from cache import get_cached_tenant
from database import SessionLocal
from handlers import HANDLERS, Context, run_pipeline
from logging_utils import get_logger
from models import Message, Tenant, Usage
from services.whatsapp import send_whatsapp_message
from utils.i18n import detect_lang

logger = get_logger(__name__)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "lumi-verify-6969")
router = APIRouter(tags=["Webhook"])


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/webhook")
async def verify_webhook(
    mode: str = Query(None, alias="hub.mode"),
    challenge: str = Query(None, alias="hub.challenge"),
    verify_token: str = Query(None, alias="hub.verify_token"),
):
    logger.info(
        "Webhook verification request received",
        extra={"mode": mode, "token_provided": bool(verify_token)},
    )
    if mode == "subscribe" and verify_token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")
    logger.warning("Invalid webhook verification attempt")
    return Response(
        content="Verification failed", status_code=403, media_type="text/plain"
    )


@router.post("/webhook")
async def webhook_handler(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
        logger.debug("Webhook request received", extra={"body": body})
    except Exception:
        logger.error("Invalid JSON in webhook request")
        return {"status": "success"}

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_id = metadata.get("phone_number_id")

                tenant_db = db.query(Tenant).filter(Tenant.phone_id == phone_id).first()
                if not tenant_db:
                    logger.warning(
                        "Tenant not found for webhook", extra={"phone_id": phone_id}
                    )
                    continue

                tenant = await get_cached_tenant(
                    request.app.state.redis, db, cast(str, tenant_db.id)
                )
                if not tenant:
                    logger.warning(
                        "Tenant config not found", extra={"tenant_id": tenant_db.id}
                    )
                    continue

                for message in value.get("messages", []):
                    if message.get("type") == "text":
                        await process_message(
                            request.app.state.redis, db, tenant, message
                        )
    except Exception as e:
        logger.error(
            "Error processing webhook",
            extra={"error": str(e), "payload": body},
            exc_info=e,
        )
    return {"status": "success"}


async def process_message(
    redis: Redis, db: Session, tenant: Dict[str, Any], message: Dict[str, Any]
) -> None:
    try:
        message_id = message.get("id")
        from_number = message.get("from")
        text = message.get("text", {}).get("body", "")
        raw_ts = message.get("timestamp")
        ts = (
            datetime.fromtimestamp(int(raw_ts), timezone.utc)
            if raw_ts
            else datetime.now(timezone.utc)
        )

        logger.info(
            "Processing message",
            extra={
                "tenant_id": tenant["id"],
                "message_id": message_id,
                "from": from_number,
                "text_length": len(text),
            },
        )

        existing = db.query(Message).filter(Message.wa_msg_id == message_id).first()
        if existing:
            logger.info("Message already processed", extra={"message_id": message_id})
            return

        user_message = Message(
            tenant_id=tenant["id"],
            wa_msg_id=message_id,
            role="inbound",
            text=text,
            tokens=0,
        )
        db.add(user_message)

        inbound_usage = Usage(
            tenant_id=tenant["id"],
            direction="inbound",
            tokens=0,
            msg_ts=ts,
        )
        db.add(inbound_usage)

        ctx: Context = {
            "message": message,
            "text": text,
            "tenant_id": cast(str, tenant["id"]),
            "db": db,
            "redis": redis,
            "from_number": cast(str, from_number),
            "ts": ts,
            "lang": detect_lang(text),
            "reply": None,
            "attachment": None,
            "tenant": tenant,
        }

        await run_pipeline(ctx, HANDLERS)

        if ctx["reply"]:
            await send_whatsapp_message(
                phone_id=cast(str, tenant["phone_id"]),
                token=cast(str, tenant["wh_token"]),
                recipient=cast(str, from_number),
                message=cast(str, ctx["reply"]),
                attachment=ctx["attachment"],
            )

        db.commit()
    except Exception as e:
        logger.error(
            "Error in message processing",
            extra={"error": str(e), "message": message},
            exc_info=e,
        )
