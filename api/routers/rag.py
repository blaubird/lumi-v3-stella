from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from models import Tenant
from schemas.rag import QueryRequest, QueryResponse
from ai import get_rag_response

router = APIRouter(prefix="/rag", tags=["RAG"])

@router.post("/query", response_model=QueryResponse)
async def query_rag(
    query: QueryRequest,
    db: Session = Depends(get_db)
):
    """
    Query the RAG system with a question
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == query.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Use the RAG implementation to get a response
    response = await get_rag_response(
        db=db,
        tenant_id=query.tenant_id,
        user_query=query.query,
        system_prompt=tenant.system_prompt
    )
    
    return response
