from pydantic import BaseModel
from typing import List, Optional


# FAQ item for bulk import
class FAQItem(BaseModel):
    question: str
    answer: str


# Rename to match the import in admin.py
class BulkFAQImportRequest(BaseModel):
    items: List[FAQItem]


# Add the missing response schema
class BulkFAQImportResponse(BaseModel):
    total_items: int
    successful_items: int
    failed_items: int
    errors: Optional[List[str]] = None
