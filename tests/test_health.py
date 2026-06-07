"""Unit tests for the avry-blog health endpoint."""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_200_when_db_connected():
    """Health endpoint returns 200 with healthy status when DB is reachable."""
    with patch("app.main.check_health", new_callable=AsyncMock, return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "avry-blog"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_health_returns_503_when_db_disconnected():
    """Health endpoint returns 503 with unhealthy status when DB is unreachable."""
    with patch("app.main.check_health", new_callable=AsyncMock, return_value=False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["service"] == "avry-blog"
    assert data["database"] == "disconnected"
