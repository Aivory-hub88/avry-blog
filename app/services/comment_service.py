"""
Comment service - business logic for comment and reply operations.

Handles creating top-level comments, creating replies (threaded via parent_id),
listing comments with threaded structure, and incrementing blog_posts.comment_count.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from app.database.connection import get_pool
from app.models.comment import Comment

logger = logging.getLogger(__name__)


def _row_to_comment(row: asyncpg.Record) -> Comment:
    """Convert a database row to a Comment model (without replies populated)."""
    return Comment(
        id=row["id"],
        post_id=row["post_id"],
        parent_id=row["parent_id"],
        author_name=row["author_name"],
        body=row["body"],
        like_count=row["like_count"],
        dislike_count=row["dislike_count"],
        created_at=row["created_at"],
        replies=[],
    )


async def create_comment(
    post_id: uuid.UUID, author_name: str, body: str
) -> Optional[Comment]:
    """
    Create a top-level comment on a blog post.

    Persists the comment with parent_id=NULL and increments the
    blog_posts.comment_count for the associated post.

    Returns the created Comment or None if the database is unavailable.
    """
    pool = await get_pool()
    if pool is None:
        logger.error("Database pool not available")
        return None

    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO blog_comments (post_id, parent_id, author_name, body, created_at)
                VALUES ($1, NULL, $2, $3, $4)
                RETURNING *
                """,
                post_id,
                author_name,
                body,
                now,
            )

            # Increment comment_count on the associated blog post
            await conn.execute(
                """
                UPDATE blog_posts
                SET comment_count = comment_count + 1
                WHERE id = $1
                """,
                post_id,
            )

    if row is None:
        return None

    return _row_to_comment(row)


async def create_reply(
    comment_id: uuid.UUID, author_name: str, body: str
) -> Optional[Comment]:
    """
    Create a reply to an existing comment.

    Looks up the parent comment to determine the post_id, then persists
    the reply with parent_id set and increments blog_posts.comment_count.

    Returns the created reply Comment or None if the parent comment
    doesn't exist or the database is unavailable.
    """
    pool = await get_pool()
    if pool is None:
        logger.error("Database pool not available")
        return None

    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        # Look up the parent comment to get the post_id
        parent_row = await conn.fetchrow(
            "SELECT id, post_id FROM blog_comments WHERE id = $1",
            comment_id,
        )

        if parent_row is None:
            logger.warning(f"Parent comment {comment_id} not found")
            return None

        post_id = parent_row["post_id"]

        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO blog_comments (post_id, parent_id, author_name, body, created_at)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                post_id,
                comment_id,
                author_name,
                body,
                now,
            )

            # Increment comment_count on the associated blog post
            await conn.execute(
                """
                UPDATE blog_posts
                SET comment_count = comment_count + 1
                WHERE id = $1
                """,
                post_id,
            )

    if row is None:
        return None

    return _row_to_comment(row)


async def list_comments_for_post(post_id: uuid.UUID) -> list[Comment]:
    """
    List all comments for a blog post with threaded structure.

    Fetches all comments for the post, groups them by parent_id,
    and builds a tree with top-level comments containing nested replies.

    Returns a list of top-level comments, each with their replies populated.
    """
    pool = await get_pool()
    if pool is None:
        return []

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM blog_comments
            WHERE post_id = $1
            ORDER BY created_at ASC
            """,
            post_id,
        )

    if not rows:
        return []

    # Convert all rows to Comment models
    comments_by_id: dict[uuid.UUID, Comment] = {}
    for row in rows:
        comment = _row_to_comment(row)
        comments_by_id[comment.id] = comment

    # Build the tree: attach replies to their parent comments
    top_level: list[Comment] = []
    for comment in comments_by_id.values():
        if comment.parent_id is None:
            top_level.append(comment)
        else:
            parent = comments_by_id.get(comment.parent_id)
            if parent is not None:
                parent.replies.append(comment)
            else:
                # Orphaned reply (parent deleted) — treat as top-level
                top_level.append(comment)

    return top_level
