from fastapi import HTTPException, Header
from sqlalchemy.orm import Session
import os
from typing import Generator
from db import SessionLocal
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

def get_db() -> Generator[Session, None, None]:
    """
    Get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_admin_token(x_admin_token: str = Header(..., alias="X-Admin-Token")) -> str:
    """
    Verify admin API key
    
    Args:
        x_admin_token: Admin token from request header
        
    Returns:
        Admin token if valid
        
    Raises:
        HTTPException: If admin token is invalid
    """
    admin_token = os.getenv("X_ADMIN_TOKEN")
    if not admin_token:
        logger.error("X_ADMIN_TOKEN environment variable is not set")
        raise HTTPException(
            status_code=500,
            detail="Admin API key is not configured on the server"
        )
    
    if x_admin_token != admin_token:
        logger.warning("Invalid admin token provided", extra={"provided_token_length": len(x_admin_token) if x_admin_token else 0})
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info("Admin token verified successfully")
    return x_admin_token
