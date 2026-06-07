"""Unit tests for blog post models and slug generation."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.models.post import (
    BlogPost,
    BlogPostCreate,
    BlogPostUpdate,
    BlogPostListItem,
    PaginatedPosts,
    PostStatus,
)
from app.services.post_service import generate_slug


class TestPostStatus:
    """Tests for the PostStatus enum."""

    def test_enum_values(self):
        assert PostStatus.draft.value == "draft"
        assert PostStatus.published.value == "published"
        assert PostStatus.hidden.value == "hidden"

    def test_enum_from_string(self):
        assert PostStatus("draft") == PostStatus.draft
        assert PostStatus("published") == PostStatus.published
        assert PostStatus("hidden") == PostStatus.hidden

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError):
            PostStatus("invalid")


class TestSlugGeneration:
    """Tests for the generate_slug function."""

    def test_basic_title(self):
        assert generate_slug("Hello World") == "hello-world"

    def test_uppercase(self):
        assert generate_slug("UPPERCASE Title") == "uppercase-title"

    def test_special_characters_stripped(self):
        assert generate_slug("Hello! @World#") == "hello-world"

    def test_multiple_spaces_collapse(self):
        assert generate_slug("A  B  C") == "a-b-c"

    def test_leading_trailing_dashes_stripped(self):
        assert generate_slug("---hello---") == "hello"

    def test_numbers_preserved(self):
        assert generate_slug("123 Numbers") == "123-numbers"

    def test_empty_after_strip(self):
        # Title with only special characters produces empty slug
        assert generate_slug("@#$%^&*") == ""

    def test_long_title(self):
        title = "This Is A Very Long Blog Post Title With Many Words"
        slug = generate_slug(title)
        assert slug == "this-is-a-very-long-blog-post-title-with-many-words"


class TestBlogPostModel:
    """Tests for the BlogPost pydantic model."""

    def test_create_full_post(self):
        now = datetime.now(timezone.utc)
        post = BlogPost(
            id=uuid4(),
            slug="test-post",
            title="Test Post",
            excerpt="An excerpt",
            body={"type": "doc", "content": []},
            author_name="Author",
            thumbnail_url="https://example.com/img.jpg",
            status=PostStatus.published,
            like_count=5,
            dislike_count=1,
            comment_count=3,
            redacted_sections=[],
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        assert post.title == "Test Post"
        assert post.status == PostStatus.published
        assert post.like_count == 5

    def test_defaults(self):
        now = datetime.now(timezone.utc)
        post = BlogPost(
            id=uuid4(),
            slug="test",
            title="Test",
            body={"content": "hello"},
            author_name="Author",
            created_at=now,
            updated_at=now,
        )
        assert post.status == PostStatus.draft
        assert post.like_count == 0
        assert post.dislike_count == 0
        assert post.comment_count == 0
        assert post.redacted_sections == []
        assert post.excerpt is None
        assert post.thumbnail_url is None
        assert post.published_at is None


class TestBlogPostCreate:
    """Tests for the BlogPostCreate request model."""

    def test_valid_create(self):
        req = BlogPostCreate(
            title="New Post",
            body={"content": "test"},
            author_name="Admin",
        )
        assert req.title == "New Post"
        assert req.status == PostStatus.draft

    def test_with_optional_fields(self):
        req = BlogPostCreate(
            title="Post",
            body={"content": "test"},
            author_name="Admin",
            excerpt="Short",
            thumbnail_url="https://img.com/thumb.png",
            status=PostStatus.published,
        )
        assert req.excerpt == "Short"
        assert req.status == PostStatus.published

    def test_empty_title_rejected(self):
        with pytest.raises(Exception):
            BlogPostCreate(
                title="",
                body={"content": "test"},
                author_name="Admin",
            )

    def test_empty_author_rejected(self):
        with pytest.raises(Exception):
            BlogPostCreate(
                title="Valid",
                body={"content": "test"},
                author_name="",
            )


class TestBlogPostUpdate:
    """Tests for the BlogPostUpdate request model."""

    def test_all_none_is_valid(self):
        req = BlogPostUpdate()
        assert req.title is None
        assert req.body is None

    def test_partial_update(self):
        req = BlogPostUpdate(title="Updated", status=PostStatus.hidden)
        assert req.title == "Updated"
        assert req.status == PostStatus.hidden
        assert req.body is None


class TestPaginatedPosts:
    """Tests for the PaginatedPosts response model."""

    def test_empty_listing(self):
        paginated = PaginatedPosts(
            posts=[], total=0, page=1, limit=10, total_pages=0
        )
        assert len(paginated.posts) == 0
        assert paginated.total_pages == 0

    def test_with_posts(self):
        now = datetime.now(timezone.utc)
        items = [
            BlogPostListItem(
                id=uuid4(),
                slug=f"post-{i}",
                title=f"Post {i}",
                author_name="Author",
                published_at=now,
            )
            for i in range(3)
        ]
        paginated = PaginatedPosts(
            posts=items, total=15, page=1, limit=3, total_pages=5
        )
        assert len(paginated.posts) == 3
        assert paginated.total == 15
        assert paginated.total_pages == 5
