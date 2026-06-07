"""
Public blog post endpoints.

These endpoints are accessible without authentication and serve
published blog content to visitors.
"""

from fastapi import APIRouter, HTTPException, Query

from app.models.post import BlogPost, PaginatedPosts, PostStatus
from app.services.post_service import get_post_by_slug, list_published_posts

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=PaginatedPosts)
async def get_posts(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=10, ge=1, le=100, description="Posts per page"),
) -> PaginatedPosts:
    """
    Retrieve a paginated list of published blog posts.

    Posts are ordered by publication date descending. Only posts with
    'published' status are included.
    """
    return await list_published_posts(page=page, limit=limit)


@router.get("/{slug}", response_model=BlogPost)
async def get_post(slug: str) -> BlogPost:
    """
    Retrieve a single blog post by its slug.

    Returns 404 if the post does not exist or is not published.
    """
    post = await get_post_by_slug(slug)

    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.status != PostStatus.published:
        raise HTTPException(status_code=404, detail="Post not found")

    return post
