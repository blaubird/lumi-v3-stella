from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import json
import os
from db import get_db
from models import Tenant, Message, Usage
from services.whatsapp import WhatsAppService
from ai import get_rag_response
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhook"])

@router.get("/")
async def verify_webhook(
    mode: str = Query(None, alias="hub.mode"),
    challenge: str = Query(None, alias="hub.challenge"),
    verify_token: str = Query(None, alias="hub.verify_token")
):
    """
    Verify webhook endpoint for WhatsApp Business API using Meta's verification flow
    """
    logger.info("Webhook verification request received", extra={
        "mode": mode,
        "token_provided": bool(verify_token)
    })
    
    # Get expected token from environment
    expected_token = os.getenv("VERIFY_TOKEN", "lumi-verify-6969")
    
    # Check mode and token
    if mode == "subscribe" and verify_token == expected_token:
        logger.info("Webhook verified successfully")
        # Return raw challenge as plain text
        return Response(content=challenge, media_type="text/plain")
    
    # Invalid verification
    logger.warning("Invalid webhook verification attempt")
    return Response(content="Verification failed", status_code=403, media_type="text/plain")

@router.post("/")
async def webhook_handler(request: Request, db: Session = Depends(get_db)):
    """
    Handle webhook events from WhatsApp Business API
    """
    # Parse request body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    logger.debug("Webhook request received", extra={"body": body})
    
    # Process each entry
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_id = metadata.get("phone_number_id")
            
            # Find tenant by phone_id
            tenant = db.query(Tenant).filter(Tenant.phone_id == phone_id).first()
            if not tenant:
                logger.warning("Tenant not found for webhook", extra={"phone_id": phone_id})
                continue
            
            # Process messages
            for message in value.get("messages", []):
                if message.get("type") == "text":
                    await process_message(db, tenant, message)
    
    return {"status": "success"}

async def process_message(db: Session, tenant: Tenant, message: Dict[str, Any]):
    """
    Process a message from WhatsApp
    """
    # Extract message details
    message_id = message.get("id")
    from_number = message.get("from")
    text = message.get("text", {}).get("body", "")
    
    logger.info("Processing message", extra={
        "tenant_id": tenant.id,
        "message_id": message_id,
        "from": from_number,
        "text_length": len(text)
    })
    
    # Check if message already processed
    existing = db.query(Message).filter(Message.wa_msg_id == message_id).first()
    if existing:
        logger.info("Message already processed", extra={"message_id": message_id})
        return
    
    # Save user message
    user_message = Message(
        tenant_id=tenant.id,
        wa_msg_id=message_id,
        role="user",
        text=text
    )
    db.add(user_message)
    
    # Track inbound message usage (with 0 tokens as specified)
    usage_record = Usage(
        tenant_id=tenant.id,
        direction="inbound",
        tokens=0
    )
    db.add(usage_record)
    db.commit()
    
    # Generate response using RAG
    try:
        response = await get_rag_response(
            db=db,
            tenant_id=tenant.id,
            user_query=text,
            system_prompt=tenant.system_prompt
        )
        
        answer = response["answer"]
        token_count = response.get("token_count", 0)  # Get token count from response
        
        # Save bot message
        bot_message = Message(
            tenant_id=tenant.id,
            role="bot",
            text=answer,
            tokens=token_count
        )
        db.add(bot_message)
        
        # Track outbound message usage with actual token count
        outbound_usage = Usage(
            tenant_id=tenant.id,
            direction="outbound",
            tokens=token_count
        )
        db.add(outbound_usage)
        db.commit()
        
        # Send response via WhatsApp
        whatsapp = WhatsAppService(
            phone_id=tenant.phone_id,
            token=tenant.wh_token
        )
        await whatsapp.send_message(to=from_number, text=answer)
        
        logger.info("Response sent", extra={
            "tenant_id": tenant.id,
            "to": from_number,
            "response_length": len(answer),
            "token_count": token_count
        })
    except Exception as e:
        logger.error("Error processing message", extra={
            "tenant_id": tenant.id,
            "message_id": message_id,
            "error": str(e)
        }, exc_info=e)
