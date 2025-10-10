from __future__ import annotations

from datetime import datetime

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _coerce_optional_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    return _coerce_int(value, field_name)


class TenantBase(BaseModel):
    id: int = Field(..., examples=[1])
    phone_id: str
    wh_token: str
    system_prompt: str

    @field_validator("id", mode="before")
    @classmethod
    def _validate_id(cls, value: Any, info: ValidationInfo) -> int:
        return _coerce_int(value, info.field_name)


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    phone_id: Optional[str] = None
    wh_token: Optional[str] = None
    system_prompt: Optional[str] = None


class TenantResponse(TenantBase):
    model_config = ConfigDict(from_attributes=True)


class FAQBase(BaseModel):
    question: str
    answer: str


class FAQCreate(FAQBase):
    pass


class FAQResponse(FAQBase):
    id: int
    tenant_id: int
    embedding: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _validate_tenant_id(cls, value: Any, info: ValidationInfo) -> int:
        return _coerce_int(value, info.field_name)


class MessageBase(BaseModel):
    role: str
    text: str


class MessageResponse(MessageBase):
    id: int
    tenant_id: int
    wa_msg_id: Optional[str] = None
    tokens: Optional[int] = None
    ts: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _validate_tenant_id(cls, value: Any, info: ValidationInfo) -> int:
        return _coerce_int(value, info.field_name)


class UsageResponse(BaseModel):
    id: int
    tenant_id: int
    direction: str
    tokens: int
    msg_ts: datetime
    model: Optional[str] = None
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _validate_tenant_id(cls, value: Any, info: ValidationInfo) -> int:
        return _coerce_int(value, info.field_name)

    @field_validator(
        "prompt_tokens", "completion_tokens", "total_tokens", mode="before"
    )
    @classmethod
    def _validate_usage_tokens(cls, value: Any, info: ValidationInfo) -> Optional[int]:
        return _coerce_optional_int(value, info.field_name)


class UsageStatsResponse(BaseModel):
    items: List[UsageResponse]
    total_inbound_tokens: int
    total_outbound_tokens: int


class BulkFAQItem(BaseModel):
    question: str
    answer: str


class BulkFAQImportRequest(BaseModel):
    items: List[BulkFAQItem]


class BulkFAQImportResponse(BaseModel):
    total_items: int
    successful_items: int
    failed_items: int
    errors: Optional[List[str]] = None
