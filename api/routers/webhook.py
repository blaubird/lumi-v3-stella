import os
import json
from typing import Dict, Any, cast
from fastapi import APIRouter, Depends, Request, Query, Response
from sqlalchemy.orm import Session
from redis.asyncio import Redis
from database import SessionLocal
from models import Tenant, Message, Usage, Appointment
from cache import get_cached_faqs, get_cached_tenant
import re
from ai import get_rag_response
from services.whatsapp import send_whatsapp_message
from logging_utils import get_logger
from utils.i18n import detect_lang, tr
from utils.ics_generator import generate_ics
from datetime import datetime, timezone

# Initialize logger
logger = get_logger(__name__)
BOOK_RE = re.compile(r"\bbook\s+(\d{1,2}[/-]\d{1,2})\s+(\d{1,2}:\d{2})", re.I)

# Define verification token as a constant
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "lumi-verify-6969")

# Use router without trailing slash to avoid 307 redirects
router = APIRouter(tags=["Webhook"])


# Dependency to get DB session
def get_db():
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
    """
    Verify webhook endpoint for WhatsApp Business API using Meta's verification flow
    """
    logger.info(
        "Webhook verification request received",
        extra={"mode": mode, "token_provided": bool(verify_token)},
    )

    # Check mode and token
    if mode == "subscribe" and verify_token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        # Return raw challenge as plain text
        return Response(content=challenge, media_type="text/plain")

    # Invalid verification
    logger.warning("Invalid webhook verification attempt")
    return Response(
        content="Verification failed", status_code=403, media_type="text/plain"
    )


@router.post("/webhook")
async def webhook_handler(request: Request, db: Session = Depends(get_db)):
    """
    Handle webhook events from WhatsApp Business API
    """
    # Parse request body
    try:
        body = await request.json()
        logger.debug("Webhook request received", extra={"body": body})
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook request")
        # Return success response instead of raising an exception
        return {"status": "success"}

    try:
        # Process each entry
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_id = metadata.get("phone_number_id")

                # Find tenant by phone_id
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

                # Process messages
                for message in value.get("messages", []):
                    if message.get("type") == "text":
                        await process_message(
                            request.app.state.redis, db, tenant, message
                        )
    except Exception as e:
        # Log the error but still return success
        logger.error(
            "Error processing webhook",
            extra={"error": str(e), "payload": body},
            exc_info=e,
        )

    return {"status": "success"}


async def process_message(
    redis: Redis, db: Session, tenant: Dict[str, Any], message: Dict[str, Any]
):
    """
    Process a message from WhatsApp
    """
    try:
        # Extract message details
        message_id = message.get("id")
        from_number = message.get("from")
        text = message.get("text", {}).get("body", "")
        raw_ts = message.get("timestamp")  # Extract timestamp from message

        # Convert epoch timestamp to datetime object
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

        # Check if message already processed
        existing = db.query(Message).filter(Message.wa_msg_id == message_id).first()
        if existing:
            logger.info("Message already processed", extra={"message_id": message_id})
            return

        # Save user message
        user_message = Message(
            tenant_id=tenant["id"],
            wa_msg_id=message_id,
            role="inbound",
            text=text,
            tokens=0,  # Initialize with 0 tokens
        )
        db.add(user_message)

        # Track inbound message usage (with 0 tokens as specified)
        usage_record = Usage(
            tenant_id=tenant["id"],
            direction="inbound",
            tokens=0,
            msg_ts=ts,  # Use converted datetime
            total_tokens=0,
        )
        db.add(usage_record)
        db.commit()

        m = BOOK_RE.search(text)
        if m:
            date_part, time_part = m.groups()
            try:
                # Assuming current year for booking if not specified
                current_year = datetime.now(timezone.utc).year
                # Parse date and time, handling both MM/DD and MM-DD formats
                month, day = map(int, re.split(r"[/-]", date_part))
                hour, minute = map(int, time_part.split(":"))

                # Construct datetime object in UTC
                starts_at = datetime(
                    current_year, month, day, hour, minute, tzinfo=timezone.utc
                )

                # If the parsed date is in the past, assume next year
                if starts_at < datetime.now(timezone.utc):
                    starts_at = datetime(
                        current_year + 1, month, day, hour, minute, tzinfo=timezone.utc
                    )

            except ValueError as exc:
                logger.error(
                    "Failed to parse booking time",
                    extra={"text": text, "error": str(exc)},
                )
                starts_at = None

            if starts_at:
                appt = Appointment(
                    tenant_id=tenant["id"],
                    customer_phone=from_number,
                    customer_email=None,
                    starts_at=starts_at,
                    status="pending",
                )
                db.add(appt)
                db.commit()  # Commit appointment to get its ID if needed later, and ensure it's saved

                lang = detect_lang(text)
                dt_str = starts_at.strftime("%d/%m %H:%M")
                reply = tr("booking.confirmed", lang, dt=dt_str)
                token_count = len(reply.split())

                reply = f"✅ booked for {starts_at.strftime('%d/%m %H:%M')}. You’ll get a reminder."
                token_count = len(reply.split())

                bot_message = Message(
                    tenant_id=tenant["id"],
                    role="assistant",
                    text=reply,
                    tokens=token_count,
                )
                db.add(bot_message)

                outbound_usage = Usage(
                    tenant_id=cast(str, tenant["id"]),
                    direction="outbound",
                    tokens=token_count,
                    msg_ts=ts,
                    total_tokens=token_count,
                    completion_tokens=token_count,
                )
                db.add(outbound_usage)
                db.commit()

                ics = generate_ics("Appointment", starts_at)
                await send_whatsapp_message(
                    phone_id=cast(str, tenant["phone_id"]),
                    token=cast(str, tenant["wh_token"]),
                    recipient=cast(str, from_number),
                    message=reply,
                    attachment=ics,
                )
                return

        # Check for exact FAQ match before using RAG
        faqs = await get_cached_faqs(redis, db, cast(str, tenant["id"]))
        faq = next((f for f in faqs if f["question"].lower() == text.lower()), None)

        if faq:
            logger.info(
                "Exact FAQ match found",
                extra={"tenant_id": tenant["id"], "question": faq["question"]},
            )

            answer = cast(str, faq["answer"])
            token_count = len(answer.split())

            # Save bot message
            bot_message = Message(
                tenant_id=tenant["id"],
                role="assistant",
                text=answer,
                tokens=token_count,
            )
            db.add(bot_message)

            # Track outbound message usage
            outbound_usage = Usage(
                tenant_id=tenant["id"],
                direction="outbound",
                tokens=token_count,
                msg_ts=ts,
                total_tokens=token_count,
                completion_tokens=token_count,
            )
            db.add(outbound_usage)
            db.commit()

            # Send response via WhatsApp
            await send_whatsapp_message(
                phone_id=cast(str, tenant["phone_id"]),
                token=cast(str, tenant["wh_token"]),
                recipient=cast(str, from_number),
                message=answer,
            )

            logger.info(
                "FAQ match response sent",
                extra={
                    "tenant_id": tenant["id"],
                    "to": from_number,
                    "response_length": len(answer),
                    "token_count": token_count,
                },
            )
            return
        else:
            # Log for debugging
            logger.debug(
                "No exact FAQ match found",
                extra={"tenant_id": tenant["id"], "text": text},
            )
        # Generate response using RAG if no exact match
        try:
            lang = detect_lang(text)
            response = await get_rag_response(
                tenant_id=cast(str, tenant["id"]),
                user_text=text,
                lang=lang,
                db=db,
                redis=redis,
            )

            answer = response["text"]
            token_count = response.get("total_tokens", 0)

            # Save bot message
            bot_message = Message(
                tenant_id=cast(str, tenant["id"]),
                role="assistant",
                text=answer,
                tokens=token_count,
            )
            db.add(bot_message)

            # Track outbound message usage with actual token count
            db.commit()

            # Send response via WhatsApp using the send_whatsapp_message function
            await send_whatsapp_message(
                phone_id=cast(str, tenant["phone_id"]),
                token=cast(str, tenant["wh_token"]),
                recipient=cast(str, from_number),
                message=answer,
            )

            logger.info(
                "Response sent",
                extra={
                    "tenant_id": cast(str, tenant["id"]),
                    "to": from_number,
                    "response_length": len(answer),
                    "token_count": token_count,
                },
            )
        except Exception as e:
            logger.error(
                "Error processing message response",
                extra={
                    "tenant_id": cast(str, tenant["id"]),
                    "message_id": message_id,
                    "error": str(e),
                },
                exc_info=e,
            )
    except Exception as e:
        logger.error(
            "Error in message processing",
            extra={"error": str(e), "message": message},
            exc_info=e,
        )
