"""
Reaction service - business logic for post and comment reactions.

Handles like/dislike operations for both blog posts and comments,
including duplicate detection via the unique constraint on
(target_type, target_id, session_id) and count updates.
"""

import logging
from typing import Optional
from uuid import UUID

import asyncpg

from app.database.connection import get_pool
from app.models.reaction import Reaction, ReactionResponse, ReactionType, TargetType

logger = logging.getLogger(__name__)


def _row_to_reaction(row: asyncpg.Record) -> Reaction:
    """Convert a database row to a Reaction model."""
    return Reaction(
        id=row["id"],
        target_type=TargetType(row["target_type"]),
        target_id=row["target_id"],
        reaction_type=ReactionType(row["reaction_type"]),
        session_id=row["session_id"],
        created_at=row["created_at"],
    )


async def _insert_reaction(
    target_type: TargetType,
    target_id: UUID,
    reaction_type: ReactionType,
    session_id: str,
) -> tuple[Reaction, bool]:
    """
    Insert a reaction into blog_reactions.

    Returns a tuple of (reaction, is_new). If the unique constraint is violated
    (same session already reacted on this target), returns the existing reaction
    with is_new=False.
    """
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("Database pool not available")

    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO blog_reactions (target_type, target_id, reaction_type, session_id)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                target_type.value,
                target_id,
                reaction_type.value,
                session_id,
            )
            return _row_to_reaction(row), True
        except asyncpg.UniqueViolationError:
            # Duplicate: session already reacted on this target
            existing = await conn.fetchrow(
                """
                SELECT * FROM blog_reactions
                WHERE target_type = $1 AND target_id = $2 AND session_id = $3
                """,
                target_type.value,
                target_id,
                session_id,
            )
            return _row_to_reaction(existing), False


async def _get_post_count(post_id: UUID, count_column: str) -> int:
    """Get the current like_count or dislike_count for a post."""
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("Database pool not available")

    async with pool.acquire() as conn:
        return await conn.fetchval(
            f"SELECT {count_column} FROM blog_posts WHERE id = $1",
            post_id,
        )


async def _get_comment_count(comment_id: UUID, count_column: str) -> int:
    """Get the current like_count or dislike_count for a comment."""
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("Database pool not available")

    async with pool.acquire() as conn:
        return await conn.fetchval(
            f"SELECT {count_column} FROM blog_comments WHERE id = $1",
            comment_id,
        )


async def like_post(post_id: UUID, session_id: str) -> Optional[ReactionResponse]:
    """
    Like a blog post.

    Inserts a reaction and increments blog_posts.like_count.
    On duplicate (same session_id already reacted), returns the existing
    reaction without incrementing the count.
    """
    pool = await get_pool()
    if pool is None:
        logger.error("Database pool not available")
        return None

    reaction, is_new = await _insert_reaction(
        TargetType.post, post_id, ReactionType.like, session_id
    )

    if is_new:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE blog_posts SET like_count = like_count + 1 WHERE id = $1",
                post_id,
            )

    updated_count = await _get_post_count(post_id, "like_count")

    return ReactionResponse(
        reaction=reaction,
        updated_count=updated_count,
        is_duplicate=not is_new,
    )


async def dislike_post(post_id: UUID, session_id: str) -> Optional[ReactionResponse]:
    """
    Dislike a blog post.

    Inserts a reaction and increments blog_posts.dislike_count.
    On duplicate (same session_id already reacted), returns the existing
    reaction without incrementing the count.
    """
    pool = await get_pool()
    if pool is None:
        logger.error("Database pool not available")
        return None

    reaction, is_new = await _insert_reaction(
        TargetType.post, post_id, ReactionType.dislike, session_id
    )

    if is_new:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE blog_posts SET dislike_count = dislike_count + 1 WHERE id = $1",
                post_id,
            )

    updated_count = await _get_post_count(post_id, "dislike_count")

    return ReactionResponse(
        reaction=reaction,
        updated_count=updated_count,
        is_duplicate=not is_new,
    )


async def like_comment(
    comment_id: UUID, session_id: str
) -> Optional[ReactionResponse]:
    """
    Like a blog comment.

    Inserts a reaction and increments blog_comments.like_count.
    On duplicate (same session_id already reacted), returns the existing
    reaction without incrementing the count.
    """
    pool = await get_pool()
    if pool is None:
        logger.error("Database pool not available")
        return None

    reaction, is_new = await _insert_reaction(
        TargetType.comment, comment_id, ReactionType.like, session_id
    )

    if is_new:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE blog_comments SET like_count = like_count + 1 WHERE id = $1",
                comment_id,
            )

    updated_count = await _get_comment_count(comment_id, "like_count")

    return ReactionResponse(
        reaction=reaction,
        updated_count=updated_count,
        is_duplicate=not is_new,
    )


async def dislike_comment(
    comment_id: UUID, session_id: str
) -> Optional[ReactionResponse]:
    """
    Dislike a blog comment.

    Inserts a reaction and increments blog_comments.dislike_count.
    On duplicate (same session_id already reacted), returns the existing
    reaction without incrementing the count.
    """
    pool = await get_pool()
    if pool is None:
        logger.error("Database pool not available")
        return None

    reaction, is_new = await _insert_reaction(
        TargetType.comment, comment_id, ReactionType.dislike, session_id
    )

    if is_new:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE blog_comments SET dislike_count = dislike_count + 1 WHERE id = $1",
                comment_id,
            )

    updated_count = await _get_comment_count(comment_id, "dislike_count")

    return ReactionResponse(
        reaction=reaction,
        updated_count=updated_count,
        is_duplicate=not is_new,
    )
