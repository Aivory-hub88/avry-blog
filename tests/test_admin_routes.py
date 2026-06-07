"""Unit tests for admin blog post endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.post import (
    BlogPost,
    BlogPostListItem,
    PaginatedPosts,
    PostStatus,
)


def _make_post(
    status: PostStatus = PostStatus.draft,
    slug: str = "test-post",
    post_id: uuid.UUID = None,
) -> BlogPost:
    """Create a BlogPost instance for testing."""
    now = datetime.now(timezone.utc)
    return BlogPost(
        id=post_id or uuid.uuid4(),
        slug=slug,
        title="Test Post",
        excerpt="A test excerpt",
        body={"type": "doc", "content": [{"type": "paragraph", "text": "Hello"}]},
        author_name="Test Author",
        thumbnail_url="https://example.com/img.png",
        status=status,
        like_count=0,
        dislike_count=0,
        comment_count=0,
        redacted_sections=[],
        published_at=now if status == PostStatus.published else None,
        created_at=now,
        updated_at=now,
    )


def _admin_payload():
    """Return a decoded JWT payload for an admin user."""
    return {"sub": "admin-user-id", "account_type": "admin"}


def _non_admin_payload():
    """Return a decoded JWT payload for a non-admin user."""
    return {"sub": "regular-user-id", "account_type": "user"}


ADMIN_HEADERS = {"Authorization": "Bearer valid-admin-token"}
NON_ADMIN_HEADERS = {"Authorization": "Bearer valid-user-token"}


# --- POST /api/admin/posts ---


@pytest.mark.asyncio
async def test_create_post_requires_auth():
    """POST /api/admin/posts returns 401 without auth."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/admin/posts", json={
            "title": "Test", "body": {"content": []}, "author_name": "Author"
        })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_post_requires_admin_role():
    """POST /api/admin/posts returns 403 for non-admin users."""
    with patch("app.auth.verify_token", return_value=_non_admin_payload()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/admin/posts",
                json={"title": "Test", "body": {"content": []}, "author_name": "Author"},
                headers=NON_ADMIN_HEADERS,
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_post_success():
    """POST /api/admin/posts creates a post with admin auth."""
    post = _make_post(status=PostStatus.draft)

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        with patch(
            "app.routes.admin.create_post",
            new_callable=AsyncMock,
            return_value=post,
        ) as mock_create:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/admin/posts",
                    json={
                        "title": "Test Post",
                        "body": {"type": "doc", "content": []},
                        "author_name": "Test Author",
                        "excerpt": "A test excerpt",
                    },
                    headers=ADMIN_HEADERS,
                )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Post"
    mock_create.assert_called_once()


# --- PUT /api/admin/posts/{post_id} ---


@pytest.mark.asyncio
async def test_update_post_success():
    """PUT /api/admin/posts/{post_id} updates a post."""
    post_id = uuid.uuid4()
    existing = _make_post(post_id=post_id)
    updated = _make_post(post_id=post_id)
    updated.title = "Updated Title"

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        with patch(
            "app.routes.admin.get_post_by_id",
            new_callable=AsyncMock,
            return_value=existing,
        ):
            with patch(
                "app.routes.admin.update_post",
                new_callable=AsyncMock,
                return_value=updated,
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.put(
                        f"/api/admin/posts/{post_id}",
                        json={"title": "Updated Title"},
                        headers=ADMIN_HEADERS,
                    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_post_not_found():
    """PUT /api/admin/posts/{post_id} returns 404 for non-existent post."""
    post_id = uuid.uuid4()

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        with patch(
            "app.routes.admin.get_post_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    f"/api/admin/posts/{post_id}",
                    json={"title": "Updated Title"},
                    headers=ADMIN_HEADERS,
                )

    assert response.status_code == 404


# --- DELETE /api/admin/posts/{post_id} ---


@pytest.mark.asyncio
async def test_delete_post_success():
    """DELETE /api/admin/posts/{post_id} deletes a post."""
    post_id = uuid.uuid4()
    existing = _make_post(post_id=post_id)

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        with patch(
            "app.routes.admin.get_post_by_id",
            new_callable=AsyncMock,
            return_value=existing,
        ):
            with patch(
                "app.routes.admin.delete_post",
                new_callable=AsyncMock,
                return_value=True,
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.delete(
                        f"/api/admin/posts/{post_id}",
                        headers=ADMIN_HEADERS,
                    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_post_not_found():
    """DELETE /api/admin/posts/{post_id} returns 404 for non-existent post."""
    post_id = uuid.uuid4()

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        with patch(
            "app.routes.admin.get_post_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(
                    f"/api/admin/posts/{post_id}",
                    headers=ADMIN_HEADERS,
                )

    assert response.status_code == 404


# --- PATCH /api/admin/posts/{post_id}/status ---


@pytest.mark.asyncio
async def test_change_status_success():
    """PATCH /api/admin/posts/{post_id}/status changes status."""
    post_id = uuid.uuid4()
    existing = _make_post(post_id=post_id, status=PostStatus.draft)
    published = _make_post(post_id=post_id, status=PostStatus.published)

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        with patch(
            "app.routes.admin.get_post_by_id",
            new_callable=AsyncMock,
            return_value=existing,
        ):
            with patch(
                "app.routes.admin.change_status",
                new_callable=AsyncMock,
                return_value=published,
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.patch(
                        f"/api/admin/posts/{post_id}/status",
                        json={"status": "published"},
                        headers=ADMIN_HEADERS,
                    )

    assert response.status_code == 200
    assert response.json()["status"] == "published"


@pytest.mark.asyncio
async def test_change_status_invalid_value():
    """PATCH /api/admin/posts/{post_id}/status rejects invalid status."""
    post_id = uuid.uuid4()

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/admin/posts/{post_id}/status",
                json={"status": "invalid_status"},
                headers=ADMIN_HEADERS,
            )

    assert response.status_code == 422


# --- PATCH /api/admin/posts/{post_id}/redact ---


@pytest.mark.asyncio
async def test_redact_post_success():
    """PATCH /api/admin/posts/{post_id}/redact marks sections as redacted."""
    post_id = uuid.uuid4()
    existing = _make_post(post_id=post_id)
    redacted = _make_post(post_id=post_id)
    redacted.redacted_sections = [{"start": 0, "end": 10}]

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        with patch(
            "app.routes.admin.get_post_by_id",
            new_callable=AsyncMock,
            return_value=existing,
        ):
            with patch(
                "app.routes.admin.update_post",
                new_callable=AsyncMock,
                return_value=redacted,
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.patch(
                        f"/api/admin/posts/{post_id}/redact",
                        json={"redacted_sections": [{"start": 0, "end": 10}]},
                        headers=ADMIN_HEADERS,
                    )

    assert response.status_code == 200
    assert response.json()["redacted_sections"] == [{"start": 0, "end": 10}]


# --- GET /api/admin/posts ---


@pytest.mark.asyncio
async def test_list_all_posts_requires_auth():
    """GET /api/admin/posts returns 401 without auth."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/posts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_all_posts_success():
    """GET /api/admin/posts returns all posts for admin."""
    paginated = PaginatedPosts(posts=[], total=0, page=1, limit=50, total_pages=0)

    with patch("app.auth.verify_token", return_value=_admin_payload()):
        with patch(
            "app.routes.admin.list_all_posts",
            new_callable=AsyncMock,
            return_value=paginated,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/admin/posts",
                    headers=ADMIN_HEADERS,
                )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["page"] == 1
