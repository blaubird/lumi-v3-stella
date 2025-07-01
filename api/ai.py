import os
import logging
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from sqlalchemy.orm import Session
from models import FAQ
from logging_utils import get_logger

# Initialize logger
logger = get_logger(__name__)
# Add specific logger for AI operations
logger_ai = logging.getLogger("api.ai")

# Initialize OpenAI client globally to ensure a single instance
# This helps prevent memory leaks and resource exhaustion from creating multiple clients.
client = None
try:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = AsyncOpenAI(api_key=api_key)
    else:
        logger.warning("OPENAI_API_KEY not found. OpenAI client not initialized.")
except Exception as e:
    logger.error(
        "Failed to initialize OpenAI client", extra={"error": str(e)}, exc_info=e
    )

# Model names
EMBEDDING_MODEL_NAME = "text-embedding-ada-002"
MODEL_NAME = os.getenv(
    "OPENAI_MODEL", "ft:gpt-4.1-nano-2025-04-14:luminiteq:flora:Bdezn8Rp"
)


def track_openai_call(model: str, endpoint: str):
    """
    Decorator to track OpenAI API calls
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = __import__("time").time()

            try:
                # Call the original function
                result = await func(*args, **kwargs)

                # Calculate duration
                duration = __import__("time").time() - start_time

                # Log the API call
                logger.info(
                    "OpenAI API call completed",
                    extra={
                        "model": model,
                        "endpoint": endpoint,
                        "duration_seconds": round(duration, 2),
                    },
                )

                return result
            except Exception as e:
                # Log error
                logger.error(
                    "OpenAI API call failed",
                    extra={"model": model, "endpoint": endpoint, "error": str(e)},
                    exc_info=e,
                )
                raise

        return wrapper

    return decorator


async def generate_embedding(text_content: str) -> Optional[List[float]]:
    """
    Generate an embedding for the given text content using OpenAI's API
    """
    if client is None:
        logger.error("OpenAI client is not initialized. Cannot generate embedding.")
        return None

    try:
        logger.info(
            "Generating embedding for text",
            extra={
                "text_preview": (
                    text_content[:50] + "..."
                    if len(text_content) > 50
                    else text_content
                ),
                "text_length": len(text_content),
            },
        )

        response = await client.embeddings.create(
            model=EMBEDDING_MODEL_NAME, input=text_content
        )
        embedding = response.data[0].embedding

        # Log successful result
        logger.info(
            "Successfully generated embedding",
            extra={"embedding_dimensions": len(embedding)},
        )
        return embedding
    except Exception as e:
        # Structured logging of errors
        logger.error(
            "Error during embedding generation",
            extra={"error_type": type(e).__name__, "error_details": str(e)},
            exc_info=e,
        )

        return None


async def find_relevant_faqs(
    db: Session, tenant_id: str, user_query: str, top_k: int = 3
) -> List[FAQ]:
    """
    Finds the top_k most relevant FAQs from the database for a specific tenant
    based on the user query, using cosine similarity with pgvector.
    
    Optimization: Ensure a proper index is created on the 'embedding' column
    in the FAQ table for efficient similarity search.
    Example: CREATE INDEX ON faqs USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);
    (This is a database-level optimization, not directly in Python code)
    """
    if client is None:
        logger.error("OpenAI client is not initialized. Cannot find relevant FAQs.")
        raise RuntimeError("OpenAI client is not initialized.")
    if not user_query:
        logger.warning("Empty user query provided.")
        return []
    query_embedding = await generate_embedding(user_query)
    if query_embedding is None:
        logger.warning(
            "Could not generate embedding for query", extra={"query": user_query}
        )
        return []
    try:
        # Using SQLAlchemy's ORM with pgvector's cosine_distance
        # Lower cosine_distance means higher similarity
        relevant_faqs = (
            db.query(FAQ)
            .filter(FAQ.tenant_id == tenant_id)
            .filter(FAQ.embedding.isnot(None))  # Ensure embedding is not null
            .order_by(FAQ.embedding.cosine_distance(query_embedding))
            .limit(top_k)
            .all()
        )
        logger.info(
            "Found relevant FAQs",
            extra={
                "count": len(relevant_faqs),
                "tenant_id": tenant_id,
                "query": user_query,
                "top_k": top_k,
            },
        )
        return relevant_faqs
    except Exception as e:
        logger.error(
            "Error finding relevant FAQs",
            extra={"tenant_id": tenant_id, "query": user_query},
            exc_info=e,
        )
        return []


@track_openai_call(model=MODEL_NAME, endpoint="chat/completions")
async def get_rag_response(
    db: Session, tenant_id: str, user_query: str, system_prompt: str
) -> Dict[str, Any]:
    """
    Core RAG function:
    1. Finds relevant FAQs for the user_query and tenant_id.
    2. Constructs a prompt with this context.
    3. Sends the prompt to an LLM to generate a response.

    Returns:
        Dictionary with answer, sources, and token_count
    """
    logger.info(
        "RAG: Processing query", extra={"tenant_id": tenant_id, "query": user_query}
    )

    relevant_faqs = await find_relevant_faqs(db, tenant_id, user_query, top_k=3)

    context_parts = []
    sources = []
    if not relevant_faqs:
        context_str = (
            "No specific information found in the knowledge base for your query."
        )
    else:
        for i, faq_item in enumerate(relevant_faqs):
            context_parts.append(
                f"{i+1}. Question: {faq_item.question}\n   Answer: {faq_item.answer}"
            )
            sources.append(
                {
                    "id": faq_item.id,
                    "question": faq_item.question,
                    "answer": faq_item.answer,
                }
            )
        context_str = "Relevant information from knowledge base:\n" + "\n\n".join(
            context_parts
        )

    # Construct the prompt for the LLM
    prompt = f"{system_prompt}\n\nContext from knowledge base:\n{context_str}\n\nUser Question: {user_query}\n\nAnswer:"

    logger_ai.info(f"Calling model {MODEL_NAME}")

    logger.debug(
        "Constructed prompt for LLM",
        extra={"prompt_length": len(prompt), "faq_count": len(relevant_faqs)},
    )

    # For now, we'll return a placeholder response that includes the context found
    try:
        # In a real implementation, this would be an actual OpenAI API call
        # response = await openai.ChatCompletion.acreate(...)

        if not relevant_faqs:
            llm_answer = f"I couldn't find specific information in our knowledge base for your question: \'{user_query}\'. Please try rephrasing or ask something else."
        else:
            llm_answer = f"Based on the information I found regarding \'{user_query}\':\n\n{context_str}\n\n(This is a conceptual answer. An actual LLM would synthesize this information to directly answer your question.)"
    except Exception as e:
        logger_ai.error(f"OpenAI error: {e}")
        return "Извините, временная ошибка. Попробуйте позже."

    # Calculate token count (simplified estimation)
    # In a real implementation, this would come from the OpenAI API response
    token_count = len(prompt.split()) + len(llm_answer.split())

    logger.info(
        "RAG: Generated response",
        extra={
            "tenant_id": tenant_id,
            "response_length": len(llm_answer),
            "token_count": token_count,
        },
    )

    return {"answer": llm_answer, "sources": sources, "token_count": token_count}


