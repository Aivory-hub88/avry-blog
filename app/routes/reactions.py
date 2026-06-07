"""
Reaction endpoints for blog posts and comments.

These endpoints are public (no authentication required) and allow
visitors to like/dislike posts and comments using a session identifier.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.models.reaction import ReactionRequest, ReactionResponse
from app.services.reaction_service import (
    dislike_comment,
    dislike_post,
    like_comment,
    like_post,
)

router = APIRouter(tags=["reactions"])


@router.post("/posts/{post_id}/like", response_model=ReactionResponse)
async def post_like(post_id: UUID, body: ReactionRequest) -> ReactionResponse:
    """
    Like a blog post.

    Increments the post's like_count. If the same session has already
    reacted on this post, the existing reaction is returned without
    incrementing the count.
    """
    result = await like_post(post_id, body.session_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to process reaction")
    return result


@router.post("/posts/{post_id}/dislike", response_model=ReactionResponse)
async def post_dislike(post_id: UUID, body: ReactionRequest) -> ReactionResponse:
    """
    Dislike a blog post.

    Increments the post's dislike_count. If the same session has already
    reacted on this post, the existing reaction is returned without
    incrementing the count.
    """
    result = await dislike_post(post_id, body.session_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to process reaction")
    return result


@router.post("/comments/{comment_id}/like", response_model=ReactionResponse)
async def comment_like(comment_id: UUID, body: ReactionRequest) -> ReactionResponse:
    """
    Like a blog comment.

    Increments the comment's like_count. If the same session has already
    reacted on this comment, the existing reaction is returned without
    incrementing the count.
    """
    result = await like_comment(comment_id, body.session_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to process reaction")
    return result


@router.post("/comments/{comment_id}/dislike", response_model=ReactionResponse)
async def comment_dislike(comment_id: UUID, body: ReactionRequest) -> ReactionResponse:
    """
    Dislike a blog comment.

    Increments the comment's dislike_count. If the same session has already
    reacted on this comment, the existing reaction is returned without
    incrementing the count.
    """
    result = await dislike_comment(comment_id, body.session_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to process reaction")
    return result
