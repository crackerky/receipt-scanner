import os
import logging
from typing import Optional, List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    """Application settings with secure environment variable handling."""
    
    def __init__(self):
        # First, set environment and debug to avoid dependency issues
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        
        # Required environment variables
        self.openai_api_key = self._get_required_env("OPENAI_API_KEY")
        
        # Optional environment variables with defaults
        self.database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/receipt_scanner")
        self.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
        
        # Tesseract configuration
        self.tessdata_prefix = os.getenv("TESSDATA_PREFIX")
        
        # CORS configuration
        allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        self.allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]
        
        # API rate limiting
        self.rate_limit_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
        self.rate_limit_window = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
        
        # Validate configuration
        self._validate_config()
        
        # Setup logging to exclude sensitive information
        self._setup_secure_logging()
    
    def _get_required_env(self, key: str) -> str:
        """Get required environment variable with error handling."""
        value = os.getenv(key)
        if not value:
            if self.environment == "development":
                logging.warning(f"Required environment variable {key} is not set. Some features may be limited.")
                return ""
            else:
                raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    def _validate_config(self):
        """Validate configuration settings."""
        if self.environment == "production":
            if self.secret_key == "dev-secret-key-change-in-production":
                raise ValueError("SECRET_KEY must be changed in production")
            
            if self.debug:
                logging.warning("DEBUG is enabled in production environment")
            
            if "localhost" in self.allowed_origins:
                logging.warning("localhost is allowed in production CORS settings")
    
    def _setup_secure_logging(self):
        """Setup logging to exclude sensitive information."""
        class SanitizeFilter(logging.Filter):
            def filter(self, record):
                if hasattr(record, 'msg'):
                    msg = str(record.msg)
                    # Replace API keys and other sensitive data
                    if self.openai_api_key:
                        msg = msg.replace(self.openai_api_key, '***REDACTED***')
                    msg = msg.replace(self.secret_key, '***REDACTED***')
                    record.msg = msg
                return True
        
        # Add filter to all loggers
        logging.getLogger().addFilter(SanitizeFilter())
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    @property
    def openai_available(self) -> bool:
        """Check if OpenAI API is available."""
        return bool(self.openai_api_key)

# Global settings instance
settings = Settings()

# Export for backward compatibility
__all__ = ["settings"]