from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TenantBase(BaseModel):
    phone_id: str
    wh_token: str
    system_prompt: str

class TenantCreate(TenantBase):
    id: str

class TenantUpdate(BaseModel):
    phone_id: Optional[str] = None
    wh_token: Optional[str] = None
    system_prompt: Optional[str] = None

class TenantResponse(TenantBase):
    id: str
    
    model_config = {'from_attributes': True}

class FAQBase(BaseModel):
    question: str
    answer: str

class FAQCreate(FAQBase):
    pass

class FAQResponse(FAQBase):
    id: int
    tenant_id: str
    embedding: Optional[str] = None
    
    model_config = {'from_attributes': True}

class MessageBase(BaseModel):
    role: str
    text: str

class MessageResponse(MessageBase):
    id: int
    tenant_id: str
    wa_msg_id: Optional[str] = None
    tokens: Optional[int] = None
    ts: datetime
    
    model_config = {'from_attributes': True}

class UsageResponse(BaseModel):
    id: int
    tenant_id: str
    direction: str
    tokens: int
    msg_ts: datetime
    
    model_config = {'from_attributes': True}

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
