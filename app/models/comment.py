"""
Comment models for the avry-blog service.

Defines the Comment pydantic model with threaded reply support,
and request schemas for creating comments and replies.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class Comment(BaseModel):
    """Comment model matching the blog_comments database schema."""

    id: UUID
    post_id: UUID
    parent_id: Optional[UUID] = None
    author_name: str
    body: str
    like_count: int = 0
    dislike_count: int = 0
    created_at: datetime
    replies: list["Comment"] = Field(default_factory=list)


class CommentCreate(BaseModel):
    """Request body for creating a comment or reply."""

    author_name: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
