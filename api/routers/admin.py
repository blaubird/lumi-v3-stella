from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional
import os

from db import get_db
from models import Tenant, FAQ
from schemas.admin import TenantCreate, TenantResponse, TenantUpdate
from schemas.rag import FAQCreate, FAQResponse

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/tenants", response_model=List[TenantResponse])
def get_tenants(db: Session = Depends(get_db)):
    """Get all tenants"""
    tenants = db.query(Tenant).all()
    return tenants

@router.post("/tenants", response_model=TenantResponse)
def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant"""
    # Check if tenant with same phone_id already exists
    existing = db.query(Tenant).filter(Tenant.phone_id == tenant.phone_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tenant with this phone_id already exists")
    
    # Create new tenant
    db_tenant = Tenant(
        phone_id=tenant.phone_id,
        wh_token=tenant.wh_token,
        system_prompt=tenant.system_prompt
    )
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Get tenant by ID"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant(tenant_id: str, tenant_update: TenantUpdate, db: Session = Depends(get_db)):
    """Update tenant"""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Update fields
    for field, value in tenant_update.dict(exclude_unset=True).items():
        setattr(db_tenant, field, value)
    
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@router.delete("/tenants/{tenant_id}")
def delete_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Delete tenant"""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    db.delete(db_tenant)
    db.commit()
    return {"status": "success", "message": f"Tenant {tenant_id} deleted"}

# FAQ endpoints
@router.get("/tenants/{tenant_id}/faqs", response_model=List[FAQResponse])
def get_tenant_faqs(tenant_id: str, db: Session = Depends(get_db)):
    """Get all FAQs for a tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    faqs = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
    return faqs

@router.post("/tenants/{tenant_id}/faqs", response_model=FAQResponse)
def create_faq(tenant_id: str, faq: FAQCreate, db: Session = Depends(get_db)):
    """Create a new FAQ for a tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Create new FAQ
    db_faq = FAQ(
        tenant_id=tenant_id,
        question=faq.question,
        answer=faq.answer
    )
    db.add(db_faq)
    db.commit()
    db.refresh(db_faq)
    
    # Generate embedding asynchronously
    # This would typically be done in a background task
    # For now, we'll just return the FAQ without embedding
    
    return db_faq
