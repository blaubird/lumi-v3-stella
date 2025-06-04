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
async def get_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get all tenants with pagination and ordering"""
    try:
        logger.info("Starting tenant retrieval", extra={"page": page, "page_size": page_size})
        
        offset = (page - 1) * page_size
        
        # Use only id for ordering to avoid any potential issues with timestamps
        query = db.query(Tenant).order_by(Tenant.id.desc())
        
        # Log the query being executed
        logger.info(f"Executing query: {str(query)}")
        
        tenants = query.offset(offset).limit(page_size).all()
        
        # Log successful retrieval
        logger.info("Successfully retrieved tenants", extra={"page": page, "page_size": page_size, "count": len(tenants)})
        
        return tenants
    except Exception as e:
        logger.error("Error retrieving tenants", extra={"error": str(e), "page": page, "page_size": page_size}, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error while retrieving tenants: {str(e)}")


@router.post("/tenants", response_model=TenantResponse, status_code=201, dependencies=[Depends(verify_admin_token)])
async def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant"""
    try:
        # Check if phone_id already exists
        existing = db.query(Tenant).filter(Tenant.phone_id == tenant.phone_id).first()
        if existing:
            logger.warning("Tenant creation failed: phone_id already exists", extra={"phone_id": tenant.phone_id})
            raise HTTPException(status_code=400, detail="Phone ID already exists")
        
        # Use the ID from the request instead of generating a new UUID
        tenant_id = tenant.id
        
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating tenant", extra={"error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error while creating tenant: {str(e)}")


@router.get("/tenants/{tenant_id:str}", response_model=TenantResponse, dependencies=[Depends(verify_admin_token)])
async def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Get a specific tenant by ID"""
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            logger.warning("Tenant not found", extra={"tenant_id": tenant_id})
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        logger.info("Retrieved tenant", extra={"tenant_id": tenant_id})
        return tenant
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving tenant", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error while retrieving tenant: {str(e)}")

@router.put("/tenants/{tenant_id:str}", response_model=TenantResponse, dependencies=[Depends(verify_admin_token)])
async def update_tenant(tenant_id: str, tenant: TenantUpdate, db: Session = Depends(get_db)):
    """Update a tenant"""
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating tenant", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error while updating tenant: {str(e)}")

@router.delete("/tenants/{tenant_id:str}", dependencies=[Depends(verify_admin_token)])
async def delete_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Delete a tenant"""
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            logger.warning("Tenant not found for deletion", extra={"tenant_id": tenant_id})
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Delete the tenant - child records will be deleted automatically via CASCADE
        db.delete(tenant)
        db.commit()
        
        logger.info("Tenant deleted", extra={"tenant_id": tenant_id})
        return {"status": "success", "message": f"Tenant {tenant_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting tenant", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error while deleting tenant: {str(e)}")


@router.get("/tenants/{tenant_id:str}/messages", response_model=List[MessageResponse], dependencies=[Depends(verify_admin_token)])
async def get_tenant_messages(
    tenant_id: str, 
    limit: int = 50, 
    offset: int = 0, 
    db: Session = Depends(get_db)
):
    """Get messages for a specific tenant"""
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving tenant messages", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error while retrieving tenant messages: {str(e)}")

@router.get("/tenants/{tenant_id:str}/faqs", response_model=List[FAQResponse], dependencies=[Depends(verify_admin_token)])
async def get_tenant_faqs(tenant_id: str, db: Session = Depends(get_db)):
    """Get FAQs for a specific tenant"""
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            logger.warning("Tenant not found for FAQ retrieval", extra={"tenant_id": tenant_id})
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        faqs = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
        
        logger.info("Retrieved FAQs for tenant", extra={"tenant_id": tenant_id, "count": len(faqs)})
        return faqs
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving tenant FAQs", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error while retrieving tenant FAQs: {str(e)}")

@router.post("/tenants/{tenant_id:str}/faqs", response_model=FAQResponse, status_code=201, dependencies=[Depends(verify_admin_token)])
async def create_faq(
    tenant_id: str, 
    faq: FAQCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new FAQ for a tenant"""
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            logger.warning("Tenant not found for FAQ creation", extra={"tenant_id": tenant_id})
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        try:
            # Create new FAQ without embedding initially
            db_faq = FAQ(
                tenant_id=tenant_id,
                question=faq.question,
                answer=faq.answer
            )
            db.add(db_faq)
            db.commit()
            db.refresh(db_faq)
        except Exception as db_error:
            logger.error("Database error creating FAQ", extra={
                "tenant_id": tenant_id,
                "error": str(db_error)
            }, exc_info=db_error)
            raise HTTPException(status_code=400, detail=f"Error creating FAQ: {str(db_error)}")
        
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating FAQ", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error while creating FAQ: {str(e)}")

@router.get("/tenants/{tenant_id:str}/usage", response_model=UsageStatsResponse, dependencies=[Depends(verify_admin_token)])
async def get_tenant_usage(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get usage statistics for a specific tenant"""
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving tenant usage", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error while retrieving tenant usage: {str(e)}")

@router.post("/tenants/{tenant_id:str}/faqs/bulk", response_model=BulkFAQImportResponse, status_code=201, dependencies=[Depends(verify_admin_token)])
async def bulk_import_faq(
    tenant_id: str,
    import_data: BulkFAQImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Bulk import multiple FAQ entries for a tenant
    """
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in bulk FAQ import", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error during bulk FAQ import: {str(e)}")

async def generate_embedding_for_faq(db: Session, faq_id: int, tenant_id: str, question: str, answer: str):
    """Background task to generate embedding for FAQ"""
    try:
        # Get the FAQ from the database
        faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
        if not faq:
            logger.error("FAQ not found for embedding generation", extra={"faq_id": faq_id, "tenant_id": tenant_id})
            return
        
        # Generate embedding
        embedding = await generate_embedding(question, answer)
        
        # Update FAQ with embedding
        faq.embedding = embedding
        db.commit()
        
        logger.info("Embedding generated for FAQ", extra={"faq_id": faq_id, "tenant_id": tenant_id})
    except Exception as e:
        logger.error("Error generating embedding for FAQ", extra={
            "faq_id": faq_id,
            "tenant_id": tenant_id,
            "error": str(e)
        }, exc_info=e)
