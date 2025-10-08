from pydantic import BaseModel, Field
from typing import List, Optional, Union


class FAQBase(BaseModel):
    question: str
    answer: str


class FAQCreate(FAQBase):
    pass


class FAQResponse(FAQBase):
    id: int
    tenant_id: int

    model_config = {"from_attributes": True}


class QueryRequest(BaseModel):
    tenant_id: int
    query: str
    lang: Optional[str] = None


class UsedChunk(BaseModel):
    id: Union[int, str]
    score: float
    q: Optional[str] = None
    a: Optional[str] = None


class QueryResponse(BaseModel):
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    used_chunks: List[UsedChunk] = Field(default_factory=list)
