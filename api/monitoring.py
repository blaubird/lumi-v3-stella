from prometheus_client import Counter, Histogram, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from typing import Optional

# Create a private registry
registry = CollectorRegistry()

# Create metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total count of HTTP requests',
    ['method', 'path'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'path'],
    registry=registry
)

def get_metrics() -> tuple[str, str]:
    """
    Returns the metrics in Prometheus format
    
    Returns:
        tuple: (metrics_content, content_type)
    """
    return generate_latest(registry).decode('utf-8'), CONTENT_TYPE_LATEST

def setup_monitoring(app):
    """
    Setup monitoring for FastAPI application
    
    Args:
        app: FastAPI application instance
    """
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware
    import time
    
    class PrometheusMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            method = request.method
            path = request.url.path
            
            # Skip metrics endpoint itself
            if path == "/metrics":
                return await call_next(request)
            
            start_time = time.time()
            
            # Process request
            response = await call_next(request)
            
            # Record metrics
            duration = time.time() - start_time
            http_requests_total.labels(method=method, path=path).inc()
            http_request_duration_seconds.labels(method=method, path=path).observe(duration)
            
            return response
    
    # Add middleware
    app.add_middleware(PrometheusMiddleware)
    
    # Add metrics endpoint
    from fastapi import APIRouter
    
    metrics_router = APIRouter()
    
    @metrics_router.get("/metrics", include_in_schema=False)
    async def metrics():
        metrics_data, content_type = get_metrics()
        return Response(content=metrics_data, media_type=content_type)
    
    # Import Response here to avoid circular imports
    from fastapi.responses import Response
    
    # Include router
    app.include_router(metrics_router)
    
    return app
