from datetime import datetime, timedelta
from typing import Optional, Union
import logging

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.db_models import User
from app.models import TokenData

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# HTTP Bearer scheme
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

def create_fake_test_user() -> User:
    """Create a fake test user for development purposes."""
    return User(
        id=9999,
        username="test_user",
        email="test@example.com",
        is_active=True,
        is_superuser=False,
        hashed_password=get_password_hash("test_password")
    )

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[TokenData]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        token_data = TokenData(username=username)
        return token_data
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None

def authenticate_user(db: Session, username: str, password: str) -> Union[User, bool]:
    """Authenticate a user with username and password."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def get_user(db: Session, username: str) -> Optional[User]:
    """Get a user by username."""
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get a user by email."""
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, username: str, email: str, password: str) -> User:
    """Create a new user."""
    hashed_password = get_password_hash(password)
    db_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token_data = verify_token(credentials.credentials)
        if token_data is None or token_data.username is None:
            raise credentials_exception
        
        user = get_user(db, username=token_data.username)
        if user is None:
            raise credentials_exception
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        return user
    except Exception as e:
        logger.warning(f"Authentication failed: {e}")
        raise credentials_exception

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get the current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_active_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current active user with optional authentication.
    If DISABLE_AUTH is true, returns a fake test user.
    """
    # Check if auth is disabled
    if settings.disable_auth:
        logger.warning("Authentication is disabled - using test user")
        return create_fake_test_user()
    
    # If auth is enabled, use normal authentication
    return await get_current_active_user(credentials, db)

async def get_current_active_user_optional_original(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get the current active user with optional authentication.
    Returns a fake test user when no authentication is provided.
    
    WARNING: This function is for testing purposes only and should be removed in production!
    """
    # If no credentials are provided, return a fake test user
    if credentials is None:
        logger.warning("No authentication provided - returning fake test user. THIS SHOULD ONLY BE USED FOR TESTING!")
        
        # Create a fake user object for testing
        fake_user = User()
        fake_user.id = 9999
        fake_user.username = "test_user"
        fake_user.email = "test@example.com"
        fake_user.is_active = True
        fake_user.hashed_password = get_password_hash("test_password")
        
        return fake_user
    
    # If credentials are provided, use the normal authentication flow
    try:
        # Manually call the get_current_user logic
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        token_data = verify_token(credentials.credentials)
        if token_data is None or token_data.username is None:
            raise credentials_exception
        
        user = get_user(db, username=token_data.username)
        if user is None:
            raise credentials_exception
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        return user
    except Exception as e:
        # If authentication fails, return the fake test user
        logger.warning(f"Authentication failed ({e}) - returning fake test user. THIS SHOULD ONLY BE USED FOR TESTING!")
        
        fake_user = User()
        fake_user.id = 9999
        fake_user.username = "test_user"
        fake_user.email = "test@example.com"
        fake_user.is_active = True
        fake_user.hashed_password = get_password_hash("test_password")
        
        return fake_user