from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import os
from typing import Generator
from db import SessionLocal
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

# API key header for admin authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_db() -> Generator[Session, None, None]:
    """
    Get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_admin_token(api_key: str = Security(API_KEY_HEADER)) -> str:
    """
    Verify admin API key
    
    Args:
        api_key: API key from request header
        
    Returns:
        API key if valid
        
    Raises:
        HTTPException: If API key is invalid
    """
    admin_token = os.getenv("X_ADMIN_TOKEN")
    if not admin_token:
        logger.error("X_ADMIN_TOKEN environment variable is not set")
        raise HTTPException(
            status_code=500,
            detail="Admin API key is not configured on the server"
        )
    
    if api_key != admin_token:
        logger.warning("Invalid admin API key provided", extra={"provided_key_length": len(api_key) if api_key else 0})
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    logger.info("Admin API key verified successfully")
    return api_key
