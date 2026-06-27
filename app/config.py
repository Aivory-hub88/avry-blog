"""Configuration module for avry-blog service"""
import os
import sys
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    pydantic-settings automatically reads matching env vars (case-insensitive),
    so DATABASE_URL, JWT_SECRET, etc. are picked up directly from the container
    environment without needing python-dotenv.
    """

    model_config = ConfigDict(extra="ignore")

    # Server configuration
    app_name: str = "AVRY Blog Service"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8089

    # Database — injected by docker-compose as DATABASE_URL env var
    database_url: str = "postgresql://postgres:postgres@localhost:5432/aivery"

    # Authentication — using local JWT_SECRET (Supabase removed)
    jwt_secret: str = ""

    # Keep supabase_jwt_secret as optional alias so auth.py doesn't break
    # but it will be empty; JWT verification falls back to jwt_secret
    supabase_jwt_secret: str = ""

    # CORS configuration
    cors_origins: list[str] = ["*"]


# Global settings instance
try:
    settings = Settings()
    print(f"✓ Configuration loaded successfully")
    print(f"  - App: {settings.app_name} v{settings.app_version}")
    print(f"  - Port: {settings.port}")
    print(f"  - Database host: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")
except Exception as e:
    print(f"✗ Failed to load configuration: {str(e)}")
    sys.exit(1)
