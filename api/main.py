from fastapi import FastAPI, Request, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
import os
import sys
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from db import get_db, engine, Base
from models import Tenant, Message
from routers import webhook, admin, rag
from tasks import process_ai_reply
from monitoring import setup_metrics
from logging_utils import get_logger
from alembic.config import Config as AlembicConfig
from alembic import command

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Propagate root handlers to specific loggers
for logger_name in ["api", "hypercorn", "sqlalchemy"]:
    logger = logging.getLogger(logger_name)
    logger.handlers = []
    logger.propagate = True

# Initialize logger
log = logging.getLogger("api")

# Create tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="Lumi API",
    description="WhatsApp AI Assistant API",
    version="0.1.0",
    docs_url=None,
    redoc_url="/docs"
)

@app.on_event("startup")
async def startup_event():
    # Apply migrations
    log.info("Applying Alembic migrations...")
    alembic_cfg = AlembicConfig("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    log.info("Migrations applied")
    
    # Setup metrics
    setup_metrics(app)
    log.info("Metrics setup complete")
    
    # CORS middleware is implicitly added
    log.info("CORS middleware added")
    
    # Routers are registered
    log.info("Routers registered")

# Setup metrics
setup_metrics(app)

# Include routers
app.include_router(webhook.router)
app.include_router(admin.router)
app.include_router(rag.router)

@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def custom_swagger_ui_html():
    log.info("Swagger UI requested")
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
    log.info("Health check requested")
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    WhatsApp webhook endpoint
    """
    log.info("Webhook request received")
    body = await request.json()
    
    # Process webhook
    if "object" in body and body["object"] == "whatsapp_business_account":
        log.info("Processing WhatsApp webhook", extra={"account_id": body.get("id")})
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
                            
                            log.info(
                                "Processing text message", 
                                extra={
                                    "msg_id": whatsapp_msg_id,
                                    "sender": sender_phone,
                                    "content_length": len(text_content)
                                }
                            )
                            
                            # Find tenant by phone ID
                            tenant = db.query(Tenant).filter(Tenant.phone_id == value.get("metadata", {}).get("phone_number_id")).first()
                            if not tenant:
                                log.warning("Tenant not found for phone ID", extra={"phone_id": value.get("metadata", {}).get("phone_number_id")})
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
                                log.info("Message saved to database", extra={"db_id": db_message.id})
                                
                                # Process AI reply in background
                                log.info("Scheduling AI reply processing")
                                background_tasks.add_task(
                                    process_ai_reply,
                                    tenant_id=tenant.id,
                                    wa_msg_id=whatsapp_msg_id,
                                    text=text_content
                                )
                                
                            except IntegrityError as e:
                                log.error("Database integrity error", exc_info=e)
                                db.rollback()
                                continue
                            except Exception as e:
                                log.error("Unexpected error processing message", exc_info=e)
                                db.rollback()
                                continue
    else:
        log.warning("Received non-WhatsApp webhook", extra={"object_type": body.get("object")})
    
    return {"status": "received"}

if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config
    
    # Configure Hypercorn
    config = Config()
    config.bind = [f"0.0.0.0:{int(os.getenv('PORT', '8080'))}"]
    config.use_reloader = True
    
    # Configure Hypercorn logging
    config.accesslog = "-"  # Output access logs to stdout
    config.errorlog = "-"   # Output error logs to stdout
    config.loglevel = "INFO"
    
    log.info(f"Starting Hypercorn server on {config.bind}")
    
    # Run app with Hypercorn
    import asyncio
    asyncio.run(hypercorn.asyncio.serve(app, config))
