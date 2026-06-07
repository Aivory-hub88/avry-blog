"""
Unit tests for the WebSocket connection manager.

Tests the ConnectionManager class methods: connect, disconnect, broadcast,
heartbeat detection, and the global blog_manager instance.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.websocket.manager import ConnectionManager, blog_manager, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT


@pytest.fixture
def manager():
    """Create a fresh ConnectionManager for each test."""
    return ConnectionManager()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.receive_text = AsyncMock()
    return ws


class TestConnectionManager:
    """Tests for ConnectionManager basic operations."""

    @pytest.mark.asyncio
    async def test_connect_accepts_and_adds_connection(self, manager, mock_websocket):
        """connect() should accept the websocket and add it to active connections."""
        await manager.connect(mock_websocket)

        mock_websocket.accept.assert_called_once()
        assert manager.connection_count == 1
        assert mock_websocket in manager.active_connections

    @pytest.mark.asyncio
    async def test_connect_multiple_clients(self, manager):
        """connect() should handle multiple simultaneous connections."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.connect(ws3)

        assert manager.connection_count == 3

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, manager, mock_websocket):
        """disconnect() should remove a connection from the active list."""
        await manager.connect(mock_websocket)
        assert manager.connection_count == 1

        manager.disconnect(mock_websocket)
        assert manager.connection_count == 0
        assert mock_websocket not in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_connection(self, manager, mock_websocket):
        """disconnect() should not raise when removing a non-existent connection."""
        # Should not raise
        manager.disconnect(mock_websocket)
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_clients(self, manager):
        """broadcast() should send the message to all connected clients."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)

        message = {"type": "post_published", "data": {"post_id": "abc123"}}
        await manager.broadcast(message)

        expected_payload = json.dumps(message)
        ws1.send_text.assert_called_once_with(expected_payload)
        ws2.send_text.assert_called_once_with(expected_payload)

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self, manager):
        """broadcast() should remove connections that fail to receive."""
        ws_alive = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text = AsyncMock(side_effect=Exception("Connection closed"))

        await manager.connect(ws_alive)
        await manager.connect(ws_dead)

        assert manager.connection_count == 2

        message = {"type": "post_edited", "data": {"post_id": "xyz"}}
        await manager.broadcast(message)

        # Dead connection should be removed
        assert manager.connection_count == 1
        assert ws_alive in manager.active_connections
        assert ws_dead not in manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_empty_connections(self, manager):
        """broadcast() should not raise when no connections exist."""
        # Should complete without error
        await manager.broadcast({"type": "test"})

    @pytest.mark.asyncio
    async def test_broadcast_message_types(self, manager):
        """broadcast() should correctly serialize all expected message types."""
        ws = AsyncMock()
        await manager.connect(ws)

        messages = [
            {"type": "post_published", "data": {"post_id": "1", "title": "Hello"}},
            {"type": "post_hidden", "data": {"post_id": "2"}},
            {"type": "post_edited", "data": {"post_id": "3", "title": "Updated"}},
            {"type": "new_comment", "data": {"comment_id": "c1", "post_id": "1", "body": "Nice!"}},
            {
                "type": "reaction_update",
                "data": {
                    "target_type": "post",
                    "target_id": "1",
                    "like_count": 5,
                    "dislike_count": 2,
                },
            },
        ]

        for msg in messages:
            await manager.broadcast(msg)

        assert ws.send_text.call_count == 5

        # Verify each message was serialized correctly
        for i, msg in enumerate(messages):
            call_args = ws.send_text.call_args_list[i]
            sent_payload = call_args[0][0]
            assert json.loads(sent_payload) == msg

    @pytest.mark.asyncio
    async def test_active_connections_returns_copy(self, manager, mock_websocket):
        """active_connections property should return a copy, not the internal list."""
        await manager.connect(mock_websocket)
        connections = manager.active_connections
        connections.clear()  # Modifying the copy

        # Internal list should be unaffected
        assert manager.connection_count == 1

    @pytest.mark.asyncio
    async def test_shutdown_closes_all_connections(self, manager):
        """shutdown() should close all connections and clear the list."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)

        await manager.shutdown()

        assert manager.connection_count == 0
        ws1.close.assert_called_once()
        ws2.close.assert_called_once()


class TestHeartbeatConfiguration:
    """Tests for heartbeat configuration constants."""

    def test_heartbeat_interval_is_30_seconds(self):
        """Heartbeat interval should be 30 seconds as per spec."""
        assert HEARTBEAT_INTERVAL == 30

    def test_heartbeat_timeout_is_10_seconds(self):
        """Heartbeat timeout should be 10 seconds as per spec."""
        assert HEARTBEAT_TIMEOUT == 10


class TestGlobalBlogManager:
    """Tests for the global blog_manager instance."""

    def test_blog_manager_is_connection_manager_instance(self):
        """blog_manager should be a ConnectionManager instance."""
        assert isinstance(blog_manager, ConnectionManager)

    def test_blog_manager_starts_empty(self):
        """blog_manager should have no connections initially."""
        assert blog_manager.connection_count == 0


class TestWebSocketEndpoint:
    """Tests for the /ws/blog WebSocket endpoint registration."""

    @pytest.mark.asyncio
    async def test_websocket_endpoint_registered(self):
        """The /ws/blog endpoint should be registered on the FastAPI app."""
        from app.main import app

        # Check that the websocket route exists
        ws_routes = [
            route
            for route in app.routes
            if hasattr(route, "path") and route.path == "/ws/blog"
        ]
        assert len(ws_routes) == 1
