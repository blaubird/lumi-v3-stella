from prometheus_client import Counter, Histogram, CollectorRegistry
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from api.database import SessionLocal
from api.logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

# Create a private registry
registry = CollectorRegistry()

# Create metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total count of HTTP requests",
    ["method", "endpoint"],
    registry=registry,
)

REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    registry=registry,
)

CACHE_HIT = Counter(
    "cache_hit_total",
    "Total cache hits",
    ["bucket"],
    registry=registry,
)

CACHE_MISS = Counter(
    "cache_miss_total",
    "Total cache misses",
    ["bucket"],
    registry=registry,
)


def setup_metrics(app: FastAPI):
    """
    Setup metrics for FastAPI application
    """
    from prometheus_fastapi_instrumentator import Instrumentator
    from prometheus_fastapi_instrumentator.metrics import requests, latency

    # Create instrumentator
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=[".*admin.*", "/metrics"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="inprogress",
        inprogress_labels=True,
    )

    # Add custom metrics using the supported method
    instrumentator.add(requests())
    instrumentator.add(latency())

    # Instrument app and expose metrics endpoint
    instrumentator.instrument(app).expose(app, include_in_schema=False)

    return app


# Dependency to get DB session for health check
def get_db_health_check():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_health_check_endpoint(app: FastAPI):
    """
    Adds a comprehensive health check endpoint to the FastAPI application.
    This health check verifies database connectivity.
    """

    @app.get(
        "/health",
        summary="Health Check",
        response_description="Application health status",
    )
    async def health_check(db: Session = Depends(get_db_health_check)):
        logger.info("Health check requested")
        status = {"status": "ok", "dependencies": {}}

        # Database connectivity check
        try:
            db.execute(text("SELECT 1"))
            status["dependencies"]["database"] = "ok"
        except Exception as e:
            logger.error(
                "Database health check failed", extra={"error": str(e)}, exc_info=True
            )
            status["status"] = "degraded"
            status["dependencies"]["database"] = f"error: {str(e)}"
            raise HTTPException(status_code=500, detail="Database connection failed")

        # Add other service checks here if needed (e.g., OpenAI, WhatsApp API)
        # For example, to check OpenAI API:
        # try:
        #     from ai import client as openai_client
        #     if openai_client:
        #         await openai_client.models.list() # A simple API call
        #         status["dependencies"]["openai_api"] = "ok"
        #     else:
        #         status["dependencies"]["openai_api"] = "error: client not initialized"
        #         status["status"] = "degraded"
        # except Exception as e:
        #     logger.error("OpenAI API health check failed", extra={"error": str(e)}, exc_info=True)
        #     status["status"] = "degraded"
        #     status["dependencies"]["openai_api"] = f"error: {str(e)}"
        #     raise HTTPException(status_code=500, detail="OpenAI API connection failed")

        logger.info("Health check completed", extra=status)
        return status
