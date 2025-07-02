#!/usr/bin/env python3
"""Initialize the database and create tables"""

from app.database import engine, Base
from app.db_models import Receipt, User
import os

def init_db():
    """Create all tables in the database"""
    print("Creating database tables...")
    
    # Create receipts directory for image storage if it doesn't exist
    os.makedirs("receipts_images", exist_ok=True)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    
    # Print the database location
    from app.database import DATABASE_URL
    print(f"Database location: {DATABASE_URL}")

if __name__ == "__main__":
    init_db()