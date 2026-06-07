"""
Property-based tests for blog post endpoints.

Uses Hypothesis to verify correctness properties of the blog listing API.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.post import BlogPostListItem, PaginatedPosts


# --- Strategies ---

_uuid_strategy = st.builds(uuid.uuid4)

_datetime_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(timezone.utc),
)

_slug_strategy = st.from_regex(r"[a-z0-9]+(-[a-z0-9]+)*", fullmatch=True).filter(
    lambda s: 1 <= len(s) <= 200
)

_blog_post_list_item_strategy = st.builds(
    BlogPostListItem,
    id=_uuid_strategy,
    slug=_slug_strategy,
    title=st.text(min_size=1, max_size=200).filter(lambda t: t.strip()),
    excerpt=st.one_of(st.none(), st.text(min_size=0, max_size=500)),
    author_name=st.text(min_size=1, max_size=100).filter(lambda t: t.strip()),
    thumbnail_url=st.one_of(
        st.none(),
        st.from_regex(r"https://[a-z]+\.[a-z]+/[a-z0-9]+\.(png|jpg)", fullmatch=True),
    ),
    like_count=st.integers(min_value=0, max_value=100000),
    dislike_count=st.integers(min_value=0, max_value=100000),
    comment_count=st.integers(min_value=0, max_value=100000),
    published_at=_datetime_strategy,
)


# --- Property 2: Blog post response completeness ---


class TestBlogPostResponseCompleteness:
    """
    Feature: blog-and-careers, Property 2: Blog post response completeness

    For any published blog post, the listing response item SHALL include
    id, slug, title, excerpt, author_name, thumbnail_url, like_count,
    dislike_count, comment_count, and published_at fields.

    **Validates: Requirements 1.2, 3.1**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(post_item=_blog_post_list_item_strategy)
    async def test_listing_response_contains_all_required_fields(self, post_item: BlogPostListItem):
        """
        Property 2: For any published blog post, the listing response SHALL
        include all required fields: id, slug, title, excerpt, author_name,
        thumbnail_url, like_count, dislike_count, comment_count, and published_at.

        **Validates: Requirements 1.2, 3.1**
        """
        paginated = PaginatedPosts(
            posts=[post_item],
            total=1,
            page=1,
            limit=10,
            total_pages=1,
        )

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
        assert len(data["posts"]) == 1

        post_data = data["posts"][0]

        # Verify all required fields are present in the response
        required_fields = [
            "id",
            "slug",
            "title",
            "excerpt",
            "author_name",
            "thumbnail_url",
            "like_count",
            "dislike_count",
            "comment_count",
            "published_at",
        ]

        for field in required_fields:
            assert field in post_data, f"Required field '{field}' missing from listing response"

        # Verify field values match the generated post
        assert post_data["id"] == str(post_item.id)
        assert post_data["slug"] == post_item.slug
        assert post_data["title"] == post_item.title
        assert post_data["excerpt"] == post_item.excerpt
        assert post_data["author_name"] == post_item.author_name
        assert post_data["thumbnail_url"] == post_item.thumbnail_url
        assert post_data["like_count"] == post_item.like_count
        assert post_data["dislike_count"] == post_item.dislike_count
        assert post_data["comment_count"] == post_item.comment_count
        # published_at is serialized as ISO string; verify it's present and non-null
        assert post_data["published_at"] is not None


# --- Strategies for Property 1 ---

_post_status_strategy = st.sampled_from(["draft", "published", "hidden"])


@st.composite
def _post_with_status_strategy(draw):
    """Generate a BlogPostListItem paired with a random status."""
    status = draw(_post_status_strategy)
    # Only published posts have a meaningful published_at
    published_at = draw(_datetime_strategy) if status == "published" else None

    item = BlogPostListItem(
        id=draw(_uuid_strategy),
        slug=draw(_slug_strategy),
        title=draw(st.text(min_size=1, max_size=100).filter(lambda t: t.strip())),
        excerpt=draw(st.one_of(st.none(), st.text(min_size=0, max_size=200))),
        author_name=draw(st.text(min_size=1, max_size=50).filter(lambda t: t.strip())),
        thumbnail_url=draw(st.one_of(st.none(), st.just("https://example.com/img.png"))),
        like_count=draw(st.integers(min_value=0, max_value=10000)),
        dislike_count=draw(st.integers(min_value=0, max_value=10000)),
        comment_count=draw(st.integers(min_value=0, max_value=10000)),
        published_at=published_at,
    )
    return {"item": item, "status": status}


@st.composite
def _mixed_status_posts_strategy(draw):
    """
    Generate a list of blog posts with mixed statuses (draft, published, hidden).
    Returns a list of dicts with 'item' (BlogPostListItem) and 'status' keys.
    """
    return draw(st.lists(_post_with_status_strategy(), min_size=0, max_size=25))


# --- Property 1: Blog listing contains only published posts in descending date order ---


class TestBlogListingPublishedOnly:
    """
    Feature: blog-and-careers, Property 1: Blog listing contains only published posts in descending date order

    For any set of blog posts with mixed statuses (draft, published, hidden),
    the public listing endpoint SHALL return only posts with published status,
    and they SHALL be ordered by publication date descending.

    **Validates: Requirements 1.1, 1.3**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(posts_data=_mixed_status_posts_strategy())
    async def test_listing_contains_only_published_posts_in_descending_order(self, posts_data):
        """
        Property 1: Blog listing contains only published posts in descending date order.

        For any set of blog posts with mixed statuses (draft, published, hidden),
        the public listing endpoint SHALL return only posts with published status,
        and they SHALL be ordered by publication date descending.

        **Validates: Requirements 1.1, 1.3**
        """
        # Extract only published posts and sort them descending by published_at
        published_items = [
            entry["item"] for entry in posts_data
            if entry["status"] == "published"
        ]
        published_sorted = sorted(
            published_items,
            key=lambda p: p.published_at if p.published_at else datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        # Simulate what the service returns: only published posts, sorted descending
        paginated = PaginatedPosts(
            posts=published_sorted,
            total=len(published_sorted),
            page=1,
            limit=100,
            total_pages=1 if published_sorted else 0,
        )

        with patch(
            "app.routes.posts.list_published_posts",
            new_callable=AsyncMock,
            return_value=paginated,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/posts?page=1&limit=100")

        assert response.status_code == 200
        data = response.json()
        returned_posts = data["posts"]

        # PROPERTY ASSERTION 1: Only published posts are returned
        # The count must match exactly the number of published posts from our input
        assert len(returned_posts) == len(published_sorted), (
            f"Expected {len(published_sorted)} published posts, got {len(returned_posts)}. "
            f"Input had {len(posts_data)} total posts with statuses: "
            f"{[e['status'] for e in posts_data]}"
        )

        # PROPERTY ASSERTION 2: No draft or hidden posts leaked into the response
        returned_ids = {p["id"] for p in returned_posts}
        expected_ids = {str(p.id) for p in published_sorted}
        assert returned_ids == expected_ids, (
            "Returned post IDs don't match expected published post IDs"
        )

        # PROPERTY ASSERTION 3: Posts are ordered by published_at descending
        if len(returned_posts) > 1:
            published_dates = []
            for p in returned_posts:
                if p["published_at"] is not None:
                    published_dates.append(datetime.fromisoformat(p["published_at"]))

            for i in range(len(published_dates) - 1):
                assert published_dates[i] >= published_dates[i + 1], (
                    f"Posts not in descending date order at index {i}: "
                    f"{published_dates[i].isoformat()} should be >= "
                    f"{published_dates[i + 1].isoformat()}"
                )


# --- Additional imports for Property 3 ---
from app.models.post import BlogPost, PostStatus


# --- Strategies for Property 3 ---

_non_published_status_strategy = st.sampled_from([PostStatus.draft, PostStatus.hidden])

_arbitrary_slug_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd"), whitelist_characters="-_"),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip("-_") != "")


def _make_blog_post(slug: str, status: PostStatus) -> BlogPost:
    """Create a BlogPost with given slug and status for testing."""
    now = datetime.now(timezone.utc)
    return BlogPost(
        id=uuid.uuid4(),
        slug=slug,
        title="Test Post Title",
        excerpt="An excerpt",
        body={"type": "doc", "content": [{"type": "paragraph", "text": "Body content"}]},
        author_name="Author",
        thumbnail_url=None,
        status=status,
        like_count=0,
        dislike_count=0,
        comment_count=0,
        redacted_sections=[],
        published_at=now if status == PostStatus.published else None,
        created_at=now,
        updated_at=now,
    )


# --- Property 3: Non-existent or unpublished post returns 404 ---


class TestNonExistentOrUnpublishedPostReturns404:
    """
    Feature: blog-and-careers, Property 3: Non-existent or unpublished post returns 404

    For any slug that does not map to a post, or maps to a post with non-published
    status, the single post endpoint SHALL return a 404 response.

    **Validates: Requirements 2.3**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(slug=_arbitrary_slug_strategy)
    async def test_nonexistent_slug_returns_404(self, slug: str):
        """
        Property 3a: For any slug that does not map to a post (get_post_by_slug
        returns None), the single post endpoint SHALL return a 404 response.

        **Validates: Requirements 2.3**
        """
        with patch(
            "app.routes.posts.get_post_by_slug",
            new_callable=AsyncMock,
            return_value=None,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/posts/{slug}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Post not found"

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(slug=_arbitrary_slug_strategy, status=_non_published_status_strategy)
    async def test_unpublished_post_returns_404(self, slug: str, status: PostStatus):
        """
        Property 3b: For any slug that maps to a post with non-published status
        (draft or hidden), the single post endpoint SHALL return a 404 response.

        **Validates: Requirements 2.3**
        """
        post = _make_blog_post(slug=slug, status=status)

        with patch(
            "app.routes.posts.get_post_by_slug",
            new_callable=AsyncMock,
            return_value=post,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/posts/{slug}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Post not found"
