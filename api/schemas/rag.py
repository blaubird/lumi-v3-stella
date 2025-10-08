from pydantic import BaseModel, Field
from typing import List


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


class QueryResponse(BaseModel):
    answer: str
    sources: List[FAQResponse] = Field(default_factory=list)
