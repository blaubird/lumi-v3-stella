from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from db import get_db
from models import Tenant, Message, FAQ, Usage
from schemas.admin import (
    TenantCreate, TenantUpdate, TenantResponse, 
    FAQCreate, FAQResponse, MessageResponse,
    BulkFAQImportRequest, BulkFAQImportResponse,
    UsageStatsResponse
)
from deps import verify_admin_token
from ai import generate_embedding
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/tenants", response_model=List[TenantResponse], dependencies=[Depends(verify_admin_token)])
async def get_tenants(db: Session = Depends(get_db)):
    """Get all tenants"""
    tenants = db.query(Tenant).all()
    logger.info("Retrieved all tenants", extra={"count": len(tenants)})
    return tenants

@router.post("/tenants", response_model=TenantResponse, dependencies=[Depends(verify_admin_token)])
async def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant"""
    # Check if phone_id already exists
    existing = db.query(Tenant).filter(Tenant.phone_id == tenant.phone_id).first()
    if existing:
        logger.warning("Tenant creation failed: phone_id already exists", extra={"phone_id": tenant.phone_id})
        raise HTTPException(status_code=400, detail="Phone ID already exists")
    
    # Generate a unique ID for the tenant
    import uuid
    tenant_id = str(uuid.uuid4())
    
    # Create new tenant
    db_tenant = Tenant(
        id=tenant_id,
        phone_id=tenant.phone_id,
        wh_token=tenant.wh_token,
        system_prompt=tenant.system_prompt
    )
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    
    logger.info("Tenant created", extra={"tenant_id": tenant_id})
    return db_tenant

@router.get("/tenants/{tenant_id}", response_model=TenantResponse, dependencies=[Depends(verify_admin_token)])
async def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Get a specific tenant by ID"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    logger.info("Retrieved tenant", extra={"tenant_id": tenant_id})
    return tenant

@router.put("/tenants/{tenant_id}", response_model=TenantResponse, dependencies=[Depends(verify_admin_token)])
async def update_tenant(tenant_id: str, tenant: TenantUpdate, db: Session = Depends(get_db)):
    """Update a tenant"""
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not db_tenant:
        logger.warning("Tenant not found for update", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Update fields if provided
    if tenant.phone_id is not None:
        # Check if new phone_id already exists
        if tenant.phone_id != db_tenant.phone_id:
            existing = db.query(Tenant).filter(Tenant.phone_id == tenant.phone_id).first()
            if existing:
                logger.warning("Tenant update failed: phone_id already exists", extra={"phone_id": tenant.phone_id})
                raise HTTPException(status_code=400, detail="Phone ID already exists")
        db_tenant.phone_id = tenant.phone_id
    
    if tenant.wh_token is not None:
        db_tenant.wh_token = tenant.wh_token
    
    if tenant.system_prompt is not None:
        db_tenant.system_prompt = tenant.system_prompt
    
    db.commit()
    db.refresh(db_tenant)
    
    logger.info("Tenant updated", extra={"tenant_id": tenant_id})
    return db_tenant

@router.delete("/tenants/{tenant_id}", dependencies=[Depends(verify_admin_token)])
async def delete_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Delete a tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found for deletion", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Delete tenant
    db.delete(tenant)
    db.commit()
    
    logger.info("Tenant deleted", extra={"tenant_id": tenant_id})
    return {"status": "success", "message": f"Tenant {tenant_id} deleted"}

@router.get("/tenants/{tenant_id}/messages", response_model=List[MessageResponse], dependencies=[Depends(verify_admin_token)])
async def get_tenant_messages(
    tenant_id: str, 
    limit: int = 50, 
    offset: int = 0, 
    db: Session = Depends(get_db)
):
    """Get messages for a specific tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found for message retrieval", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    messages = db.query(Message).filter(
        Message.tenant_id == tenant_id
    ).order_by(
        Message.ts.desc()
    ).offset(offset).limit(limit).all()
    
    logger.info("Retrieved messages for tenant", extra={"tenant_id": tenant_id, "count": len(messages)})
    return messages

@router.get("/tenants/{tenant_id}/faqs", response_model=List[FAQResponse], dependencies=[Depends(verify_admin_token)])
async def get_tenant_faqs(tenant_id: str, db: Session = Depends(get_db)):
    """Get FAQs for a specific tenant"""
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

@router.get("/tenants/{tenant_id}/usage", response_model=UsageStatsResponse, dependencies=[Depends(verify_admin_token)])
async def get_tenant_usage(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get usage statistics for a specific tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        logger.warning("Tenant not found for usage retrieval", extra={"tenant_id": tenant_id})
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Get paginated usage items
    usage_items = db.query(Usage).filter(
        Usage.tenant_id == tenant_id
    ).order_by(
        Usage.msg_ts.desc()
    ).offset(offset).limit(limit).all()
    
    # Get total inbound tokens
    total_inbound = db.query(func.sum(Usage.tokens)).filter(
        Usage.tenant_id == tenant_id,
        Usage.direction == "inbound"
    ).scalar() or 0
    
    # Get total outbound tokens
    total_outbound = db.query(func.sum(Usage.tokens)).filter(
        Usage.tenant_id == tenant_id,
        Usage.direction == "outbound"
    ).scalar() or 0
    
    logger.info("Retrieved usage for tenant", extra={
        "tenant_id": tenant_id,
        "items_count": len(usage_items),
        "total_inbound": total_inbound,
        "total_outbound": total_outbound
    })
    
    return {
        "items": usage_items,
        "total_inbound_tokens": total_inbound,
        "total_outbound_tokens": total_outbound
    }

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
