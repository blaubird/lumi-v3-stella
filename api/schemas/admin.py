from pydantic import BaseModel, Field
from typing import List, Optional

class TenantBase(BaseModel):
    phone_id: str
    wh_token: str
    system_prompt: str

class TenantCreate(TenantBase):
    pass

class TenantUpdate(BaseModel):
    phone_id: Optional[str] = None
    wh_token: Optional[str] = None
    system_prompt: Optional[str] = None

class TenantResponse(TenantBase):
    id: str
    
    class Config:
        orm_mode = True
