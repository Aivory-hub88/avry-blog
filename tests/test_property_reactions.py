"""
Property-based tests for blog reaction incrementing logic.

Uses Hypothesis to verify that liking/disliking posts and comments correctly
increments the reaction count, and that duplicate reactions (same session_id)
do not increment counts.

Feature: blog-and-careers, Property 4: Reactions increment correctly
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

import asyncpg

from app.models.reaction import ReactionType, TargetType
from app.services.reaction_service import (
    like_post,
    dislike_post,
    like_comment,
    dislike_comment,
)


# --- Strategies ---

_initial_count_strategy = st.integers(min_value=0, max_value=10000)

_session_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() != "")


class _FakeRecord(dict):
    """A dict subclass that supports key access like asyncpg.Record."""

    def __getitem__(self, key):
        return super().__getitem__(key)


def _make_reaction_row(target_type: str, target_id, reaction_type: str, session_id: str):
    """Create a fake reaction database row."""
    return _FakeRecord({
        "id": uuid.uuid4(),
        "target_type": target_type,
        "target_id": target_id,
        "reaction_type": reaction_type,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc),
    })


# --- Property 4: Reactions increment correctly ---


class TestReactionsIncrementCorrectly:
    """
    Feature: blog-and-careers, Property 4: Reactions increment correctly

    For any blog post or comment with an initial reaction count N, submitting
    a like SHALL result in a like_count of N+1, and submitting a dislike SHALL
    result in a dislike_count of N+1.

    **Validates: Requirements 3.2, 3.3, 3.6**
    """

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        initial_count=_initial_count_strategy,
        session_id=_session_id_strategy,
    )
    async def test_like_post_increments_count(self, initial_count, session_id):
        """
        Property 4: For any blog post with initial like_count N and a unique
        session_id, submitting a like SHALL result in updated_count of N+1
        and is_duplicate SHALL be False.

        **Validates: Requirements 3.2**
        """
        post_id = uuid.uuid4()
        expected_new_count = initial_count + 1

        reaction_row = _make_reaction_row("post", post_id, "like", session_id)

        # Mock connection that handles INSERT (success) and UPDATE + SELECT
        mock_conn = AsyncMock()
        # INSERT succeeds (new reaction)
        mock_conn.fetchrow = AsyncMock(return_value=reaction_row)
        # UPDATE increments the count
        mock_conn.execute = AsyncMock(return_value=None)
        # SELECT returns N+1
        mock_conn.fetchval = AsyncMock(return_value=expected_new_count)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.reaction_service.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await like_post(post_id, session_id)

        assert result is not None
        assert result.updated_count == expected_new_count
        assert result.is_duplicate is False

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        initial_count=_initial_count_strategy,
        session_id=_session_id_strategy,
    )
    async def test_dislike_post_increments_count(self, initial_count, session_id):
        """
        Property 4: For any blog post with initial dislike_count N and a unique
        session_id, submitting a dislike SHALL result in updated_count of N+1
        and is_duplicate SHALL be False.

        **Validates: Requirements 3.3**
        """
        post_id = uuid.uuid4()
        expected_new_count = initial_count + 1

        reaction_row = _make_reaction_row("post", post_id, "dislike", session_id)

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=reaction_row)
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.fetchval = AsyncMock(return_value=expected_new_count)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.reaction_service.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await dislike_post(post_id, session_id)

        assert result is not None
        assert result.updated_count == expected_new_count
        assert result.is_duplicate is False

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        initial_count=_initial_count_strategy,
        session_id=_session_id_strategy,
    )
    async def test_like_comment_increments_count(self, initial_count, session_id):
        """
        Property 4: For any blog comment with initial like_count N and a unique
        session_id, submitting a like SHALL result in updated_count of N+1
        and is_duplicate SHALL be False.

        **Validates: Requirements 3.6**
        """
        comment_id = uuid.uuid4()
        expected_new_count = initial_count + 1

        reaction_row = _make_reaction_row("comment", comment_id, "like", session_id)

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=reaction_row)
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.fetchval = AsyncMock(return_value=expected_new_count)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.reaction_service.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await like_comment(comment_id, session_id)

        assert result is not None
        assert result.updated_count == expected_new_count
        assert result.is_duplicate is False

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        initial_count=_initial_count_strategy,
        session_id=_session_id_strategy,
    )
    async def test_dislike_comment_increments_count(self, initial_count, session_id):
        """
        Property 4: For any blog comment with initial dislike_count N and a unique
        session_id, submitting a dislike SHALL result in updated_count of N+1
        and is_duplicate SHALL be False.

        **Validates: Requirements 3.6**
        """
        comment_id = uuid.uuid4()
        expected_new_count = initial_count + 1

        reaction_row = _make_reaction_row("comment", comment_id, "dislike", session_id)

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=reaction_row)
        mock_conn.execute = AsyncMock(return_value=None)
        mock_conn.fetchval = AsyncMock(return_value=expected_new_count)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.reaction_service.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await dislike_comment(comment_id, session_id)

        assert result is not None
        assert result.updated_count == expected_new_count
        assert result.is_duplicate is False

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        initial_count=_initial_count_strategy,
        session_id=_session_id_strategy,
    )
    async def test_duplicate_like_post_does_not_increment(self, initial_count, session_id):
        """
        Property 4 (duplicate case): For any blog post, when the same session_id
        submits a like that triggers a UniqueViolationError, the count SHALL NOT
        be incremented and is_duplicate SHALL be True.

        **Validates: Requirements 3.2**
        """
        post_id = uuid.uuid4()

        # The existing reaction row (returned after UniqueViolationError)
        existing_reaction_row = _make_reaction_row("post", post_id, "like", session_id)

        # First call to fetchrow raises UniqueViolationError (INSERT fails)
        # Second call returns the existing reaction (SELECT)
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(
            side_effect=[
                asyncpg.UniqueViolationError("duplicate key"),
                existing_reaction_row,
            ]
        )
        # fetchval returns the unchanged count (no increment happened)
        mock_conn.fetchval = AsyncMock(return_value=initial_count)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.reaction_service.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await like_post(post_id, session_id)

        assert result is not None
        # Count should remain at N (not incremented)
        assert result.updated_count == initial_count
        assert result.is_duplicate is True

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        initial_count=_initial_count_strategy,
        session_id=_session_id_strategy,
    )
    async def test_duplicate_dislike_comment_does_not_increment(self, initial_count, session_id):
        """
        Property 4 (duplicate case): For any blog comment, when the same session_id
        submits a dislike that triggers a UniqueViolationError, the count SHALL NOT
        be incremented and is_duplicate SHALL be True.

        **Validates: Requirements 3.6**
        """
        comment_id = uuid.uuid4()

        existing_reaction_row = _make_reaction_row("comment", comment_id, "dislike", session_id)

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(
            side_effect=[
                asyncpg.UniqueViolationError("duplicate key"),
                existing_reaction_row,
            ]
        )
        mock_conn.fetchval = AsyncMock(return_value=initial_count)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.reaction_service.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await dislike_comment(comment_id, session_id)

        assert result is not None
        # Count should remain at N (not incremented)
        assert result.updated_count == initial_count
        assert result.is_duplicate is True
