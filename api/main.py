import os
import logging
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
import sys
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
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

# Configure root logger at INFO level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)

# Propagate root handlers to specific loggers
for name in ("api", "hypercorn.access", "hypercorn.error", "sqlalchemy"):
    logging.getLogger(name).handlers = logging.root.handlers
    logging.getLogger(name).propagate = True

logging.info("Starting application")

# Check required environment variables
required_env_vars = [
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "VERIFY_TOKEN",
    "WH_TOKEN",
    "WH_PHONE_ID",
    "DATABASE_URL",
    "X_ADMIN_TOKEN"
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    logging.error("Please set these environment variables in Railway and restart the application")
    sys.exit(1)

# Run Alembic migrations at startup
logging.info("Running Alembic migrations...")
alembic_cfg = AlembicConfig("alembic.ini")
command.upgrade(alembic_cfg, "head")
logging.info("Migrations completed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database engine
    logging.info("Initializing database engine")
    Base.metadata.create_all(bind=engine)
    
    # Setup metrics
    logging.info("Setting up metrics")
    setup_metrics(app)
    logging.info("Metrics setup complete")
    
    logging.info("Application startup finished")
    
    yield
    
    # Optional shutdown logs could be added here

# Create FastAPI app with lifespan
app = FastAPI(
    title="Lumi API",
    description="WhatsApp AI Assistant API",
    version="0.1.0",
    docs_url=None,
    redoc_url="/docs",
    lifespan=lifespan
)

# Add CORS middleware - MUST be before app startup
logging.info("Adding CORS middleware")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.info("CORS middleware added")

# Include routers - MUST be before app startup
logging.info("Registering routers")
app.include_router(webhook.router)
app.include_router(admin.router)
app.include_router(rag.router)
logging.info("Routers registered")

# Initialize logger
log = logging.getLogger("api")

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

# Removed duplicate @app.post("/webhook") handler as it's now handled by the router

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
