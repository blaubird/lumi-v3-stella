from pydantic import BaseModel
from typing import List, Optional

class BulkImportRequest(BaseModel):
    tenant_id: int
    faqs: List[dict]
