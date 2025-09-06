"""FastAPI application entry point."""

# ruff: noqa: E402
import os

from typing import Any, cast
from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from api.routers import (
    webhook,
    admin,
    rag,
    telegram_webhook,
    instagram_webhook,
)
from api.jobs.scheduler import init_scheduler
from api.monitoring import setup_metrics, add_health_check_endpoint
from api.logging_utils import configure_basic_logging, get_logger, request_context
from alembic.config import Config as AlembicConfig
from alembic import command
from pathlib import Path
from redis.asyncio import from_url as redis_from_url
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from api.config import settings  # Import settings
from api.schemas.common import ErrorResponse  # Import ErrorResponse schema

configure_basic_logging()
logger = get_logger(__name__)
logger.info("Starting application")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database engine
    logger.info("Initializing database engine")

    # Run Alembic migrations at startup
    logger.info("Running Alembic migrations...")
    root_path = Path(__file__).resolve().parent
    alembic_cfg = AlembicConfig(str(root_path / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(root_path / "alembic"))
    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations completed")

    # Setup metrics
    logger.info("Setting up metrics")
    setup_metrics(app)
    logger.info("Metrics setup complete")

    logger.info("Initializing Redis")
    app.state.redis = redis_from_url(
        settings.REDIS_URL,
        decode_responses=True,
        encoding="utf-8",
        max_connections=32,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
    )
    try:
        await app.state.redis.ping()
    except Exception as e:
        logger.warning("Redis ping failed", extra={"error": str(e)}, exc_info=True)

    # Add comprehensive health check endpoint
    add_health_check_endpoint(app)
    logger.info("Health check endpoint added")

    logger.info("Application startup finished")

    try:
        yield
    finally:
        await app.state.redis.aclose()

    # Optional shutdown logs could be added here


# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="WhatsApp AI Assistant API",
    version=settings.PROJECT_VERSION,
    docs_url=None,
    redoc_url="/docs",
    lifespan=lifespan,
)

# Add CORS middleware - MUST be before app startup
logger.info("Adding CORS middleware")

# Get allowed origins from environment variable, default to a safe empty list
# In a production environment, this should be explicitly set to your frontend domains.
allowed_origins = [
    origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
logger.info("CORS middleware added")

# Include routers - MUST be before app startup
logger.info("Registering routers")
app.include_router(webhook.router)
app.include_router(admin.router)
app.include_router(rag.router)
app.include_router(telegram_webhook.router)
app.include_router(instagram_webhook.router)
logger.info("Routers registered")

init_scheduler(app)

# Initialize logger
log = get_logger("api")


@app.get("/healthz", include_in_schema=False)
async def healthz(request: Request):
    redis_ok = True
    try:
        await request.app.state.redis.ping()
    except Exception as e:
        logger.warning("Health check degraded", extra={"error": str(e)})
        redis_ok = False
    status_str = "ok" if redis_ok else "degraded"
    return {"status": status_str, "redis": redis_ok}


@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def custom_swagger_ui_html():
    log.info("Swagger UI requested")
    return get_swagger_ui_html(
        openapi_url=app.openapi_url or "",
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
            "exception_type": exc.__class__.__name__,
        },
        exc_info=exc,
    )

    status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=exc.__class__.__name__,
            detail=str(exc),
            request_id=request_context.get().get("request_id", "unknown"),
        ).dict(),
    )


if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    # Configure Hypercorn
    config = Config()
    config.bind = [f'0.0.0.0:{int(os.getenv("PORT", "8080"))}']
    config.use_reloader = True

    # Configure Hypercorn logging
    config.accesslog = "-"  # Output access logs to stdout
    config.errorlog = "-"  # Output error logs to stdout
    config.loglevel = "INFO"

    log.info(f"Starting Hypercorn server on {config.bind}")

    # Run app with Hypercorn
    import asyncio

    asyncio.run(hypercorn.asyncio.serve(cast(Any, app), config))
