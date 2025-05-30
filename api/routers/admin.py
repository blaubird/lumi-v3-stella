from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from db import get_db
from models import Tenant, FAQ
from schemas.admin import TenantCreate, TenantResponse, TenantUpdate, FAQCreate, FAQResponse
from schemas.bulk_import import BulkFAQImportRequest, BulkFAQImportResponse
from deps import verify_admin_token
from ai import generate_embedding
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# === Tenant Management ===
@router.get("/tenants", response_model=List[TenantResponse], dependencies=[Depends(verify_admin_token)])
def get_tenants(db: Session = Depends(get_db)):
    """Get all tenants"""
    tenants = db.query(Tenant).all()
    logger.info("Retrieved all tenants", extra={"count": len(tenants)})
    return tenants

@router.post("/tenants", response_model=TenantResponse, dependencies=[Depends(verify_admin_token)])
def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant"""
    # Check if tenant with same phone_id already exists
    existing = db.query(Tenant).filter(Tenant.phone_id == tenant.phone_id).first()
    if existing:
        logger.warning("Tenant with phone_id already exists", extra={"phone_id": tenant.phone_id})
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
    
    logger.info("Tenant created", extra={"tenant_id": db_tenant.id, "phone_id": db_tenant.phone_id})
    return db_tenant

@router.get("/tenants/{tenant_id}", response_model=TenantResponse, dependencies=[Depends(verify_admin_token)])
def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Get tenant by ID"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    logger.info("Tenant retrieved", extra={"tenant_id": tenant_id})
    return tenant

@router.put("/tenants/{tenant_id}", response_model=TenantResponse, dependencies=[Depends(verify_admin_token)])
def update_tenant(tenant_id: str, tenant_update: TenantUpdate, db: Session = Depends(get_db)):
    """Update tenant"""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        logger.warning("Tenant not found for update", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Update fields
    update_data = tenant_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_tenant, field, value)
    
    db.commit()
    db.refresh(db_tenant)
    
    logger.info("Tenant updated", extra={
        "tenant_id": tenant_id,
        "updated_fields": list(update_data.keys())
    })
    return db_tenant

@router.delete("/tenants/{tenant_id}", dependencies=[Depends(verify_admin_token)])
def delete_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Delete tenant"""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        logger.warning("Tenant not found for deletion", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    db.delete(db_tenant)
    db.commit()
    
    logger.info("Tenant deleted", extra={"tenant_id": tenant_id})
    return {"status": "success", "message": f"Tenant {tenant_id} deleted"}

# === FAQ Management ===
@router.get("/tenants/{tenant_id}/faqs", response_model=List[FAQResponse], dependencies=[Depends(verify_admin_token)])
def get_tenant_faqs(tenant_id: str, db: Session = Depends(get_db)):
    """Get all FAQs for a tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found for FAQ retrieval", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    faqs = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
    logger.info("Retrieved FAQs for tenant", extra={"tenant_id": tenant_id, "count": len(faqs)})
    return faqs

@router.post("/tenants/{tenant_id}/faqs", response_model=FAQResponse, dependencies=[Depends(verify_admin_token)])
async def create_faq(
    tenant_id: str, 
    faq: FAQCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new FAQ for a tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found for FAQ creation", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Create new FAQ without embedding initially
    db_faq = FAQ(
        tenant_id=tenant_id,
        question=faq.question,
        answer=faq.answer
    )
    db.add(db_faq)
    db.commit()
    db.refresh(db_faq)
    
    # Generate embedding in background
    background_tasks.add_task(
        generate_embedding_for_faq,
        db=db,
        faq_id=db_faq.id,
        tenant_id=tenant_id,
        question=faq.question,
        answer=faq.answer
    )
    
    logger.info("FAQ created", extra={
        "faq_id": db_faq.id,
        "tenant_id": tenant_id,
        "question_length": len(faq.question),
        "answer_length": len(faq.answer)
    })
    
    return db_faq

@router.post("/tenants/{tenant_id}/faqs/bulk", response_model=BulkFAQImportResponse, dependencies=[Depends(verify_admin_token)])
async def bulk_import_faq(
    tenant_id: str,
    import_data: BulkFAQImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Bulk import multiple FAQ entries for a tenant
    """
    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found for bulk FAQ import", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail=f"Tenant with id {tenant_id} not found.")
    
    successful_items = 0
    failed_items = 0
    errors = []
    
    # Process each FAQ item
    for item in import_data.items:
        try:
            # Create FAQ without embedding initially
            db_faq = FAQ(
                tenant_id=tenant_id,
                question=item.question,
                answer=item.answer
            )
            db.add(db_faq)
            db.commit()
            db.refresh(db_faq)
            
            # Schedule embedding generation in background
            background_tasks.add_task(
                generate_embedding_for_faq,
                db=db,
                faq_id=db_faq.id,
                tenant_id=tenant_id,
                question=item.question,
                answer=item.answer
            )
            
            successful_items += 1
        except Exception as e:
            failed_items += 1
            errors.append(f"Error processing FAQ: {str(e)}")
            logger.error("Error in bulk FAQ import", extra={
                "tenant_id": tenant_id,
                "question": item.question[:50],
                "error": str(e)
            }, exc_info=e)
    
    logger.info("Bulk FAQ import completed", extra={
        "tenant_id": tenant_id,
        "total_items": len(import_data.items),
        "successful_items": successful_items,
        "failed_items": failed_items
    })
    
    return {
        "total_items": len(import_data.items),
        "successful_items": successful_items,
        "failed_items": failed_items,
        "errors": errors if errors else None
    }

async def generate_embedding_for_faq(db: Session, faq_id: int, tenant_id: str, question: str, answer: str):
    """
    Generate embedding for a FAQ and update the database
    """
    try:
        # Get the FAQ from the database
        faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
        if not faq:
            logger.error("FAQ not found for embedding generation", extra={
                "faq_id": faq_id,
                "tenant_id": tenant_id
            })
            return
        
        # Generate embedding
        content_to_embed = f"Question: {question} Answer: {answer}"
        embedding = await generate_embedding(content_to_embed)
        
        if embedding is None:
            logger.error("Failed to generate embedding for FAQ", extra={
                "faq_id": faq_id,
                "tenant_id": tenant_id
            })
            return
        
        # Update FAQ with embedding
        faq.embedding = embedding
        db.commit()
        
        logger.info("Embedding generated for FAQ", extra={
            "faq_id": faq_id,
            "tenant_id": tenant_id,
            "embedding_dimensions": len(embedding)
        })
    except Exception as e:
        logger.error("Error generating embedding for FAQ", extra={
            "faq_id": faq_id,
            "tenant_id": tenant_id,
            "error": str(e)
        }, exc_info=e)
