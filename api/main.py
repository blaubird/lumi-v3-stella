import os
import time
from fastapi import FastAPI, Depends, Request, HTTPException, Query, Response
from alembic.config import Config
from alembic import command
import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# Changed to absolute imports as main.py is the entry point
from deps import get_db, tenant_by_phone_id 
from models import Message, Tenant 
from routers import admin as admin_router
from routers import rag as rag_router

# Import logging and monitoring utilities
from logging_utils import setup_logging, get_logger
from monitoring_utils import setup_monitoring, track_openai_call

# Environment Variable Sanitization
if os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY").strip()
if os.getenv("WH_TOKEN"):
    os.environ["WH_TOKEN"] = os.getenv("WH_TOKEN").strip()
if os.getenv("WH_PHONE_ID"):
    os.environ["WH_PHONE_ID"] = os.getenv("WH_PHONE_ID").strip()
if os.getenv("VERIFY_TOKEN"):
    os.environ["VERIFY_TOKEN"] = os.getenv("VERIFY_TOKEN").strip()

# Initialize OpenAI client
ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(
    title="Luminiteq WhatsApp Integration API",
    description="Handles WhatsApp webhooks, processes messages using AI, provides admin functionalities, and RAG capabilities.",
    version="1.3.0"
)

# Setup structured logging
logger = setup_logging(app)("main")

# Setup monitoring
setup_monitoring(app)

# Include the admin and RAG routers
app.include_router(admin_router.router)
app.include_router(rag_router.router)

@app.on_event("startup")
def startup_event():
    logger.info("Application startup: running Alembic migrations.")
    try:
        # Ensure alembic.ini path is correct relative to this file's location
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
        alembic_cfg = Config(cfg_path)
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.error("Error during Alembic migrations", exc_info=e)
    
    # Record startup time for metrics
    app.state.start_time = time.time()

# Health Check Endpoint
@app.get("/health", tags=["Monitoring"], summary="Perform a Health Check")
async def health_check():
    return {"status": "ok", "message": "Service is healthy"}

# Webhook Verification Endpoint
@app.get("/webhook", tags=["Webhook"], summary="Verify WhatsApp Webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
    if not VERIFY_TOKEN:
        logger.error("VERIFY_TOKEN environment variable not set.")
        raise HTTPException(status_code=500, detail="Webhook verification token not configured.")

    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        logger.info("Webhook verification successful.")
        return Response(content=hub_challenge, media_type="text/plain")
    else:
        logger.warning("Webhook verification failed", extra={
            "mode": hub_mode,
            "token_match": False
        })
        raise HTTPException(status_code=403, detail="Forbidden: Verification token mismatch.")

# Main Webhook Endpoint for Receiving Messages
@app.post("/webhook", tags=["Webhook"], summary="Receive WhatsApp Messages")
async def webhook_handler(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("Error parsing webhook payload", exc_info=e)
        raise HTTPException(status_code=400, detail="Invalid payload format.")

    logger.info("Received webhook payload", extra={"payload": payload})

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_id = metadata.get("phone_number_id")

            if not phone_id:
                logger.warning("Missing phone_number_id in webhook metadata.")
                continue

            tenant = tenant_by_phone_id(phone_id, db)
            if not tenant:
                logger.warning("Tenant not found for phone_id", extra={"phone_id": phone_id})
                continue

            for msg_data in value.get("messages", []):
                sender_phone = msg_data.get("from")
                text_content = msg_data.get("text", {}).get("body", "")
                whatsapp_msg_id = msg_data.get("id")

                if not all([sender_phone, text_content, whatsapp_msg_id]):
                    logger.warning("Incomplete message data received", extra={"msg_data": msg_data})
                    continue

                existing_message = db.query(Message).filter_by(wa_msg_id=whatsapp_msg_id).first()
                if existing_message:
                    logger.info("Skipping duplicate WhatsApp message ID", extra={"wa_msg_id": whatsapp_msg_id})
                    continue

                try:
                    db_message = Message(
                        tenant_id=tenant.id,
                        wa_msg_id=whatsapp_msg_id,
                        role="user",
                        text=text_content
                    )
                    db.add(db_message)
                    db.commit()
                    db.refresh(db_message)
                    logger.info("Saved incoming message", extra={
                        "message_id": db_message.id,
                        "wa_msg_id": whatsapp_msg_id,
                        "tenant_id": tenant.id
                    })
                except IntegrityError as e:
                    db.rollback()
                    logger.error("IntegrityError saving message", extra={"wa_msg_id": whatsapp_msg_id}, exc_info=e)
                    continue
                except Exception as e:
                    db.rollback()
                    logger.error("Error saving message", extra={"wa_msg_id": whatsapp_msg_id}, exc_info=e)
                    continue

                chat_history_query = (
                    db.query(Message)
                      .filter_by(tenant_id=tenant.id)
                      .order_by(Message.id.desc())
                      .limit(10)
                )
                history_messages = chat_history_query.all()[::-1]
                
                chat_for_ai = [
                    {"role": "system", "content": tenant.system_prompt}
                ] + [{"role": m.role, "content": m.text} for m in history_messages]

                # Process AI reply directly (Celery removed)
                await process_ai_reply(
                    tenant_id=tenant.id,
                    tenant_phone_id=tenant.phone_id,
                    tenant_wh_token=tenant.wh_token,
                    tenant_system_prompt=tenant.system_prompt,
                    chat_context=chat_for_ai,
                    sender_phone=sender_phone,
                    message_id=db_message.id
                )
                logger.info("Processed AI reply", extra={
                    "wa_msg_id": whatsapp_msg_id,
                    "tenant_id": tenant.id,
                    "message_id": db_message.id
                })

    return {"status": "received", "message": "Webhook processed successfully."}

async def process_ai_reply(
    tenant_id: int,
    tenant_phone_id: str,
    tenant_wh_token: str,
    tenant_system_prompt: str,
    chat_context: list,
    sender_phone: str,
    message_id: int
):
    """
    Process AI reply directly
    """
    try:
        # Get AI response
        response = await ai.chat.completions.create(
            model="gpt-4",
            messages=chat_context,
            temperature=0.7,
            max_tokens=500
        )
        ai_reply = response.choices[0].message.content
        
        # Save AI reply to database
        db = next(get_db())
        try:
            db_message = Message(
                tenant_id=tenant_id,
                role="assistant",
                text=ai_reply
            )
            db.add(db_message)
            db.commit()
            db.refresh(db_message)
        except Exception as e:
            db.rollback()
            logger.error("Error saving AI reply to database", exc_info=e)
        finally:
            db.close()
        
        # Send reply to WhatsApp
        await send_whatsapp_message(
            phone_id=tenant_phone_id,
            token=tenant_wh_token,
            recipient=sender_phone,
            message=ai_reply
        )
        
        return {"status": "success", "message_id": message_id}
    except Exception as e:
        logger.error("Error in process_ai_reply", exc_info=e)
        return {"status": "error", "error": str(e)}

async def send_whatsapp_message(phone_id: str, token: str, recipient: str, message: str):
    """
    Send WhatsApp message
    """
    try:
        url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": message}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("Error sending WhatsApp message", exc_info=e)
        return {"error": str(e)}

if __name__ == "__main__":
    import hypercorn
    from hypercorn.config import Config as HyperConfig
    
    config = HyperConfig()
    config.bind = [f"0.0.0.0:{int(os.getenv('PORT', '8000'))}"]
    config.use_reloader = True
    
    import asyncio
    asyncio.run(hypercorn.asyncio.serve(app, config))
