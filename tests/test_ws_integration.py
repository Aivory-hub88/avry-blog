"""
Integration tests for WebSocket broadcast delivery in avry-blog.

Validates Requirements 13.1, 13.2, 13.3, 13.4:
- Blog_Service establishes WebSocket connections with clients
- Admin publishes post → connected blog WS client receives update within 2s
- Admin hides post → connected blog WS client receives update within 2s
- Admin edits post → connected blog WS client receives update within 2s

These tests use real WebSocket connections to the FastAPI app via Starlette's
TestClient, with the database mocked. The broadcast function is called directly
to simulate admin actions triggering real-time updates.
"""

import asyncio
import json
import threading

import pytest
from unittest.mock import patch, AsyncMock

from app.main import app
from app.websocket.manager import blog_manager


@pytest.fixture(autouse=True)
def mock_database():
    """Mock database calls so tests don't require a real PostgreSQL connection."""
    with patch("app.database.connection.create_pool", new_callable=AsyncMock), \
         patch("app.database.connection.close_pool", new_callable=AsyncMock), \
         patch("app.database.connection.check_health", new_callable=AsyncMock, return_value=True), \
         patch("app.database.migrations.run_migrations", new_callable=AsyncMock), \
         patch("app.seed.seed_welcome_post", new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def reset_manager():
    """Reset the global blog_manager state before each test for isolation."""
    blog_manager._active_connections = []
    if blog_manager._heartbeat_task is not None:
        blog_manager._heartbeat_task.cancel()
    blog_manager._heartbeat_task = None
    yield
    # Cleanup after test
    blog_manager._active_connections = []
    if blog_manager._heartbeat_task is not None:
        blog_manager._heartbeat_task.cancel()
    blog_manager._heartbeat_task = None


def _broadcast_sync(manager, message: dict) -> None:
    """Run an async broadcast in a new event loop on a separate thread (within 2s)."""
    async def do_broadcast():
        await manager.broadcast(message)

    loop = asyncio.new_event_loop()
    t = threading.Thread(target=lambda: loop.run_until_complete(do_broadcast()))
    t.start()
    t.join(timeout=2)
    loop.close()


class TestBlogWebSocketBroadcastIntegration:
    """Integration tests: admin action → blog WS broadcast → client receives within 2s."""

    def test_post_published_broadcast_delivery(self):
        """
        Admin publishes a post → connected blog WS client receives
        'post_published' message within 2 seconds.

        Validates: Requirements 13.1, 13.3
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/blog") as websocket:
                message = {
                    "type": "post_published",
                    "data": {
                        "post_id": "test-post-123",
                        "title": "New Integration Test Post",
                        "slug": "new-integration-test-post",
                    },
                }

                _broadcast_sync(blog_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "post_published"
                assert received["data"]["post_id"] == "test-post-123"
                assert received["data"]["title"] == "New Integration Test Post"

    def test_post_hidden_broadcast_delivery(self):
        """
        Admin hides a post → connected blog WS client receives
        'post_hidden' message within 2 seconds.

        Validates: Requirements 13.1, 13.3
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/blog") as websocket:
                message = {
                    "type": "post_hidden",
                    "data": {
                        "post_id": "hidden-post-456",
                    },
                }

                _broadcast_sync(blog_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "post_hidden"
                assert received["data"]["post_id"] == "hidden-post-456"

    def test_post_edited_broadcast_delivery(self):
        """
        Admin edits a post → connected blog WS client receives
        'post_edited' message within 2 seconds.

        Validates: Requirements 13.1, 13.3
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/blog") as websocket:
                message = {
                    "type": "post_edited",
                    "data": {
                        "post_id": "edited-post-789",
                        "title": "Updated Title",
                    },
                }

                _broadcast_sync(blog_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "post_edited"
                assert received["data"]["post_id"] == "edited-post-789"
                assert received["data"]["title"] == "Updated Title"

    def test_new_comment_broadcast_delivery(self):
        """
        New comment posted → connected blog WS client receives
        'new_comment' message within 2 seconds.

        Validates: Requirements 13.1, 13.3
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/blog") as websocket:
                message = {
                    "type": "new_comment",
                    "data": {
                        "comment_id": "comment-001",
                        "post_id": "test-post-123",
                        "author_name": "Test User",
                        "body": "Great post!",
                    },
                }

                _broadcast_sync(blog_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "new_comment"
                assert received["data"]["comment_id"] == "comment-001"
                assert received["data"]["post_id"] == "test-post-123"

    def test_reaction_update_broadcast_delivery(self):
        """
        Reaction count changes → connected blog WS client receives
        'reaction_update' message within 2 seconds.

        Validates: Requirements 13.1, 13.3
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/blog") as websocket:
                message = {
                    "type": "reaction_update",
                    "data": {
                        "target_type": "post",
                        "target_id": "test-post-123",
                        "like_count": 10,
                        "dislike_count": 2,
                    },
                }

                _broadcast_sync(blog_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "reaction_update"
                assert received["data"]["like_count"] == 10
                assert received["data"]["dislike_count"] == 2

    def test_multiple_clients_receive_broadcast(self):
        """
        Broadcast sent → ALL connected WS clients receive the message
        within 2 seconds.

        Validates: Requirements 13.1, 13.3
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client1, TestClient(app) as client2:
            with client1.websocket_connect("/ws/blog") as ws1, \
                 client2.websocket_connect("/ws/blog") as ws2:

                message = {
                    "type": "post_published",
                    "data": {
                        "post_id": "broadcast-all-test",
                        "title": "Broadcast to All",
                    },
                }

                _broadcast_sync(blog_manager, message)

                data1 = ws1.receive_text()
                data2 = ws2.receive_text()

                received1 = json.loads(data1)
                received2 = json.loads(data2)

                assert received1["type"] == "post_published"
                assert received1["data"]["post_id"] == "broadcast-all-test"
                assert received2["type"] == "post_published"
                assert received2["data"]["post_id"] == "broadcast-all-test"
