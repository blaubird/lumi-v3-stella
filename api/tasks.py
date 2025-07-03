import os
import logging
from openai import AsyncOpenAI
from database import SessionLocal
from models import Tenant, Message, Usage
from ai import find_relevant_faqs
from services.whatsapp import send_whatsapp_message
from logging_utils import get_logger

logger = get_logger(__name__)
# Add specific logger for AI operations
logger_ai = logging.getLogger("api.ai")

# Get OpenAI model from environment
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "ft:gpt-4.1-nano-2025-04-14:luminiteq:flora:Bdezn8Rp")

async def process_ai_reply(tenant_id: str, wa_msg_id: str, user_text: str):
    """
    Process AI reply asynchronously
    
    Args:
        tenant_id: Tenant ID
        wa_msg_id: WhatsApp message ID
        text: User message text
    """
    # Create a new database session
    db = SessionLocal()
    
    try:
        logger.info("Starting AI reply processing", extra={
            "tenant_id": tenant_id,
            "wa_msg_id": wa_msg_id,
            "text_length": len(user_text)
        })
        
        # Get tenant information
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
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
            faq_context = "Relevant information from knowledge base:\n" + "\n\n".join(faq_parts)
        else:
            faq_context = "No specific information found in the knowledge base for this query."
        
        # Build messages list with system prompt first
        messages = [
            {"role": "system", "content": tenant.system_prompt + "\n\n" + faq_context}
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
            # Standardize role naming: 'user' -> 'inbound', 'bot' -> 'assistant'
            standardized_role = "inbound" if msg.role == "user" else "assistant" if msg.role == "bot" else msg.role
            messages.append({"role": standardized_role, "content": msg.text})
        
        # Add current user message
        messages.append({"role": "inbound", "content": user_text}) # Changed 'user' to 'inbound'
        
        logger_ai.info(f"Calling model {OPENAI_MODEL}")
        
        logger.info("Calling OpenAI API", extra={
            "tenant_id": tenant.id,
            "model": OPENAI_MODEL,
            "message_count": len(messages),
            "temperature": 0.4
        })
        
        # Call OpenAI API
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
            return
            
        ai = AsyncOpenAI(api_key=api_key)
        
        try:
            response = await ai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.4
            )
            
            # Extract reply text and token count
            reply_text = response.choices[0].message.content
            token_count = response.usage.total_tokens
            
            logger.info("Received OpenAI response", extra={
                "tenant_id": tenant.id,
                "token_count": token_count,
                "reply_length": len(reply_text)
            })
            
            # Save bot message
            bot_message = Message(
                tenant_id=tenant.id,
                role="assistant", # Changed 'bot' to 'assistant'
                text=reply_text,
                tokens=token_count
            )
            db.add(bot_message)
            
            # Insert outbound usage record
            usage_record = Usage(
                tenant_id=tenant.id,
                direction="outbound",
                tokens=token_count
            )
            db.add(usage_record)
            db.commit()
            
            # Get WhatsApp credentials from tenant
            phone_id = os.getenv("WH_PHONE_ID", tenant.phone_id)
            token = os.getenv("WH_TOKEN", tenant.wh_token)
            
            # Extract user phone from wa_msg_id (format: "phone:message_id")
            user_phone = wa_msg_id.split(":")[0] if ":" in wa_msg_id else wa_msg_id
            
            # Send WhatsApp message
            await send_whatsapp_message(phone_id, token, user_phone, reply_text)
            
            logger.info("WhatsApp message sent", extra={
                "tenant_id": tenant.id,
                "to": user_phone
            })
        except Exception as e:
            logger_ai.error(f"OpenAI error: {e}")
            return "Извините, временная ошибка. Попробуйте позже."
            
    except Exception as e:
        logger.error("Error in process_ai_reply", extra={
            "tenant_id": tenant.id,
            "error": str(e)
        }, exc_info=e)
    finally:
        # Close the DB session
        db.close()
        logger.info("AI reply processing completed", extra={"tenant_id": tenant_id})


