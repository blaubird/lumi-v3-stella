from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from models import Tenant
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
        
        # Use the RAG implementation to get a response
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
