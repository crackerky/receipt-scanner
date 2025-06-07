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
        
        # Vision API settings
        self.use_vision_api = os.getenv("USE_VISION_API", "true").lower() == "true"
        self.vision_api_model = os.getenv("VISION_API_MODEL", "gpt-4o")  # or "gpt-4o-mini"
        
        # Optional environment variables with defaults
        self.database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/receipt_scanner")
        self.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
        
        # Tesseract configuration
        self.tessdata_prefix = os.getenv("TESSDATA_PREFIX")
        
        # CORS configuration
        allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        
        # Special handling for wildcard
        if allowed_origins_str == "*":
            self.allowed_origins = ["*"]
        else:
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
                # OpenAI API keyは必須ではない（OCRのみで動作可能）
                if key == "OPENAI_API_KEY":
                    logging.warning(f"OpenAI API key not set. Will use OCR-only mode.")
                    return ""
                else:
                    raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    def _validate_config(self):
        """Validate configuration settings."""
        if self.environment == "production":
            if self.secret_key == "dev-secret-key-change-in-production":
                logging.warning("Using default SECRET_KEY in production - please change this!")
            
            if self.debug:
                logging.warning("DEBUG is enabled in production environment")
            
            if "*" in self.allowed_origins:
                logging.warning("CORS is set to allow all origins (*) in production - this is not recommended!")
            elif "localhost" in str(self.allowed_origins):
                logging.warning("localhost is allowed in production CORS settings")
    
    def _setup_secure_logging(self):
        """Setup logging to exclude sensitive information."""
        # Create a filter with access to settings
        openai_api_key = self.openai_api_key
        secret_key = self.secret_key
        
        class SanitizeFilter(logging.Filter):
            def filter(self, record):
                if hasattr(record, 'msg'):
                    msg = str(record.msg)
                    # Replace API keys and other sensitive data
                    if openai_api_key:
                        msg = msg.replace(openai_api_key, '***REDACTED***')
                    if secret_key:
                        msg = msg.replace(secret_key, '***REDACTED***')
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
    
    @property
    def vision_api_available(self) -> bool:
        """Check if Vision API is available and enabled."""
        return bool(self.openai_api_key) and self.use_vision_api

# Global settings instance
settings = Settings()

# Export for backward compatibility
__all__ = ["settings"]
