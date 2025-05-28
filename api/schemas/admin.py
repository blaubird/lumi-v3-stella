from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class TenantBase(BaseModel):
    phone_id: str
    wh_token: str
    system_prompt: str

class TenantCreate(TenantBase):
    pass

class TenantResponse(TenantBase):
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class FAQBase(BaseModel):
    question: str
    answer: str

class FAQCreate(FAQBase):
    pass

class FAQResponse(FAQBase):
    id: int
    tenant_id: str
    embedding: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class MessageBase(BaseModel):
    role: str
    text: str

class MessageResponse(MessageBase):
    id: int
    tenant_id: str
    wa_msg_id: Optional[str] = None
    tokens: Optional[int] = None
    ts: datetime
    
    class Config:
        from_attributes = True
