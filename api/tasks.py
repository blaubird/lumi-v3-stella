import os
import json
import httpx
from celery import Celery
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from db import SessionLocal
from models import Message

# Configure Celery
celery_app = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
)

@celery_app.task
def process_ai_reply(
    tenant_id: int,
    tenant_phone_id: str,
    tenant_wh_token: str,
    tenant_system_prompt: str,
    chat_context: list,
    sender_phone: str,
    message_id: int
):
    """
    Process AI reply asynchronously
    
    Args:
        tenant_id: Tenant ID
        tenant_phone_id: WhatsApp phone ID
        tenant_wh_token: WhatsApp token
        tenant_system_prompt: System prompt
        chat_context: Chat context for AI
        sender_phone: Sender phone number
        message_id: Message ID in database
    """
    try:
        # Import here to avoid circular imports
        from openai import AsyncOpenAI
        import asyncio
        
        # Create OpenAI client
        ai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Define async function to get AI response
        async def get_ai_response():
            try:
                response = await ai.chat.completions.create(
                    model="gpt-4",
                    messages=chat_context,
                    temperature=0.7,
                    max_tokens=500
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"Error getting AI response: {str(e)}")
                return "I'm sorry, I couldn't process your request at the moment."
        
        # Run async function
        ai_reply = asyncio.run(get_ai_response())
        
        # Save AI reply to database
        db = SessionLocal()
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
            print(f"Error saving AI reply to database: {str(e)}")
        finally:
            db.close()
        
        # Send reply to WhatsApp
        send_whatsapp_message(
            phone_id=tenant_phone_id,
            token=tenant_wh_token,
            recipient=sender_phone,
            message=ai_reply
        )
        
        return {"status": "success", "message_id": message_id}
    except Exception as e:
        print(f"Error in process_ai_reply: {str(e)}")
        return {"status": "error", "error": str(e)}

def send_whatsapp_message(phone_id: str, token: str, recipient: str, message: str):
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
        
        response = httpx.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error sending WhatsApp message: {str(e)}")
        return {"error": str(e)}
