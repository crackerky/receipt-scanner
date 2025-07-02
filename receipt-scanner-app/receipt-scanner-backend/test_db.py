#!/usr/bin/env python3
"""Test database connection and basic operations"""

from datetime import datetime
from app.database import engine, SessionLocal, Base
from app.db_models import Receipt

def test_database():
    """Test database operations"""
    print("Testing database connection...")
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created")
    
    # Create a session
    db = SessionLocal()
    
    try:
        # Create a test receipt
        test_receipt = Receipt(
            store_name="Test Store",
            purchase_date=datetime.now(),
            total_amount=1234.56,
            category="食費",
            processing_mode="test",
            confidence_score=0.95
        )
        
        # Add to database
        db.add(test_receipt)
        db.commit()
        db.refresh(test_receipt)
        print(f"✓ Test receipt created with ID: {test_receipt.id}")
        
        # Query the receipt
        receipt = db.query(Receipt).filter(Receipt.id == test_receipt.id).first()
        if receipt:
            print(f"✓ Receipt retrieved: {receipt.store_name} - ¥{receipt.total_amount}")
        
        # Update the receipt
        receipt.category = "交通費"
        db.commit()
        print("✓ Receipt updated")
        
        # Count receipts
        count = db.query(Receipt).count()
        print(f"✓ Total receipts in database: {count}")
        
        # Clean up - soft delete
        receipt.is_deleted = True
        db.commit()
        print("✓ Receipt soft deleted")
        
        print("\n✅ All database tests passed!")
        
    except Exception as e:
        print(f"\n❌ Database test failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_database()