"""Backfill FAQ embeddings using the configured OpenAI embedding model."""

from __future__ import annotations

import asyncio
import os
from typing import List, Optional

from sqlalchemy.orm import Session

from api.ai import generate_embedding
from api.database import SessionLocal
from api.logging_utils import get_logger
from api.models import FAQ

logger = get_logger(__name__)


async def _fetch_batch(
    db: Session, tenant_id: Optional[str], batch_size: int
) -> List[FAQ]:
    def _load() -> List[FAQ]:
        query = db.query(FAQ).filter(FAQ.embedding.is_(None))
        if tenant_id:
            query = query.filter(FAQ.tenant_id == tenant_id)
        return query.order_by(FAQ.id).limit(batch_size).all()

    return await asyncio.to_thread(_load)


async def _process_batch(db: Session, batch: List[FAQ]) -> int:
    updated = 0
    for faq in batch:
        try:
            embedding = await generate_embedding(f"{faq.question}\n\n{faq.answer}")
        except Exception as exc:  # pragma: no cover - network errors nondeterministic
            logger.error(
                "Failed to generate embedding",
                extra={"faq_id": faq.id, "tenant_id": faq.tenant_id, "error": str(exc)},
            )
            continue
        faq.embedding = embedding
        db.add(faq)
        updated += 1
    if updated:
        try:
            db.commit()
        except Exception as exc:  # pragma: no cover - commit errors rare
            db.rollback()
            logger.error("Failed to commit embedding batch", extra={"error": str(exc)})
            return 0
    return updated


async def main() -> None:
    tenant_id = os.getenv("FAQ_BACKFILL_TENANT_ID")
    batch_size = int(os.getenv("FAQ_BACKFILL_BATCH_SIZE", "25"))
    pause_seconds = float(os.getenv("FAQ_BACKFILL_SLEEP_SECONDS", "0"))

    logger.info(
        "Starting FAQ embedding backfill",
        extra={
            "tenant_id": tenant_id,
            "batch_size": batch_size,
            "pause_seconds": pause_seconds,
        },
    )

    db = SessionLocal()
    total_updated = 0
    try:
        while True:
            batch = await _fetch_batch(db, tenant_id, batch_size)
            if not batch:
                break
            updated = await _process_batch(db, batch)
            total_updated += updated
            logger.info(
                "Backfill batch processed",
                extra={"batch_size": len(batch), "updated": updated},
            )
            if pause_seconds > 0:
                await asyncio.sleep(pause_seconds)
    finally:
        db.close()

    logger.info("Backfill completed", extra={"updated_total": total_updated})


if __name__ == "__main__":
    asyncio.run(main())
