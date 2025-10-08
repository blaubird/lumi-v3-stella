from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from deps import get_db
from database import engine
from models import Tenant, Base
from deps import verify_admin_token
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Scripts"])


@router.post("/setup-db", dependencies=[Depends(verify_admin_token)])
def setup_database(drop_existing: bool = False, db: Session = Depends(get_db)):
    """
    Set up the database schema

    Args:
        drop_existing: Whether to drop existing tables before creating new ones
    """
    try:
        if drop_existing:
            logger.info("Dropping existing tables...")
            Base.metadata.drop_all(bind=engine)

        logger.info("Creating tables...")
        Base.metadata.create_all(bind=engine)

        logger.info("Database setup complete")
        return {"status": "success", "message": "Database setup complete"}
    except Exception as e:
        logger.error(f"Database setup failed: {str(e)}", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Database setup failed: {str(e)}")


@router.post("/create-tenant", dependencies=[Depends(verify_admin_token)])
def create_tenant(
    phone_id: str,
    wh_token: Optional[str] = None,
    system_prompt: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Create a new tenant in the database

    Args:
        phone_id: WhatsApp phone ID
        wh_token: Webhook verification token (generated if not provided)
        system_prompt: System prompt for the AI (default provided if not specified)
    """
    # Generate webhook token if not provided
    if not wh_token:
        wh_token = str(uuid.uuid4())

    # Set default system prompt if not provided
    if not system_prompt:
        system_prompt = "You are a helpful assistant that answers questions based on the provided knowledge base."

    try:
        # Check if tenant with same phone_id already exists
        existing = db.query(Tenant).filter(Tenant.phone_id == phone_id).first()
        if existing:
            logger.warning(
                f"Tenant with phone_id {phone_id} already exists",
                extra={"tenant_id": existing.id},
            )
            return {
                "status": "exists",
                "message": f"Tenant with phone_id {phone_id} already exists",
                "tenant_id": existing.id,
            }

        # Create new tenant
        tenant = Tenant(
            phone_id=phone_id, wh_token=wh_token, system_prompt=system_prompt
        )

        # Add to database
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        logger.info(
            "Tenant created successfully",
            extra={"tenant_id": tenant.id, "phone_id": tenant.phone_id},
        )

        return {
            "status": "success",
            "message": "Tenant created successfully",
            "tenant": {
                "id": tenant.id,
                "phone_id": tenant.phone_id,
                "wh_token": tenant.wh_token,
            },
        }
    except Exception as e:
        logger.error(f"Tenant creation failed: {str(e)}", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Tenant creation failed: {str(e)}")
