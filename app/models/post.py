"""
Blog post models and enums.

Defines the BlogPost pydantic model, PostStatus enum, and request/response schemas
for blog post CRUD operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PostStatus(str, Enum):
    """Blog post publication status."""

    draft = "draft"
    published = "published"
    hidden = "hidden"


class BlogPost(BaseModel):
    """Full blog post model matching the database schema."""

    id: UUID
    slug: str
    title: str
    excerpt: Optional[str] = None
    body: Any  # JSONB - structured rich editor content
    author_name: str
    thumbnail_url: Optional[str] = None
    status: PostStatus = PostStatus.draft
    like_count: int = 0
    dislike_count: int = 0
    comment_count: int = 0
    redacted_sections: list[Any] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class BlogPostListItem(BaseModel):
    """Blog post item for public listing (subset of fields)."""

    id: UUID
    slug: str
    title: str
    excerpt: Optional[str] = None
    author_name: str
    thumbnail_url: Optional[str] = None
    like_count: int = 0
    dislike_count: int = 0
    comment_count: int = 0
    published_at: Optional[datetime] = None


class BlogPostCreate(BaseModel):
    """Request body for creating a blog post."""

    title: str = Field(..., min_length=1, max_length=500)
    body: Any  # JSONB rich editor content
    author_name: str = Field(..., min_length=1, max_length=255)
    excerpt: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: PostStatus = PostStatus.draft


class BlogPostUpdate(BaseModel):
    """Request body for updating a blog post (all fields optional)."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    body: Optional[Any] = None
    author_name: Optional[str] = Field(None, min_length=1, max_length=255)
    excerpt: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: Optional[PostStatus] = None
    redacted_sections: Optional[list[Any]] = None


class PaginatedPosts(BaseModel):
    """Paginated response for blog post listings."""

    posts: list[BlogPostListItem]
    total: int
    page: int
    limit: int
    total_pages: int
