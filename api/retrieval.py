"""FAQ retrieval helpers for RAG."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from config import settings
from logging_utils import get_logger
from models import FAQ

from ai import generate_embedding

logger = get_logger(__name__)


def _score_from_distance(distance: float | None) -> float:
    if distance is None or not isinstance(distance, (int, float)):
        return 0.0
    score = 1.0 - float(distance)
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _faq_similarity_stmt(embedding: List[float], tenant_id: str, limit: int) -> Select[Any]:
    return (
        select(
            FAQ.id,
            FAQ.question,
            FAQ.answer,
            FAQ.embedding.cosine_distance(list(embedding)).label("distance"),
        )
        .where(FAQ.tenant_id == tenant_id)
        .where(FAQ.embedding.isnot(None))
        .order_by(FAQ.embedding.cosine_distance(list(embedding)))
        .limit(limit)
    )


async def top_k_faqs(db: Session, tenant_id: str, query_text: str) -> List[Dict[str, Any]]:
    """Return the most relevant FAQ entries for a tenant."""

    if not query_text.strip():
        return []

    threshold = getattr(settings, "RAG_SIMILARITY_THRESHOLD", 0.0)
    top_k = max(1, getattr(settings, "RAG_TOP_K", 1))

    query_embedding = await generate_embedding(query_text)

    stmt = _faq_similarity_stmt(list(query_embedding), tenant_id, top_k * 2)

    def _load() -> List[Dict[str, Any]]:
        rows = db.execute(stmt).all()
        results: List[Dict[str, Any]] = []
        for row in rows:
            distance = getattr(row, "distance", None)
            if distance is None and isinstance(row, (list, tuple)) and len(row) > 3:
                distance = row[3]
            score = _score_from_distance(distance)
            if score < threshold:
                continue
            faq_id = getattr(row, "id", None)
            if faq_id is None and isinstance(row, (list, tuple)):
                faq_id = row[0]
            if faq_id is None:
                continue
            question = getattr(row, "question", "")
            if question == "" and isinstance(row, (list, tuple)) and len(row) > 1:
                question = row[1]
            answer = getattr(row, "answer", "")
            if answer == "" and isinstance(row, (list, tuple)) and len(row) > 2:
                answer = row[2]
            results.append(
                {
                    "id": int(faq_id),
                    "q": question,
                    "a": answer,
                    "score": score,
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]

    faqs = await asyncio.to_thread(_load)
    if faqs:
        logger.debug(
            "Retrieved FAQ matches",
            extra={
                "tenant_id": tenant_id,
                "count": len(faqs),
                "best_score": round(faqs[0]["score"], 4),
            },
        )
    else:
        logger.debug("No FAQ matches above threshold", extra={"tenant_id": tenant_id})
    return faqs
