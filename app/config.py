"""Configuration module for avry-blog service"""
import os
import sys
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")
load_dotenv(".env")


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = ConfigDict(extra="ignore")

    # Server configuration
    app_name: str = "AVRY Blog Service"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8089

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/aivery"

    # Authentication
    supabase_jwt_secret: str = ""
    jwt_secret: str = ""  # Legacy fallback

    # CORS configuration
    cors_origins: list[str] = ["*"]


# Global settings instance
try:
    settings = Settings()
    print(f"✓ Configuration loaded successfully")
    print(f"  - App: {settings.app_name} v{settings.app_version}")
    print(f"  - Port: {settings.port}")
except Exception as e:
    print(f"✗ Failed to load configuration: {str(e)}")
    sys.exit(1)
