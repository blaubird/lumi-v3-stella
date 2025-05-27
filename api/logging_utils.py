import logging
import json
import time
import traceback
from typing import Dict, Any, Optional, Callable
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from contextvars import ContextVar

# Context variable for storing request_id and other metadata
request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})

class StructuredLogger:
    """
    Class for structured JSON logging
    """
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _log(self, level: int, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        """Base logging method with context addition"""
        context = request_context.get()
        log_data = {
            "message": msg,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "level": logging.getLevelName(level),
        }
        
        # Add request context if available
        if context:
            log_data.update(context)
        
        # Add additional fields
        if extra:
            log_data.update(extra)
        
        # Add exception information if available
        if exc_info:
            if isinstance(exc_info, Exception):
                log_data["exception"] = {
                    "type": exc_info.__class__.__name__,
                    "message": str(exc_info),
                    "traceback": traceback.format_exc()
                }
            else:
                log_data["exc_info"] = True
        
        # Log as JSON
        self.logger.log(level, json.dumps(log_data), exc_info=exc_info if exc_info is True else None)
    
    def debug(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.DEBUG, msg, extra, exc_info)
    
    def info(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.INFO, msg, extra, exc_info)
    
    def warning(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.WARNING, msg, extra, exc_info)
    
    def error(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.ERROR, msg, extra, exc_info)
    
    def critical(self, msg: str, extra: Optional[Dict[str, Any]] = None, exc_info=None):
        self._log(logging.CRITICAL, msg, extra, exc_info)

def get_logger(name: str) -> StructuredLogger:
    """Factory method for getting a structured logger"""
    return StructuredLogger(name)

class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding request context to logs
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = f"{time.time()}-{id(request)}"
        
        # Create request context
        context = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
        }
        
        # Set context
        token = request_context.set(context)
        
        try:
            # Measure request execution time
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Add information about execution time and response status
            context = request_context.get()
            context.update({
                "status_code": response.status_code,
                "process_time_ms": round(process_time * 1000, 2)
            })
            
            # Add request ID header
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            # Log exception
            logger = get_logger("middleware")
            logger.error(
                f"Unhandled exception in request: {str(e)}",
                extra={"exception_type": e.__class__.__name__},
                exc_info=e
            )
            # Pass exception to global handler
            raise
        finally:
            # Reset context - only do this once in the finally block
            request_context.reset(token)

class GlobalExceptionHandler:
    """
    Global exception handler for FastAPI
    """
    def __init__(self, app: FastAPI):
        @app.exception_handler(Exception)
        async def handle_exception(request: Request, exc: Exception):
            # Get logger
            logger = get_logger("exception_handler")
            
            # Log exception
            logger.error(
                f"Unhandled exception: {str(exc)}",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "exception_type": exc.__class__.__name__
                },
                exc_info=exc
            )
            
            # Return error response
            from fastapi.responses import JSONResponse
            from fastapi import status
            
            # Determine status code based on exception type
            if hasattr(exc, "status_code"):
                status_code = exc.status_code
            else:
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            
            # Form response
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": exc.__class__.__name__,
                    "detail": str(exc),
                    "request_id": request_context.get().get("request_id", "unknown")
                }
            )

def setup_logging(app: FastAPI):
    """
    Setup logging and exception handling
    """
    # Add middleware for request context
    app.add_middleware(RequestContextMiddleware)
    
    # Add global exception handler
    GlobalExceptionHandler(app)
    
    # Configure basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',  # Use simple format as StructuredLogger does formatting
        handlers=[
            logging.StreamHandler(),  # Console output
        ]
    )
    
    # Return factory function for creating loggers
    return get_logger
