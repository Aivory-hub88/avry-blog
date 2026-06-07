"""
Reaction models.

Defines the Reaction pydantic model and request schema for blog post
and comment reactions (likes/dislikes) with session-based uniqueness.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TargetType(str, Enum):
    """Target type for a reaction."""

    post = "post"
    comment = "comment"


class ReactionType(str, Enum):
    """Type of reaction."""

    like = "like"
    dislike = "dislike"


class Reaction(BaseModel):
    """Full reaction model matching the database schema."""

    id: UUID
    target_type: TargetType
    target_id: UUID
    reaction_type: ReactionType
    session_id: str
    created_at: datetime


class ReactionRequest(BaseModel):
    """Request body for submitting a reaction."""

    session_id: str = Field(..., min_length=1, max_length=255)


class ReactionResponse(BaseModel):
    """Response after a reaction is submitted."""

    reaction: Reaction
    updated_count: int
    is_duplicate: bool = False
