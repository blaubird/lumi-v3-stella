from __future__ import annotations

from datetime import datetime

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from utils.tenant_ids import TenantIdNormalizationError, normalize_tenant_id


def _coerce_int(value: Any, field_name: Optional[str]) -> int:
    label = field_name or "value"
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc


def _coerce_tenant_id(value: Any, field_name: Optional[str]) -> str:
    try:
        return normalize_tenant_id(value, field_name=field_name)
    except TenantIdNormalizationError as exc:
        raise ValueError(str(exc)) from exc


class TenantBase(BaseModel):
    id: str = Field(..., examples=["1", "test_tenant_X"])
    phone_id: str
    wh_token: str
    system_prompt: str

    @field_validator("id", mode="before")
    @classmethod
    def _validate_id(cls, value: Any, info: ValidationInfo) -> str:
        return _coerce_tenant_id(value, info.field_name)


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
    tenant_id: str = Field(examples=["1", "test_tenant_X"])
    embedding: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _validate_tenant_id(cls, value: Any, info: ValidationInfo) -> str:
        return _coerce_tenant_id(value, info.field_name)


class MessageBase(BaseModel):
    role: str
    text: str


class MessageResponse(MessageBase):
    id: int
    tenant_id: str = Field(examples=["1", "test_tenant_X"])
    wa_msg_id: Optional[str] = None
    tokens: Optional[int] = None
    ts: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _validate_tenant_id(cls, value: Any, info: ValidationInfo) -> str:
        return _coerce_tenant_id(value, info.field_name)


class UsageResponse(BaseModel):
    id: int
    tenant_id: str = Field(examples=["1", "test_tenant_X"])
    direction: Optional[str] = None
    tokens: Optional[int] = None
    msg_ts: datetime
    model: Optional[str] = None
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    trace_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _validate_tenant_id(cls, value: Any, info: ValidationInfo) -> str:
        return _coerce_tenant_id(value, info.field_name)

    @field_validator(
        "prompt_tokens", "completion_tokens", "total_tokens", mode="before"
    )
    @classmethod
    def _validate_usage_tokens(cls, value: Any, info: ValidationInfo) -> int:
        if value is None:
            return 0
        return _coerce_int(value, info.field_name)


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
