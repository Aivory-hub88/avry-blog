"""Unit tests for public blog post endpoints."""

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


def _make_post(status: PostStatus = PostStatus.published, slug: str = "test-post") -> BlogPost:
    """Create a BlogPost instance for testing."""
    now = datetime.now(timezone.utc)
    return BlogPost(
        id=uuid.uuid4(),
        slug=slug,
        title="Test Post",
        excerpt="A test excerpt",
        body={"type": "doc", "content": [{"type": "paragraph", "text": "Hello"}]},
        author_name="Test Author",
        thumbnail_url="https://example.com/img.png",
        status=status,
        like_count=5,
        dislike_count=1,
        comment_count=3,
        redacted_sections=[],
        published_at=now,
        created_at=now,
        updated_at=now,
    )


def _make_list_item() -> BlogPostListItem:
    """Create a BlogPostListItem for testing."""
    now = datetime.now(timezone.utc)
    return BlogPostListItem(
        id=uuid.uuid4(),
        slug="test-post",
        title="Test Post",
        excerpt="A test excerpt",
        author_name="Test Author",
        thumbnail_url="https://example.com/img.png",
        like_count=5,
        dislike_count=1,
        comment_count=3,
        published_at=now,
    )


@pytest.mark.asyncio
async def test_get_posts_returns_paginated_results():
    """GET /api/posts returns paginated published posts."""
    items = [_make_list_item()]
    paginated = PaginatedPosts(posts=items, total=1, page=1, limit=10, total_pages=1)

    with patch(
        "app.routes.posts.list_published_posts",
        new_callable=AsyncMock,
        return_value=paginated,
    ) as mock_list:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/posts")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["limit"] == 10
    assert data["total_pages"] == 1
    assert len(data["posts"]) == 1
    assert data["posts"][0]["title"] == "Test Post"
    mock_list.assert_called_once_with(page=1, limit=10)


@pytest.mark.asyncio
async def test_get_posts_respects_pagination_params():
    """GET /api/posts passes page and limit params to service."""
    paginated = PaginatedPosts(posts=[], total=0, page=3, limit=5, total_pages=0)

    with patch(
        "app.routes.posts.list_published_posts",
        new_callable=AsyncMock,
        return_value=paginated,
    ) as mock_list:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/posts?page=3&limit=5")

    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 3
    assert data["limit"] == 5
    mock_list.assert_called_once_with(page=3, limit=5)


@pytest.mark.asyncio
async def test_get_posts_empty_listing():
    """GET /api/posts returns empty list when no published posts exist."""
    paginated = PaginatedPosts(posts=[], total=0, page=1, limit=10, total_pages=0)

    with patch(
        "app.routes.posts.list_published_posts",
        new_callable=AsyncMock,
        return_value=paginated,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/posts")

    assert response.status_code == 200
    data = response.json()
    assert data["posts"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_post_by_slug_returns_published_post():
    """GET /api/posts/{slug} returns a published post."""
    post = _make_post(status=PostStatus.published, slug="my-post")

    with patch(
        "app.routes.posts.get_post_by_slug",
        new_callable=AsyncMock,
        return_value=post,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/posts/my-post")

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "my-post"
    assert data["title"] == "Test Post"
    assert data["author_name"] == "Test Author"


@pytest.mark.asyncio
async def test_get_post_by_slug_returns_404_when_not_found():
    """GET /api/posts/{slug} returns 404 for non-existent slug."""
    with patch(
        "app.routes.posts.get_post_by_slug",
        new_callable=AsyncMock,
        return_value=None,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/posts/nonexistent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Post not found"


@pytest.mark.asyncio
async def test_get_post_by_slug_returns_404_for_draft_post():
    """GET /api/posts/{slug} returns 404 for draft posts."""
    post = _make_post(status=PostStatus.draft, slug="draft-post")

    with patch(
        "app.routes.posts.get_post_by_slug",
        new_callable=AsyncMock,
        return_value=post,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/posts/draft-post")

    assert response.status_code == 404
    assert response.json()["detail"] == "Post not found"


@pytest.mark.asyncio
async def test_get_post_by_slug_returns_404_for_hidden_post():
    """GET /api/posts/{slug} returns 404 for hidden posts."""
    post = _make_post(status=PostStatus.hidden, slug="hidden-post")

    with patch(
        "app.routes.posts.get_post_by_slug",
        new_callable=AsyncMock,
        return_value=post,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/posts/hidden-post")

    assert response.status_code == 404
    assert response.json()["detail"] == "Post not found"
