"""
Admin blog post endpoints.

All endpoints require admin JWT authentication (admin or superadmin account_type).
Provides full CRUD operations, status management, and redaction for blog posts.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_admin
from app.models.post import (
    BlogPost,
    BlogPostCreate,
    BlogPostUpdate,
    PaginatedPosts,
    PostStatus,
)
from app.services.post_service import (
    change_status,
    create_post,
    delete_post,
    get_post_by_id,
    list_all_posts,
    update_post,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class StatusChange(BaseModel):
    """Request body for changing a post's status."""

    status: PostStatus


class RedactRequest(BaseModel):
    """Request body for marking sections as redacted."""

    redacted_sections: list = Field(default_factory=list)


@router.post("/posts", response_model=BlogPost, status_code=201)
async def admin_create_post(
    data: BlogPostCreate,
    user: dict = Depends(require_admin),
) -> BlogPost:
    """
    Create a new blog post.

    Accepts Rich_Editor JSONB body content. Status defaults to 'draft'
    unless explicitly set to 'published'.
    """
    post = await create_post(
        title=data.title,
        body=data.body,
        author_name=data.author_name,
        excerpt=data.excerpt,
        thumbnail_url=data.thumbnail_url,
        status=data.status.value,
    )
    if post is None:
        raise HTTPException(status_code=500, detail="Failed to create post")
    return post


@router.put("/posts/{post_id}", response_model=BlogPost)
async def admin_update_post(
    post_id: UUID,
    data: BlogPostUpdate,
    user: dict = Depends(require_admin),
) -> BlogPost:
    """
    Edit an existing blog post.

    Only provided (non-None) fields are updated.
    """
    existing = await get_post_by_id(post_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Post not found")

    # Build kwargs from non-None fields
    update_fields = data.model_dump(exclude_none=True)
    if "status" in update_fields:
        update_fields["status"] = update_fields["status"].value

    updated = await update_post(post_id, **update_fields)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to update post")
    return updated


@router.delete("/posts/{post_id}", status_code=204)
async def admin_delete_post(
    post_id: UUID,
    user: dict = Depends(require_admin),
) -> None:
    """
    Permanently delete a blog post.
    """
    existing = await get_post_by_id(post_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Post not found")

    deleted = await delete_post(post_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete post")


@router.patch("/posts/{post_id}/status", response_model=BlogPost)
async def admin_change_status(
    post_id: UUID,
    data: StatusChange,
    user: dict = Depends(require_admin),
) -> BlogPost:
    """
    Change the publication status of a blog post (publish/hide/draft).
    """
    existing = await get_post_by_id(post_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Post not found")

    updated = await change_status(post_id, data.status)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to change status")
    return updated


@router.patch("/posts/{post_id}/redact", response_model=BlogPost)
async def admin_redact_post(
    post_id: UUID,
    data: RedactRequest,
    user: dict = Depends(require_admin),
) -> BlogPost:
    """
    Mark specific sections of a blog post as redacted.
    """
    existing = await get_post_by_id(post_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Post not found")

    updated = await update_post(post_id, redacted_sections=data.redacted_sections)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to redact post")
    return updated


@router.get("/posts", response_model=PaginatedPosts)
async def admin_list_posts(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=50, ge=1, le=100, description="Posts per page"),
    user: dict = Depends(require_admin),
) -> PaginatedPosts:
    """
    List all blog posts regardless of status (admin view).

    Returns posts ordered by creation date descending.
    """
    return await list_all_posts(page=page, limit=limit)
