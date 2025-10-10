from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


class FAQBase(BaseModel):
    question: str
    answer: str


class FAQCreate(FAQBase):
    pass


class FAQResponse(FAQBase):
    id: int
    tenant_id: int

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _validate_tenant_id(cls, value: Any, info: ValidationInfo) -> int:
        return _coerce_int(value, info.field_name)


class QueryRequest(BaseModel):
    query: str
    lang: Optional[str] = None

    model_config = ConfigDict(extra="allow")


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
