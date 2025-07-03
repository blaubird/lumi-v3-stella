from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from deps import get_db
from models import Tenant, FAQ
from schemas.rag import QueryRequest, QueryResponse
from ai import get_rag_response
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["RAG"])

@router.post("/tenants/{tenant_id:str}/queries", response_model=QueryResponse, status_code=201)
async def query_rag(
    tenant_id: str,
    query: QueryRequest,
    db: Session = Depends(get_db)
):
    """
    Query the RAG system with a question for a specific tenant
    """
    try:
        # Get tenant
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            logger.warning("Tenant not found for RAG query", extra={"tenant_id": tenant_id})
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Check for exact FAQ match first
        faq = db.query(FAQ).filter(
            func.lower(FAQ.question) == func.lower(query.query),
            FAQ.tenant_id == tenant_id
        ).first()
        
        if faq:
            logger.info("Exact FAQ match found", extra={
                "tenant_id": tenant_id,
                "faq_id": faq.id,
                "question": faq.question
            })
            
            # Return the exact match answer
            return {
                "answer": faq.answer,
                "sources": [faq],
                "token_count": len(faq.answer.split())  # Simple token count estimation
            }
        else:
            # Log for debugging
            logger.debug("No exact FAQ match found", extra={
                "tenant_id": tenant_id,
                "query": query.query
            })
        
        # Use the RAG implementation to get a response if no exact match
        response = await get_rag_response(
            db=db,
            tenant_id=tenant_id,
            user_query=query.query,
            system_prompt=tenant.system_prompt
        )
        
        logger.info("RAG query processed successfully", extra={"tenant_id": tenant_id})
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing RAG query", extra={"tenant_id": tenant_id, "error": str(e)}, exc_info=e)
        raise HTTPException(status_code=500, detail=f"Internal server error while processing query: {str(e)}")
