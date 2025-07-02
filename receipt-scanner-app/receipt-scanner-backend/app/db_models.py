from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Relationship with receipts
    receipts = relationship("Receipt", back_populates="user")
    
    def to_dict(self):
        """Convert model to dictionary for API responses (excluding password)"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    store_name = Column(String(255), nullable=False)
    purchase_date = Column(DateTime, nullable=False)
    total_amount = Column(Float, nullable=False)
    
    # Additional fields
    category = Column(String(100))
    items = Column(JSON)  # Store product details as JSON
    payment_method = Column(String(50))
    tax_amount = Column(Float)
    
    # Processing metadata
    processing_mode = Column(String(20), default="auto")  # ai, ocr, auto
    confidence_score = Column(Float)
    ocr_text = Column(Text)  # Store raw OCR text
    
    # Image storage
    image_path = Column(String(500))  # Path to stored image
    image_url = Column(String(500))   # URL if using cloud storage
    
    # User association
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="receipts")
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    uploaded_at = Column(DateTime, server_default=func.now())
    
    # Soft delete
    is_deleted = Column(Boolean, default=False)
    
    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "store_name": self.store_name,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "total_amount": self.total_amount,
            "category": self.category,
            "items": self.items,
            "payment_method": self.payment_method,
            "tax_amount": self.tax_amount,
            "processing_mode": self.processing_mode,
            "confidence_score": self.confidence_score,
            "image_path": self.image_path,
            "image_url": self.image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None
        }