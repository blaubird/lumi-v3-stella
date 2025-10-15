"""AI orchestration for Lumi."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

import tiktoken
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy.orm import Session
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_chain,
    wait_fixed,
)

from config import settings
from logging_utils import get_logger
from models import FAQ, Usage
from services.tenant_config import get_tenant_config

logger = get_logger(__name__)

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
_FALLBACK_LANG_MAP: Dict[str, str] = {
    "fr": "Je ne peux pas répondre pour le moment. Un membre de l’équipe vous contactera bientôt.",
    "en": "I’m unable to answer right now. A teammate will get back to you shortly.",
}

_BACKOFF_SCHEDULE = wait_chain(
    wait_fixed(0.5),
    wait_fixed(1.5),
    wait_fixed(3.0),
)
_RETRYABLE_ERRORS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
)

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


class _RetryableAPIError(Exception):
    """Wrapper to mark retryable API errors for tenacity."""


def _context_token_budget() -> int:
    budget = getattr(settings, "RAG_CONTEXT_TOKEN_BUDGET", 1200)
    return max(0, int(budget))


def _max_chunk_tokens() -> int:
    value = getattr(settings, "RAG_MAX_CHUNK_TOKENS", 400)
    return max(1, int(value))


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
    return _FALLBACK_LANG_MAP.get(lang_key, _FALLBACK_LANG_MAP["en"])


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
    stmt = db.query(FAQ).filter(FAQ.embedding.is_(None))
    if tenant_id:
        stmt = stmt.filter(FAQ.tenant_id == tenant_id)
    rows: List[FAQ] = list(stmt)
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
        faq.embedding = response.data[0].embedding
        db.add(faq)
        updated += 1
    db.commit()
    return updated


def _token_encoding(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _truncate_to_token_limit(text: str, limit: int, encoding: tiktoken.Encoding) -> str:
    tokens = encoding.encode(text)
    if len(tokens) <= limit:
        return text
    truncated = encoding.decode(tokens[:limit])
    return _safe_snippet(truncated, len(truncated))


def _format_chunk_summary(
    index: int, chunk: FAQChunk, encoding: tiktoken.Encoding
) -> str:
    half_budget = _max_chunk_tokens() // 2
    question = _truncate_to_token_limit(chunk.question, half_budget, encoding)
    answer = _truncate_to_token_limit(chunk.answer, _max_chunk_tokens(), encoding)
    return f"{index}. Q: {question}\n   A: {answer}"


def _trim_summary_to_budget(
    summary: str, budget: int, encoding: tiktoken.Encoding
) -> str:
    tokens = encoding.encode(summary)
    if len(tokens) <= budget:
        return summary
    trimmed = encoding.decode(tokens[:budget])
    return _safe_snippet(trimmed, len(trimmed))


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


def _count_prompt_tokens(
    messages: Sequence[ChatCompletionMessageParam], encoding: tiktoken.Encoding
) -> int:
    return sum(len(encoding.encode(_message_text(message))) for message in messages)


def _build_messages(
    lang: str,
    context: str,
    question: str,
    tenant_prompt: Optional[str] = None,
) -> List[ChatCompletionMessageParam]:
    resolved_lang = _resolve_language(lang)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(lang=resolved_lang)
    rag_prompt = (
        f"FAQ context:\n{context}\n"
        f'User question: "{question}"\n'
        f"— Answer in {resolved_lang}. If insufficient context, say you don’t know."
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


async def _log_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "OpenAI chat attempt failed",
        extra={
            "attempt": retry_state.attempt_number,
            "error": str(exc) if exc else None,
        },
    )


async def _call_chat_completion(
    messages: Sequence[ChatCompletionMessageParam],
) -> tuple[str, int, int, str]:
    client = await _get_client()
    retrying = AsyncRetrying(
        retry=retry_if_exception_type(_RETRYABLE_ERRORS + (_RetryableAPIError,)),
        wait=_BACKOFF_SCHEDULE,
        stop=stop_after_attempt(4),
        before_sleep=_log_retry,
        reraise=True,
    )
    async for attempt in retrying:
        with attempt:
            try:
                response = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=list(messages),
                    temperature=getattr(settings, "AI_TEMPERATURE", 0.2),
                    max_tokens=settings.AI_MAX_TOKENS_COMPLETION,
                    timeout=getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 30.0),
                )
            except APIError as exc:
                status = getattr(exc, "status_code", None)
                if status and 500 <= status < 600:
                    raise _RetryableAPIError(str(exc)) from exc
                raise
            choice = response.choices[0]
            text = (choice.message.content or "").strip()
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else len(text.split())
            model = response.model or settings.OPENAI_MODEL
            return text, prompt_tokens, completion_tokens, model
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
        trace_id=trace_id or str(uuid4()),
    )
    db.add(record)
    try:
        db.commit()
    except Exception as exc:  # pragma: no cover - commit failures rare
        db.rollback()
        logger.error(
            "Failed to persist usage",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )


def _persist_zero_usage(db: Session, tenant_id: str, trace_id: str | None) -> None:
    _persist_usage(
        db=db,
        tenant_id=tenant_id,
        model="",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        trace_id=trace_id,
    )


async def get_rag_response(
    tenant_id: str,
    user_text: str,
    lang: str,
    db: Session,
    redis: Any,
    trace_id: str | None = None,
) -> Dict[str, Any]:
    if not _is_ai_enabled():
        return {
            "text": _fallback_text(lang),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": "",
            "used_chunks": [],
        }

    question = user_text.strip()
    if not question:
        return {
            "text": _insufficient_context_text(lang),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": "",
            "used_chunks": [],
        }

    tenant = await get_tenant_config(db, tenant_id)
    if tenant is None:
        raise ValueError(f"Unknown tenant {tenant_id}")

    encoding = _token_encoding(settings.OPENAI_MODEL)

    try:
        import retrieval
    except ImportError as exc:  # pragma: no cover - packaging issue
        raise RuntimeError("retrieval module unavailable") from exc

    try:
        faq_matches = await retrieval.top_k_faqs(db, tenant_id, question)
    except Exception as exc:
        logger.error(
            "FAQ retrieval failed",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        _persist_zero_usage(db, tenant_id, trace_id)
        return {
            "text": _fallback_text(lang),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": "",
            "used_chunks": [],
        }

    chunks = [
        FAQChunk(
            faq_id=int(item["id"]),
            question=str(item["q"]),
            answer=str(item["a"]),
            score=float(item["score"]),
        )
        for item in faq_matches
    ]

    context_text, included_chunks = _pack_context(
        chunks, encoding, _context_token_budget()
    )

    tenant_prompt = None
    if isinstance(tenant, dict):
        tenant_prompt = tenant.get("system_prompt")

    messages = _build_messages(lang, context_text, question, tenant_prompt)
    prompt_tokens_estimate = _count_prompt_tokens(messages, encoding)

    if redis is not None and trace_id and included_chunks:
        try:
            from redis_client import ns_key

            cache_key = ns_key(f"rag:ctx:{trace_id}")
        except Exception:
            cache_key = f"rag:ctx:{trace_id}"
        try:
            payload = json.dumps(
                [
                    {"id": chunk.faq_id, "score": round(chunk.score, 4)}
                    for chunk in included_chunks
                ],
                separators=(",", ":"),
            )
            await redis.setex(cache_key, 900, payload)
        except Exception as exc:
            logger.debug(
                "Failed to cache RAG context",
                extra={"trace_id": trace_id, "error": str(exc)},
            )

    try:
        completion_text, prompt_tokens, completion_tokens, model = (
            await _call_chat_completion(messages)
        )
    except APIError as exc:
        logger.error(
            "OpenAI completion failed",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        _persist_zero_usage(db, tenant_id, trace_id)
        return {
            "text": _fallback_text(lang),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": "",
            "used_chunks": _build_used_chunks(included_chunks),
        }
    except Exception as exc:
        logger.error(
            "OpenAI completion failed",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        _persist_zero_usage(db, tenant_id, trace_id)
        return {
            "text": _fallback_text(lang),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": "",
            "used_chunks": _build_used_chunks(included_chunks),
        }

    if prompt_tokens == 0:
        prompt_tokens = prompt_tokens_estimate
    total_tokens = prompt_tokens + completion_tokens

    _persist_usage(
        db=db,
        tenant_id=tenant_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        trace_id=trace_id,
    )

    return {
        "text": completion_text or _insufficient_context_text(lang),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "model": model,
        "used_chunks": _build_used_chunks(included_chunks),
    }


__all__ = [
    "FAQChunk",
    "backfill_missing_faq_embeddings",
    "generate_embedding",
    "get_rag_response",
]
