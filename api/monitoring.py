from prometheus_client import Counter, Histogram, CollectorRegistry
from fastapi import FastAPI

# Create a private registry
registry = CollectorRegistry()

# Create metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total count of HTTP requests',
    ['method', 'endpoint'],
    registry=registry
)

REQUEST_LATENCY = Histogram(
    'http_request_latency_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    registry=registry
)

def setup_metrics(app: FastAPI):
    """
    Setup metrics for FastAPI application
    
    Args:
        app: FastAPI application instance
    """
    from prometheus_fastapi_instrumentator import Instrumentator
    
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
    
    # Add custom metrics
    instrumentator.add(
        metrics_namespace="api",
        metrics_subsystem="",
        latency_target=REQUEST_LATENCY,
        counter_target=REQUEST_COUNT,
    )
    
    # Instrument app
    instrumentator.instrument(app).expose(app, include_in_schema=False)
    
    return app

