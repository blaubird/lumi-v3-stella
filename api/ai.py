"""AI orchestration for Lumi."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, cast

import tiktoken
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from redis.asyncio import Redis
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from cache import get_cached_tenant
from config import settings
from logging_utils import get_logger
from models import FAQ, Usage

logger = get_logger(__name__)

_TOP_K = 6
_SIMILARITY_THRESHOLD = 0.75
_CONTEXT_TOKEN_BUDGET = 1200
_MAX_CHUNK_TOKENS = 400
_BACKOFF_SCHEDULE = (0.5, 1.5, 3.0)
_SYSTEM_PROMPT_TEMPLATE = (
    "You are Lumi, a concise multilingual assistant for SMB customer support. "
    "Answer strictly based on the provided FAQ context. If the answer is not in "
    "the context, say you don’t know and propose to connect a human. Use language: {lang}. "
    "Be brief, accurate, and friendly."
)
_GUARDRAILS_PROMPT = (
    "If the user asks outside business scope or risky content, redirect politely. "
    "Do not invent facts. Prefer short paragraphs and bullet points."
)
_RAG_PREFIX_TEMPLATE = (
    "FAQ context (summaries):\n{summaries}\n"
    'User question: "{question}"\n'
    "— Answer in {lang}. If insufficient context, say you don’t know."
)
_FALLBACK_LANG_MAP: Dict[str, str] = {
    "fr": "Je ne peux pas répondre pour le moment. Un membre de l’équipe vous contactera bientôt.",
    "en": "I’m unable to answer right now. A teammate will get back to you shortly.",
}

_client: AsyncOpenAI | None = None
_client_lock = asyncio.Lock()


@dataclass(slots=True)
class FAQChunk:
    faq_id: int
    question: str
    answer: str
    score: float

    def to_used_chunk(self) -> Dict[str, Any]:
        return {
            "id": self.faq_id,
            "score": round(self.score, 4),
            "q": _safe_snippet(self.question),
            "a": _safe_snippet(self.answer),
        }


def _is_ai_enabled() -> bool:
    raw = getattr(settings, "AI_ENABLE", None)
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    return str(raw).lower() in {"1", "true", "yes", "on"}


async def _get_client() -> AsyncOpenAI:
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is not None:
            return _client
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is missing")
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=getattr(settings, "OPENAI_BASE_URL", None),
        )
        return _client


def _resolve_language(lang: str) -> str:
    if not lang:
        return "en"
    return lang.lower()


def _fallback_text(lang: str) -> str:
    lang_key = _resolve_language(lang)[:2]
    return _FALLBACK_LANG_MAP.get(
        lang_key,
        _FALLBACK_LANG_MAP["en"],
    )


def _insufficient_context_text(lang: str) -> str:
    resolved = _resolve_language(lang)[:2]
    if resolved == "fr":
        return (
            "Je ne dispose pas d’informations suffisantes dans la base FAQ. "
            "Souhaitez-vous qu’un membre de l’équipe prenne le relais ?"
        )
    return (
        "I don’t have enough information in the FAQ to answer. "
        "Shall I connect you with a human teammate?"
    )


def _safe_snippet(text: str, max_length: int = 280) -> str:
    text = text.strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"


def _score_from_distance(distance: float | None) -> float:
    if distance is None or not math.isfinite(distance):
        return 0.0
    return max(0.0, min(1.0, 1.0 - distance))


async def generate_embedding(text: str) -> List[float]:
    client = await _get_client()
    start = time.perf_counter()
    response = await client.embeddings.create(
        input=text,
        model=settings.OPENAI_EMBEDDING_MODEL,
        timeout=getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 30.0),
    )
    duration = time.perf_counter() - start
    logger.info(
        "Generated embedding",
        extra={"duration_ms": int(duration * 1000), "tokens": len(text.split())},
    )
    return response.data[0].embedding


async def backfill_missing_faq_embeddings(
    db: Session, tenant_id: str | None = None
) -> int:
    stmt = select(FAQ).where(FAQ.embedding.is_(None))
    if tenant_id:
        stmt = stmt.where(FAQ.tenant_id == tenant_id)
    rows: List[FAQ] = list(db.execute(stmt).scalars())
    if not rows:
        return 0
    client = await _get_client()
    updated = 0
    for faq in rows:
        try:
            response = await client.embeddings.create(
                input=f"{faq.question}\n\n{faq.answer}",
                model=settings.OPENAI_EMBEDDING_MODEL,
                timeout=getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 30.0),
            )
        except Exception as exc:  # pragma: no cover - backfill utility
            logger.error(
                "Embedding backfill failed",
                extra={"faq_id": faq.id, "tenant_id": faq.tenant_id, "error": str(exc)},
            )
            continue
        setattr(faq, "embedding", response.data[0].embedding)
        db.add(faq)
        updated += 1
    db.commit()
    return updated


def _similar_faqs_stmt(embedding: Sequence[float], tenant_id: str) -> Select[Any]:
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
        .limit(_TOP_K)
    )


def _token_encoding(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception as exc:  # pragma: no cover - defensive guard
            raise RuntimeError(
                "tiktoken encoding not available; please upgrade tiktoken"
            ) from exc


def _truncate_to_token_limit(text: str, limit: int, encoding: tiktoken.Encoding) -> str:
    tokens = encoding.encode(text)
    if len(tokens) <= limit:
        return text
    truncated = encoding.decode(tokens[:limit])
    return _safe_snippet(truncated, len(truncated))


def _pack_context(
    chunks: Iterable[FAQChunk],
    encoding: tiktoken.Encoding,
    token_budget: int,
) -> tuple[str, List[FAQChunk]]:
    included: List[FAQChunk] = []
    lines: List[str] = []
    used_tokens = 0
    for index, chunk in enumerate(chunks, start=1):
        summary = _format_chunk_summary(index, chunk, encoding)
        token_count = len(encoding.encode(summary))
        if used_tokens + token_count > token_budget:
            if not included and token_budget > 0:
                summary = _trim_summary_to_budget(summary, token_budget, encoding)
                token_count = len(encoding.encode(summary))
                if token_count <= token_budget:
                    included.append(chunk)
                    lines.append(summary)
                    used_tokens += token_count
            break
        included.append(chunk)
        lines.append(summary)
        used_tokens += token_count
    if not lines:
        return "(no relevant context)", []
    return "\n".join(lines), included


def _format_chunk_summary(
    index: int, chunk: FAQChunk, encoding: tiktoken.Encoding
) -> str:
    question = _truncate_to_token_limit(
        chunk.question, _MAX_CHUNK_TOKENS // 2, encoding
    )
    answer = _truncate_to_token_limit(chunk.answer, _MAX_CHUNK_TOKENS, encoding)
    return f"{index}. Q: {question}\n   A: {answer}"


def _trim_summary_to_budget(
    summary: str, budget: int, encoding: tiktoken.Encoding
) -> str:
    tokens = encoding.encode(summary)
    if len(tokens) <= budget:
        return summary
    trimmed = encoding.decode(tokens[:budget])
    return _safe_snippet(trimmed, len(trimmed))


def _message_text(message: ChatCompletionMessageParam) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: List[str] = []
        for part in content:
            if isinstance(part, dict):
                text_fragment = part.get("text")
                if isinstance(text_fragment, str):
                    fragments.append(text_fragment)
        return " ".join(fragments)
    return ""


async def _retrieve_similar_chunks(
    db: Session, tenant_id: str, query_embedding: Sequence[float]
) -> List[FAQChunk]:
    stmt = _similar_faqs_stmt(query_embedding, tenant_id)
    rows = db.execute(stmt).all()
    chunks: List[FAQChunk] = []
    for row in rows:
        distance = row.distance if hasattr(row, "distance") else row[3]
        score = _score_from_distance(distance)
        if score < _SIMILARITY_THRESHOLD:
            continue
        faq_id = row.id if hasattr(row, "id") else row[0]
        question = row.question if hasattr(row, "question") else row[1]
        answer = row.answer if hasattr(row, "answer") else row[2]
        chunks.append(
            FAQChunk(faq_id=faq_id, question=question, answer=answer, score=score)
        )
    return chunks


async def _call_openai(
    messages: Sequence[ChatCompletionMessageParam],
) -> tuple[str, int, int, str]:
    client = await _get_client()
    for attempt, delay in enumerate(_BACKOFF_SCHEDULE, start=1):
        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=list(messages),
                temperature=getattr(settings, "AI_TEMPERATURE", 0.2),
                max_tokens=settings.AI_MAX_TOKENS_COMPLETION,
                timeout=getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 30.0),
            )
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            logger.warning(
                "Transient OpenAI error",
                extra={"attempt": attempt, "error": str(exc)},
            )
            if attempt == len(_BACKOFF_SCHEDULE):
                raise
            await asyncio.sleep(delay)
            continue
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            if status and 500 <= status < 600:
                logger.warning(
                    "OpenAI server error",
                    extra={"attempt": attempt, "status": status},
                )
                if attempt == len(_BACKOFF_SCHEDULE):
                    raise
                await asyncio.sleep(delay)
                continue
            raise
        else:
            choice = response.choices[0]
            text = choice.message.content or ""
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else len(text.split())
            model = response.model
            return text.strip(), prompt_tokens, completion_tokens, model
    raise RuntimeError("OpenAI retries exhausted")


def _persist_usage(
    db: Session,
    tenant_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    trace_id: str | None,
) -> None:
    record = Usage(
        tenant_id=tenant_id,
        direction="outbound",
        tokens=total_tokens,
        msg_ts=datetime.now(timezone.utc),
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        trace_id=trace_id,
    )
    db.add(record)
    db.commit()


def _build_messages(
    lang: str,
    context: str,
    question: str,
    tenant_prompt: Optional[str] = None,
) -> List[ChatCompletionMessageParam]:
    resolved_lang = _resolve_language(lang)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(lang=resolved_lang)
    rag_prompt = _RAG_PREFIX_TEMPLATE.format(
        summaries=context,
        question=question,
        lang=resolved_lang,
    )
    messages: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": _GUARDRAILS_PROMPT},
    ]
    if tenant_prompt:
        messages.append({"role": "system", "content": tenant_prompt})
    messages.append({"role": "user", "content": rag_prompt})
    return messages


def _build_used_chunks(chunks: Sequence[FAQChunk]) -> List[Dict[str, Any]]:
    return [chunk.to_used_chunk() for chunk in chunks]


async def get_rag_response(
    tenant_id: str,
    user_text: str,
    lang: str,
    db: Session,
    redis: Redis,
    trace_id: str | None = None,
) -> Dict[str, Any]:
    if not _is_ai_enabled():
        text = _fallback_text(lang)
        return {
            "text": text,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": settings.OPENAI_MODEL,
            "used_chunks": [],
        }

    if not user_text:
        return {
            "text": _insufficient_context_text(lang),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": settings.OPENAI_MODEL,
            "used_chunks": [],
        }

    tenant = await get_cached_tenant(redis, db, tenant_id)
    if tenant is None:
        raise ValueError(f"Unknown tenant {tenant_id}")

    encoding = _token_encoding(settings.OPENAI_MODEL)

    try:
        query_embedding = await generate_embedding(user_text)
    except Exception as exc:
        logger.error(
            "Failed to generate query embedding",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        text = _fallback_text(lang)
        return {
            "text": text,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": settings.OPENAI_MODEL,
            "used_chunks": [],
        }

    chunks = await _retrieve_similar_chunks(db, tenant_id, query_embedding)
    context_text, used_chunks = _pack_context(chunks, encoding, _CONTEXT_TOKEN_BUDGET)
    tenant_prompt = None
    if isinstance(tenant, dict):
        tenant_prompt = cast(Optional[str], tenant.get("system_prompt"))
    messages = _build_messages(lang, context_text, user_text, tenant_prompt)

    if not used_chunks:
        text = _insufficient_context_text(lang)
        prompt_tokens_estimate = sum(
            len(encoding.encode(_message_text(message))) for message in messages
        )
        return {
            "text": text,
            "prompt_tokens": prompt_tokens_estimate,
            "completion_tokens": 0,
            "total_tokens": prompt_tokens_estimate,
            "model": settings.OPENAI_MODEL,
            "used_chunks": [],
        }

    try:
        completion_text, prompt_tokens, completion_tokens, model = await _call_openai(
            messages
        )
    except Exception as exc:
        logger.error(
            "OpenAI completion failed",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        text = _fallback_text(lang)
        return {
            "text": text,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": settings.OPENAI_MODEL,
            "used_chunks": _build_used_chunks(used_chunks),
        }

    total_tokens = prompt_tokens + completion_tokens
    try:
        _persist_usage(
            db=db,
            tenant_id=tenant_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            trace_id=trace_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to persist usage",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )

    return {
        "text": completion_text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "model": model,
        "used_chunks": _build_used_chunks(used_chunks),
    }
