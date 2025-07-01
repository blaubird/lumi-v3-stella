from pydantic import BaseModel
from typing import Optional

class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: Optional[str] = None


