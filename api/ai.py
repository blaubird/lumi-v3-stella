import os
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from openai import AsyncOpenAI
from logging_utils import get_logger
from models import FAQ
from monitoring_utils import track_openai_call

# Initialize logger
logger = get_logger(__name__)

# Initialize OpenAI client
client = None
EMBEDDING_MODEL_NAME = "text-embedding-3-small"

def load_embedding_model():
    """
    Initialize the OpenAI client for embedding generation.
    """
    global client
    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable is not set")
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        client = AsyncOpenAI(api_key=api_key)
        logger.info("OpenAI client initialized", extra={"model": EMBEDDING_MODEL_NAME})
    return client

async def generate_embedding(text_content: str) -> Optional[List[float]]:
    """
    Generate an embedding vector for the given text content using OpenAI's API.
    
    Args:
        text_content: The text to generate an embedding for
        
    Returns:
        A list of floats representing the embedding vector, or None if generation failed
    """
    global client
    if client is None:
        try:
            load_embedding_model()
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            return None
    
    if not text_content or not isinstance(text_content, str):
        logger.warning("Invalid or empty text_content provided for embedding generation.")
        return None
    
    try:
        logger.info("Generating embedding for text", extra={
            "text_preview": text_content[:50] + "..." if len(text_content) > 50 else text_content,
            "text_length": len(text_content)
        })
        
        # Check API key before request
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY is missing before embedding request")
            return None
        
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL_NAME,
            input=text_content
        )
        embedding = response.data[0].embedding
        
        # Log successful result
        logger.info("Successfully generated embedding", extra={
            "embedding_dimensions": len(embedding)
        })
        return embedding
    except Exception as e:
        # Structured logging of errors
        logger.error("Error during embedding generation", extra={
            "error_type": type(e).__name__,
            "error_details": str(e)
        }, exc_info=e)
        
        return None

async def find_relevant_faqs(db: Session, tenant_id: str, user_query: str, top_k: int = 3) -> List[FAQ]:
    """
    Finds the top_k most relevant FAQs from the database for a specific tenant
    based on the user query, using cosine similarity with pgvector.
    """
    global client
    if client is None:
        logger.error("OpenAI client is not initialized. Cannot find relevant FAQs.")
        raise RuntimeError("OpenAI client is not initialized.")
    if not user_query:
        logger.warning("Empty user query provided.")
        return []
    query_embedding = await generate_embedding(user_query)
    if query_embedding is None:
        logger.warning("Could not generate embedding for query", extra={"query": user_query})
        return []
    try:
        # Using SQLAlchemy's ORM with pgvector's cosine_distance
        # Lower cosine_distance means higher similarity
        relevant_faqs = (
            db.query(FAQ)
            .filter(FAQ.tenant_id == tenant_id)
            .filter(FAQ.embedding is not None)  # Ensure embedding is not null
            .order_by(FAQ.embedding.cosine_distance(query_embedding))
            .limit(top_k)
            .all()
        )
        logger.info("Found relevant FAQs", extra={
            "count": len(relevant_faqs),
            "tenant_id": tenant_id,
            "query": user_query,
            "top_k": top_k
        })
        return relevant_faqs
    except Exception as e:
        logger.error("Error finding relevant FAQs", extra={
            "tenant_id": tenant_id,
            "query": user_query
        }, exc_info=e)
        return []

@track_openai_call(model="gpt-4o", endpoint="chat/completions")
async def get_rag_response(db: Session, tenant_id: str, user_query: str, system_prompt: str) -> Dict[str, Any]:
    """
    Core RAG function:
    1. Finds relevant FAQs for the user_query and tenant_id.
    2. Constructs a prompt with this context.
    3. Sends the prompt to an LLM to generate a response.
    
    Returns:
        Dictionary with answer and sources
    """
    logger.info("RAG: Processing query", extra={
        "tenant_id": tenant_id,
        "query": user_query
    })
    
    relevant_faqs = await find_relevant_faqs(db, tenant_id, user_query, top_k=3)
    
    context_parts = []
    sources = []
    if not relevant_faqs:
        context_str = "No specific information found in the knowledge base for your query."
    else:
        for i, faq_item in enumerate(relevant_faqs):
            context_parts.append(f"{i+1}. Question: {faq_item.question}\n   Answer: {faq_item.answer}")
            sources.append({
                "id": faq_item.id,
                "question": faq_item.question,
                "answer": faq_item.answer
            })
        context_str = "Relevant information from knowledge base:\n" + "\n\n".join(context_parts)
    
    # Construct the prompt for the LLM
    prompt = f"{system_prompt}\n\nContext from knowledge base:\n{context_str}\n\nUser Question: {user_query}\n\nAnswer:"
    
    logger.debug("Constructed prompt for LLM", extra={
        "prompt_length": len(prompt),
        "faq_count": len(relevant_faqs)
    })
    
    # For now, we'll return a placeholder response that includes the context found
    if not relevant_faqs:
        llm_answer = f"I couldn't find specific information in our knowledge base for your question: '{user_query}'. Please try rephrasing or ask something else."
    else:
        llm_answer = f"Based on the information I found regarding '{user_query}':\n\n{context_str}\n\n(This is a conceptual answer. An actual LLM would synthesize this information to directly answer your question.)"
    
    logger.info("RAG: Generated response", extra={
        "tenant_id": tenant_id,
        "response_length": len(llm_answer)
    })
    
    return {
        "answer": llm_answer,
        "sources": sources
    }
