from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any, cast
from deps import get_db
from models import Tenant, FAQ
from schemas.rag import QueryRequest, QueryResponse, UsedChunk
from ai import get_rag_response
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["RAG"])


@router.post(
    "/tenants/{tenant_id:str}/queries", response_model=QueryResponse, status_code=201
)
async def query_rag(
    tenant_id: str,
    query: QueryRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Query the RAG system with a question for a specific tenant
    """
    try:
        # Get tenant
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            logger.warning(
                "Tenant not found for RAG query", extra={"tenant_id": tenant_id}
            )
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Check for exact FAQ match first
        faq = (
            db.query(FAQ)
            .filter(
                func.lower(FAQ.question) == func.lower(query.query),
                FAQ.tenant_id == tenant_id,
            )
            .first()
        )

        if faq:
            logger.info(
                "Exact FAQ match found",
                extra={
                    "tenant_id": tenant_id,
                    "faq_id": faq.id,
                    "question": faq.question,
                },
            )

            # Return the exact match answer
            answer_text = cast(str, faq.answer)
            return QueryResponse(
                text=answer_text,
                prompt_tokens=0,
                completion_tokens=len(answer_text.split()),
                total_tokens=len(answer_text.split()),
                model="faq-direct",
                used_chunks=[
                    UsedChunk(
                        id=cast(int, faq.id),
                        score=1.0,
                        q=cast(str, faq.question),
                        a=answer_text,
                    )
                ],
            )
        else:
            # Log for debugging
            logger.debug(
                "No exact FAQ match found",
                extra={"tenant_id": tenant_id, "query": query.query},
            )

            # Use the RAG implementation to get a response if no exact match
            redis = cast(Any, request.app.state.redis)
            response = await get_rag_response(
                tenant_id=tenant_id,
                user_text=query.query,
                lang=query.lang or "en",
                db=db,
                redis=redis,
            )

        logger.info("RAG query processed successfully", extra={"tenant_id": tenant_id})
        return QueryResponse(**response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error processing RAG query",
            extra={"tenant_id": tenant_id, "error": str(e)},
            exc_info=e,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while processing query: {str(e)}",
        )
