from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date, datetime

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

# Authentication Models
class UserCreate(BaseModel):
    """User registration model."""
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    """User login model."""
    username: str
    password: str

class UserResponse(BaseModel):
    """User response model (excluding password)."""
    id: int
    username: str
    email: str
    is_active: bool
    created_at: Optional[datetime] = None

class Token(BaseModel):
    """JWT token response model."""
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    """JWT token data model."""
    username: Optional[str] = None
