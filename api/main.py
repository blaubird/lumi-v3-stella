import os
from fastapi import FastAPI, Request, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from db import get_db, engine, Base
from models import Tenant, Message
from routers import admin
from tasks import process_ai_reply
from monitoring import setup_metrics

# Create FastAPI app
app = FastAPI(
    title="Lumi API",
    description="Lumi WhatsApp API",
    version="3.0.0",
    docs_url=None
)

# Setup metrics
setup_metrics(app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(admin.router)

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    WhatsApp webhook endpoint
    """
    body = await request.json()
    
    # Process webhook
    if "object" in body and body["object"] == "whatsapp_business_account":
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "messages":
                    value = change.get("value", {})
                    
                    # Process messages
                    for message in value.get("messages", []):
                        if message.get("type") == "text":
                            # Extract message details
                            whatsapp_msg_id = message.get("id")
                            sender_phone = message.get("from")
                            text_content = message.get("text", {}).get("body", "")
                            
                            # Find tenant by phone ID
                            tenant = db.query(Tenant).filter(Tenant.phone_id == value.get("metadata", {}).get("phone_number_id")).first()
                            if not tenant:
                                continue
                            
                            # Save message
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
                                
                                # Process AI reply in background
                                background_tasks.add_task(
                                    process_ai_reply,
                                    tenant_id=tenant.id,
                                    wa_msg_id=whatsapp_msg_id,
                                    text=text_content
                                )
                                
                            except IntegrityError:
                                db.rollback()
                                continue
                            except Exception:
                                db.rollback()
                                continue
    
    return {"status": "received"}

if __name__ == "__main__":
    import uvicorn
    
    # Run app
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=True
    )
