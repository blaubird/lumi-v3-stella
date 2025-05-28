import os
import httpx
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from db import get_db
from models import Message
from openai import AsyncOpenAI

async def process_ai_reply(tenant_id: str, wa_msg_id: str, text: str):
    """
    Process AI reply asynchronously
    
    Args:
        tenant_id: Tenant ID
        wa_msg_id: WhatsApp message ID
        text: User message text
    """
    # Create a new database session
    db = next(get_db())
    
    try:
        # Get tenant information
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            print(f"Tenant not found: {tenant_id}")
            return
        
        # Get chat history
        chat_history_query = (
            db.query(Message)
            .filter_by(tenant_id=tenant_id)
            .order_by(Message.id.desc())
            .limit(10)
        )
        history_messages = chat_history_query.all()[::-1]
        
        # Prepare chat context
        chat_context = [
            {"role": "system", "content": tenant.system_prompt}
        ] + [{"role": m.role, "content": m.text} for m in history_messages]
        
        # Get AI response
        ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await ai.chat.completions.create(
            model="gpt-4",
            messages=chat_context,
            temperature=0.7,
            max_tokens=500
        )
        
        ai_reply = response.choices[0].message.content
        token_count = response.usage.total_tokens
        
        # Save AI reply to database
        db_message = Message(
            tenant_id=tenant_id,
            role="bot",
            text=ai_reply,
            tokens=token_count
        )
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        # Get RAG response if needed
        rag_response = await get_rag_response(tenant_id, text, db)
        
        # Send reply to WhatsApp
        await send_whatsapp_message(
            phone_id=tenant.phone_id,
            token=tenant.wh_token,
            recipient=wa_msg_id.split(':')[0],  # Extract phone number from wa_msg_id
            message=ai_reply
        )
        
    except Exception as e:
        print(f"Error in process_ai_reply: {str(e)}")
    finally:
        db.close()

async def get_rag_response(tenant_id: str, query: str, db: Session):
    """
    Get RAG response for a query
    
    Args:
        tenant_id: Tenant ID
        query: User query
        db: Database session
    
    Returns:
        str: RAG response
    """
    # Implementation of RAG response logic
    # This is a placeholder for the actual implementation
    return "RAG response placeholder"

async def send_whatsapp_message(phone_id: str, token: str, recipient: str, message: str):
    """
    Send WhatsApp message
    
    Args:
        phone_id: WhatsApp phone ID
        token: WhatsApp token
        recipient: Recipient phone number
        message: Message text
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
        print(f"Error sending WhatsApp message: {str(e)}")
        return {"error": str(e)}
