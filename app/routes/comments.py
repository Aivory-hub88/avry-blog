"""
Comment and reply endpoints for the avry-blog service.

These endpoints are public (no authentication required) and allow
visitors to view threaded comments on posts and submit new comments/replies.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.models.comment import Comment, CommentCreate
from app.services.comment_service import (
    create_comment,
    create_reply,
    list_comments_for_post,
)

router = APIRouter(tags=["comments"])


@router.get("/posts/{post_id}/comments", response_model=list[Comment])
async def get_comments(post_id: UUID) -> list[Comment]:
    """
    Retrieve threaded comments for a blog post.

    Returns a list of top-level comments, each with nested replies.
    """
    comments = await list_comments_for_post(post_id)
    return comments


@router.post("/posts/{post_id}/comments", response_model=Comment, status_code=201)
async def add_comment(post_id: UUID, payload: CommentCreate) -> Comment:
    """
    Add a new top-level comment to a blog post.

    Requires author_name and body in the request body.
    Returns 404 if the post does not exist.
    """
    comment = await create_comment(
        post_id=post_id,
        author_name=payload.author_name,
        body=payload.body,
    )

    if comment is None:
        raise HTTPException(status_code=404, detail="Post not found")

    return comment


@router.post("/comments/{comment_id}/reply", response_model=Comment, status_code=201)
async def reply_to_comment(comment_id: UUID, payload: CommentCreate) -> Comment:
    """
    Reply to an existing comment.

    Requires author_name and body in the request body.
    Returns 404 if the parent comment does not exist.
    """
    reply = await create_reply(
        comment_id=comment_id,
        author_name=payload.author_name,
        body=payload.body,
    )

    if reply is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    return reply
