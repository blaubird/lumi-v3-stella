import time
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import FastAPI, Request, Response
from api.logging_utils import get_logger
from typing import Any, cast

# Initialize logger
logger = get_logger(__name__)

# Create a registry
registry = CollectorRegistry()

# Create metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total count of HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    registry=registry,
)

openai_api_calls_total = Counter(
    "openai_api_calls_total",
    "Total count of OpenAI API calls",
    ["model", "endpoint"],
    registry=registry,
)

openai_api_tokens_total = Counter(
    "openai_api_tokens_total",
    "Total count of tokens used in OpenAI API calls",
    ["model", "type"],
    registry=registry,
)

openai_api_duration_seconds = Histogram(
    "openai_api_duration_seconds",
    "OpenAI API call latency in seconds",
    ["model", "endpoint"],
    registry=registry,
)

active_tenants_gauge = Gauge(
    "active_tenants_count", "Number of active tenants", registry=registry
)

active_users_gauge = Gauge(
    "active_users_count",
    "Number of active users in the last 24 hours",
    registry=registry,
)


class PrometheusMiddleware:
    """
    Middleware for collecting HTTP request metrics
    """

    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, request: Request, call_next):
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Measure execution time
        duration = time.time() - start_time

        # Get endpoint (without query parameters)
        endpoint = request.url.path

        # Increment request counter
        http_requests_total.labels(
            method=request.method, endpoint=endpoint, status_code=response.status_code
        ).inc()

        # Record execution time
        http_request_duration_seconds.labels(
            method=request.method, endpoint=endpoint
        ).observe(duration)

        return response


def track_openai_call(model: str, endpoint: str):
    """
    Decorator for tracking OpenAI API calls
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            # Increment API call counter
            openai_api_calls_total.labels(model=model, endpoint=endpoint).inc()

            try:
                # Execute original function
                result = await func(*args, **kwargs)

                # If there's token information, record it
                if hasattr(result, "usage") and result.usage:
                    if hasattr(result.usage, "prompt_tokens"):
                        openai_api_tokens_total.labels(model=model, type="prompt").inc(
                            result.usage.prompt_tokens
                        )

                    if hasattr(result.usage, "completion_tokens"):
                        openai_api_tokens_total.labels(
                            model=model, type="completion"
                        ).inc(result.usage.completion_tokens)

                return result
            finally:
                # Record execution time
                duration = time.time() - start_time
                openai_api_duration_seconds.labels(
                    model=model, endpoint=endpoint
                ).observe(duration)

        return wrapper

    return decorator


def update_active_tenants(count: int):
    """
    Update active tenants metric
    """
    active_tenants_gauge.set(count)


def update_active_users(count: int):
    """
    Update active users metric
    """
    active_users_gauge.set(count)


def setup_metrics(app: FastAPI):
    """
    Setup metrics for FastAPI application

    Args:
        app: FastAPI application instance
    """
    # Add middleware for collecting HTTP request metrics
    app.add_middleware(cast(Any, PrometheusMiddleware))

    # Add endpoint for exporting metrics
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(
            content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST
        )

    # Initialize metrics at startup
    @app.on_event("startup")
    async def startup_metrics():
        # Initialize metrics that require database data
        # For example, number of active tenants
        pass

    return app
