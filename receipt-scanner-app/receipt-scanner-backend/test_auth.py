#!/usr/bin/env python3
"""Test authentication system"""

from datetime import datetime
from app.database import engine, SessionLocal, Base
from app.db_models import User, Receipt
from app.auth import create_user, authenticate_user, create_access_token, verify_token

def test_authentication():
    """Test authentication operations"""
    print("Testing authentication system...")
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created")
    
    # Create a session
    db = SessionLocal()
    
    try:
        # Test user creation
        print("\n--- Testing User Registration ---")
        test_user = create_user(
            db=db,
            username="testuser",
            email="test@example.com", 
            password="testpassword123"
        )
        print(f"✓ User created: {test_user.username} (ID: {test_user.id})")
        
        # Test authentication
        print("\n--- Testing Authentication ---")
        auth_user = authenticate_user(db, "testuser", "testpassword123")
        if auth_user:
            print(f"✓ Authentication successful: {auth_user.username}")
        else:
            print("❌ Authentication failed")
            return
        
        # Test wrong password
        wrong_auth = authenticate_user(db, "testuser", "wrongpassword")
        if not wrong_auth:
            print("✓ Wrong password correctly rejected")
        else:
            print("❌ Wrong password was accepted")
        
        # Test JWT token creation
        print("\n--- Testing JWT Tokens ---")
        access_token = create_access_token(data={"sub": test_user.username})
        print(f"✓ JWT token created: {access_token[:30]}...")
        
        # Test token verification
        token_data = verify_token(access_token)
        if token_data and token_data.username == test_user.username:
            print(f"✓ Token verified: {token_data.username}")
        else:
            print("❌ Token verification failed")
        
        # Test creating a receipt for the user
        print("\n--- Testing User-Receipt Association ---")
        test_receipt = Receipt(
            store_name="Test Store",
            purchase_date=datetime.now(),
            total_amount=1500.00,
            category="食費",
            processing_mode="test",
            confidence_score=0.98,
            user_id=test_user.id
        )
        
        db.add(test_receipt)
        db.commit()
        db.refresh(test_receipt)
        print(f"✓ Receipt created for user: {test_receipt.id}")
        
        # Query user's receipts
        user_receipts = db.query(Receipt).filter(Receipt.user_id == test_user.id).all()
        print(f"✓ User has {len(user_receipts)} receipt(s)")
        
        # Test user model serialization
        print("\n--- Testing Model Serialization ---")
        user_dict = test_user.to_dict()
        receipt_dict = test_receipt.to_dict()
        print(f"✓ User serialized: {user_dict['username']}")
        print(f"✓ Receipt serialized: {receipt_dict['store_name']}")
        
        # Clean up
        test_receipt.is_deleted = True
        db.query(User).filter(User.id == test_user.id).delete()
        db.commit()
        print("\n✓ Test data cleaned up")
        
        print("\n✅ All authentication tests passed!")
        
    except Exception as e:
        print(f"\n❌ Authentication test failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_authentication()