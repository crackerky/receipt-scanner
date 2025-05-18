from pydantic import BaseModel
from typing import Optional, List
from datetime import date

class ReceiptData(BaseModel):
    """Receipt data extracted from an image."""
    date: date
    store_name: str
    total_amount: float
    tax_excluded_amount: Optional[float] = None
    tax_included_amount: Optional[float] = None
    expense_category: Optional[str] = None
    
class ReceiptResponse(BaseModel):
    """Response model for receipt data extraction."""
    success: bool
    message: str
    data: Optional[ReceiptData] = None
    
class ReceiptList(BaseModel):
    """List of receipts."""
    receipts: List[ReceiptData]
