"""
Database connection pool management for avry-blog service.
Uses asyncpg with connection pooling, health checks, and exponential backoff retry.
"""

import asyncio
import logging
from typing import Optional

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None

# Retry configuration
MAX_RETRIES = 5
BASE_DELAY = 1  # seconds


async def create_pool() -> asyncpg.Pool:
    """Create and return an asyncpg connection pool with exponential backoff retry."""
    global _pool

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            logger.info("✓ Database connection pool created")
            return _pool
        except (asyncpg.PostgresError, OSError, Exception) as e:
            delay = BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                f"Database connection attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                f"Retrying in {delay}s..."
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Failed to connect to database after {MAX_RETRIES} attempts"
                )
                raise


async def get_pool() -> Optional[asyncpg.Pool]:
    """Get the current connection pool instance."""
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


async def check_health() -> bool:
    """
    Check database health by executing a simple query.
    Returns True if the database is reachable, False otherwise.
    """
    if _pool is None:
        return False

    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return False
