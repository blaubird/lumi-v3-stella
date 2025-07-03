import os
import logging
from fastapi import FastAPI, Request, BackgroundTasks, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
import sys
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from database import engine, Base
from routers import webhook, admin, rag
from tasks import process_ai_reply
from monitoring import setup_metrics, add_health_check_endpoint # Import add_health_check_endpoint
from logging_utils import get_logger, request_context
from alembic.config import Config as AlembicConfig
from alembic import command
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from config import settings # Import settings
from schemas.common import ErrorResponse # Import ErrorResponse schema

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

# Run Alembic migrations at startup
logging.info("Running Alembic migrations...")
alembic_cfg = AlembicConfig("alembic.ini")
command.upgrade(alembic_cfg, "head")
logging.info("Migrations completed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database engine
    logging.info("Initializing database engine")
    # Setup metrics
    logging.info("Setting up metrics")
    setup_metrics(app)
    logging.info("Metrics setup complete")
    
    # Add comprehensive health check endpoint
    add_health_check_endpoint(app)
    logging.info("Health check endpoint added")

    logging.info("Application startup finished")
    
    yield
    
    # Optional shutdown logs could be added here

# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="WhatsApp AI Assistant API",
    version=settings.PROJECT_VERSION,
    docs_url=None,
    redoc_url="/docs",
    lifespan=lifespan
)

# Add CORS middleware - MUST be before app startup
logging.info("Adding CORS middleware")

# Get allowed origins from environment variable, default to a safe empty list
# In a production environment, this should be explicitly set to your frontend domains.
allowed_origins = [origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = get_logger("exception_handler")
    logger.error(
        f"Unhandled exception: {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": exc.__class__.__name__
        },
        exc_info=exc
    )
    
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if hasattr(exc, "status_code"):
        status_code = exc.status_code

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=exc.__class__.__name__,
            detail=str(exc),
            request_id=request_context.get().get("request_id", "unknown")
        ).dict()
    )

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


