from typing import List, Optional, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from ai import find_relevant_faqs
from config import settings
from database import SessionLocal
from logging_utils import get_logger
from models import Message, Tenant, Usage
from services.whatsapp import send_whatsapp_message

logger = get_logger(__name__)
logger_ai = get_logger("api.ai")

# Configured OpenAI model
OPENAI_MODEL = settings.OPENAI_MODEL


async def process_ai_reply(tenant_id: str, wa_msg_id: str, user_text: str) -> None:
    """
    Process AI reply asynchronously

    Args:
        tenant_id: Tenant ID
        wa_msg_id: WhatsApp message ID
        text: User message text
    """
    # Create a new database session
    db = SessionLocal()
    tenant: Optional[Tenant] = None

    try:
        logger.info(
            "Starting AI reply processing",
            extra={
                "tenant_id": tenant_id,
                "wa_msg_id": wa_msg_id,
                "text_length": len(user_text),
            },
        )

        # Get tenant information
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant is None:
            logger.error("Tenant not found", extra={"tenant_id": tenant_id})
            return

        # Run embedding lookup and retrieve top-K FAQs
        relevant_faqs = await find_relevant_faqs(db, tenant_id, user_text, top_k=3)

        # Build context from FAQs
        faq_context = ""
        if relevant_faqs:
            faq_parts = []
            for i, faq in enumerate(relevant_faqs):
                faq_parts.append(f"FAQ {i+1}:\nQ: {faq.question}\nA: {faq.answer}")
            faq_context = "Relevant information from knowledge base:\n" + "\n\n".join(
                faq_parts
            )
        else:
            faq_context = (
                "No specific information found in the knowledge base for this query."
            )

        # Build messages list with system prompt first
        messages: List[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": cast(str, tenant.system_prompt) + "\n\n" + faq_context,
            }
        ]

        # Add recent conversation history
        history_messages = (
            db.query(Message)
            .filter_by(tenant_id=tenant_id)
            .order_by(Message.id.desc())
            .limit(6)  # Last 3 exchanges (3 user + 3 bot messages)
            .all()[::-1]  # Reverse to get chronological order
        )

        for msg in history_messages:
            role = cast(str, msg.role)
            standardized_role = (
                "inbound" if role == "user" else "assistant" if role == "bot" else role
            )
            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    {"role": standardized_role, "content": cast(str, msg.text)},
                )
            )

        # Add current user message
        messages.append(
            cast(ChatCompletionMessageParam, {"role": "inbound", "content": user_text})
        )

        logger_ai.info(f"Calling model {OPENAI_MODEL}")

        logger.info(
            "Calling OpenAI API",
            extra={
                "tenant_id": tenant.id,
                "model": OPENAI_MODEL,
                "message_count": len(messages),
                "temperature": 0.4,
            },
        )

        # Call OpenAI API
        ai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        try:
            response = await ai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=cast(List[ChatCompletionMessageParam], messages),
                temperature=0.4,
            )

            # Extract reply text and token count
            reply_text = response.choices[0].message.content or ""
            usage = response.usage
            token_count = (
                usage.total_tokens if usage and usage.total_tokens is not None else 0
            )

            logger.info(
                "Received OpenAI response",
                extra={
                    "tenant_id": tenant.id,
                    "token_count": token_count,
                    "reply_length": len(reply_text),
                },
            )

            # Save bot message
            bot_message = Message(
                tenant_id=tenant.id,
                role="assistant",
                text=reply_text,
                tokens=token_count,
            )
            db.add(bot_message)

            # Insert outbound usage record
            usage_record = Usage(
                tenant_id=tenant.id,
                direction="outbound",
                tokens=token_count,
            )
            db.add(usage_record)
            db.commit()

            # Get WhatsApp credentials from tenant
            phone_id = settings.WH_PHONE_ID
            token = settings.WH_TOKEN

            # Extract user phone from wa_msg_id (format: "phone:message_id")
            user_phone = wa_msg_id.split(":")[0] if ":" in wa_msg_id else wa_msg_id

            # Send WhatsApp message
            await send_whatsapp_message(phone_id, token, user_phone, reply_text)

            logger.info(
                "WhatsApp message sent",
                extra={"tenant_id": tenant.id, "to": user_phone},
            )
        except Exception as e:
            logger_ai.error(f"OpenAI error: {e}")
            return

    except Exception as e:
        logger.error(
            "Error in process_ai_reply",
            extra={"tenant_id": tenant.id if tenant else "unknown", "error": str(e)},
            exc_info=e,
        )
    finally:
        # Close the DB session
        db.close()
        logger.info("AI reply processing completed", extra={"tenant_id": tenant_id})
