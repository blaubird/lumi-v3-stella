from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from db import get_db
from models import Tenant

def tenant_by_phone_id(phone_id: str, db: Session) -> Tenant:
    """
    Get tenant by phone_id
    
    Args:
        phone_id: WhatsApp phone number ID
        db: Database session
        
    Returns:
        Tenant object if found, None otherwise
    """
    return db.query(Tenant).filter(Tenant.phone_id == phone_id).first()
