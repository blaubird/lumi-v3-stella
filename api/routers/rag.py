from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from models import Tenant
from schemas.rag import QueryRequest, QueryResponse
from ai import get_rag_response

router = APIRouter(prefix="/rag", tags=["RAG"])

@router.post("/tenants/{tenant_id}/queries", response_model=QueryResponse)
async def query_rag(
    tenant_id: str,
    query: QueryRequest,
    db: Session = Depends(get_db)
):
    """
    Query the RAG system with a question for a specific tenant
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Use the RAG implementation to get a response
    response = await get_rag_response(
        db=db,
        tenant_id=tenant_id,
        user_query=query.query,
        system_prompt=tenant.system_prompt
    )
    
    return response
