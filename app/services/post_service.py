"""
Post service - business logic for blog post CRUD operations.

Handles slug generation, pagination, status filtering, and all database
interactions for blog posts.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from app.database.connection import get_pool
from app.models.post import (
    BlogPost,
    BlogPostListItem,
    PaginatedPosts,
    PostStatus,
)

logger = logging.getLogger(__name__)


def generate_slug(title: str) -> str:
    """
    Generate a URL-friendly slug from a title.

    - Lowercase the title
    - Replace spaces with dashes
    - Strip special characters (keep only alphanumeric and dashes)
    - Collapse multiple dashes into one
    - Strip leading/trailing dashes
    """
    slug = title.lower()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug


async def _ensure_unique_slug(slug: str, pool: asyncpg.Pool) -> str:
    """
    Check if a slug already exists in the database.
    If it does, append a short UUID suffix to make it unique.
    """
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM blog_posts WHERE slug = $1", slug
        )
        if existing is not None:
            suffix = uuid.uuid4().hex[:8]
            slug = f"{slug}-{suffix}"
    return slug


def _row_to_blog_post(row: asyncpg.Record) -> BlogPost:
    """Convert a database row to a BlogPost model."""
    return BlogPost(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        excerpt=row["excerpt"],
        body=json.loads(row["body"]) if isinstance(row["body"], str) else row["body"],
        author_name=row["author_name"],
        thumbnail_url=row["thumbnail_url"],
        status=PostStatus(row["status"]),
        like_count=row["like_count"],
        dislike_count=row["dislike_count"],
        comment_count=row["comment_count"],
        redacted_sections=(
            json.loads(row["redacted_sections"])
            if isinstance(row["redacted_sections"], str)
            else row["redacted_sections"]
        )
        if row["redacted_sections"]
        else [],
        published_at=row["published_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_list_item(row: asyncpg.Record) -> BlogPostListItem:
    """Convert a database row to a BlogPostListItem model."""
    return BlogPostListItem(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        excerpt=row["excerpt"],
        author_name=row["author_name"],
        thumbnail_url=row["thumbnail_url"],
        like_count=row["like_count"],
        dislike_count=row["dislike_count"],
        comment_count=row["comment_count"],
        published_at=row["published_at"],
    )


async def create_post(
    title: str,
    body: Any,
    author_name: str,
    excerpt: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    status: str = "draft",
) -> Optional[BlogPost]:
    """
    Create a new blog post.

    Generates a slug from the title, ensures uniqueness, and persists to the database.
    If status is 'published', sets published_at to current time.
    """
    pool = await get_pool()
    if pool is None:
        logger.error("Database pool not available")
        return None

    slug = generate_slug(title)
    if not slug:
        # Fallback for titles that produce empty slugs
        slug = uuid.uuid4().hex[:12]
    slug = await _ensure_unique_slug(slug, pool)

    now = datetime.now(timezone.utc)
    published_at = now if status == PostStatus.published.value else None

    # Serialize body to JSON string for JSONB column
    body_json = json.dumps(body) if not isinstance(body, str) else body

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO blog_posts (slug, title, excerpt, body, author_name, thumbnail_url, status, published_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $9)
            RETURNING *
            """,
            slug,
            title,
            excerpt,
            body_json,
            author_name,
            thumbnail_url,
            status,
            published_at,
            now,
        )

    if row is None:
        return None

    return _row_to_blog_post(row)


async def get_post_by_slug(slug: str) -> Optional[BlogPost]:
    """Retrieve a blog post by its slug. Returns None if not found."""
    pool = await get_pool()
    if pool is None:
        return None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM blog_posts WHERE slug = $1", slug
        )

    if row is None:
        return None

    return _row_to_blog_post(row)


async def get_post_by_id(post_id: uuid.UUID) -> Optional[BlogPost]:
    """Retrieve a blog post by its ID. Returns None if not found."""
    pool = await get_pool()
    if pool is None:
        return None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM blog_posts WHERE id = $1", post_id
        )

    if row is None:
        return None

    return _row_to_blog_post(row)


async def list_published_posts(page: int = 1, limit: int = 10) -> PaginatedPosts:
    """
    List published blog posts with pagination.

    Returns posts ordered by published_at DESC, filtered to only published status.
    Page is 1-indexed.
    """
    pool = await get_pool()
    if pool is None:
        return PaginatedPosts(posts=[], total=0, page=page, limit=limit, total_pages=0)

    # Clamp values
    page = max(1, page)
    limit = max(1, min(100, limit))
    offset = (page - 1) * limit

    async with pool.acquire() as conn:
        # Get total count of published posts
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM blog_posts WHERE status = $1",
            PostStatus.published.value,
        )

        # Get paginated results
        rows = await conn.fetch(
            """
            SELECT id, slug, title, excerpt, author_name, thumbnail_url,
                   like_count, dislike_count, comment_count, published_at
            FROM blog_posts
            WHERE status = $1
            ORDER BY published_at DESC
            LIMIT $2 OFFSET $3
            """,
            PostStatus.published.value,
            limit,
            offset,
        )

    posts = [_row_to_list_item(row) for row in rows]
    total_pages = (total + limit - 1) // limit if total > 0 else 0

    return PaginatedPosts(
        posts=posts,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


async def list_all_posts(page: int = 1, limit: int = 50) -> PaginatedPosts:
    """
    List all blog posts regardless of status (admin use).

    Returns posts ordered by created_at DESC with pagination.
    Page is 1-indexed.
    """
    pool = await get_pool()
    if pool is None:
        return PaginatedPosts(posts=[], total=0, page=page, limit=limit, total_pages=0)

    page = max(1, page)
    limit = max(1, min(100, limit))
    offset = (page - 1) * limit

    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM blog_posts")

        rows = await conn.fetch(
            """
            SELECT id, slug, title, excerpt, author_name, thumbnail_url,
                   like_count, dislike_count, comment_count, published_at
            FROM blog_posts
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    posts = [_row_to_list_item(row) for row in rows]
    total_pages = (total + limit - 1) // limit if total > 0 else 0

    return PaginatedPosts(
        posts=posts,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


async def update_post(post_id: uuid.UUID, **fields) -> Optional[BlogPost]:
    """
    Update a blog post by ID with the provided fields.

    Only non-None fields are updated. Automatically updates the updated_at timestamp.
    If status is changed to 'published' and published_at is not set, sets it.
    """
    pool = await get_pool()
    if pool is None:
        return None

    # Build the SET clause dynamically from provided fields
    allowed_fields = {
        "title", "body", "author_name", "excerpt", "thumbnail_url",
        "status", "redacted_sections",
    }

    set_clauses = []
    values = []
    param_index = 1

    for field_name, value in fields.items():
        if field_name not in allowed_fields or value is None:
            continue

        if field_name == "body":
            value = json.dumps(value) if not isinstance(value, str) else value
            set_clauses.append(f"body = ${param_index}::jsonb")
        elif field_name == "redacted_sections":
            value = json.dumps(value) if not isinstance(value, str) else value
            set_clauses.append(f"redacted_sections = ${param_index}::jsonb")
        else:
            set_clauses.append(f"{field_name} = ${param_index}")

        values.append(value)
        param_index += 1

    if not set_clauses:
        # Nothing to update, just return the existing post
        return await get_post_by_id(post_id)

    # Always update updated_at
    set_clauses.append(f"updated_at = ${param_index}")
    values.append(datetime.now(timezone.utc))
    param_index += 1

    # If publishing, set published_at if not already set
    if fields.get("status") == PostStatus.published.value:
        set_clauses.append(
            f"published_at = COALESCE(published_at, ${param_index})"
        )
        values.append(datetime.now(timezone.utc))
        param_index += 1

    # Add the post_id as the last parameter for the WHERE clause
    values.append(post_id)

    query = f"""
        UPDATE blog_posts
        SET {', '.join(set_clauses)}
        WHERE id = ${param_index}
        RETURNING *
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *values)

    if row is None:
        return None

    return _row_to_blog_post(row)


async def delete_post(post_id: uuid.UUID) -> bool:
    """
    Delete a blog post by ID.

    Returns True if the post was deleted, False if it didn't exist.
    """
    pool = await get_pool()
    if pool is None:
        return False

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM blog_posts WHERE id = $1", post_id
        )

    # asyncpg execute returns a status string like "DELETE 1"
    return result == "DELETE 1"


async def change_status(
    post_id: uuid.UUID, new_status: PostStatus
) -> Optional[BlogPost]:
    """
    Change the status of a blog post.

    If changing to 'published', sets published_at if not already set.
    Returns the updated post or None if not found.
    """
    return await update_post(post_id, status=new_status.value)
