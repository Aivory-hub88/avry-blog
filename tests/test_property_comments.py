"""
Property-based tests for blog comment tree integrity.

Uses Hypothesis to verify that the comment threading system correctly
persists parent-child relationships and reconstructs the tree structure.

Feature: blog-and-careers, Property 5: Comment tree integrity
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from app.models.comment import Comment
from app.services.comment_service import list_comments_for_post


# --- Strategies ---

_author_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

_body_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P")),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip() != "")


@st.composite
def _comment_tree_strategy(draw):
    """
    Generate a random comment tree structure for a blog post.

    Produces a list of comment records (as dicts simulating DB rows) with
    a valid tree structure: some top-level comments (parent_id=None) and
    some replies (parent_id pointing to an existing comment).

    Returns (post_id, list_of_row_dicts) where each row dict has the fields
    matching the blog_comments table schema.
    """
    post_id = draw(st.builds(uuid.uuid4))

    # Generate between 1 and 15 comments total
    num_comments = draw(st.integers(min_value=1, max_value=15))

    rows = []
    comment_ids = []
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    for i in range(num_comments):
        comment_id = draw(st.builds(uuid.uuid4))

        # First comment is always top-level; subsequent ones may be replies
        if i == 0 or not comment_ids:
            parent_id = None
        else:
            # ~50% chance of being a reply to an existing comment
            is_reply = draw(st.booleans())
            if is_reply:
                parent_id = draw(st.sampled_from(comment_ids))
            else:
                parent_id = None

        author_name = draw(_author_name_strategy)
        body = draw(_body_strategy)

        row = {
            "id": comment_id,
            "post_id": post_id,
            "parent_id": parent_id,
            "author_name": author_name,
            "body": body,
            "like_count": draw(st.integers(min_value=0, max_value=100)),
            "dislike_count": draw(st.integers(min_value=0, max_value=100)),
            "created_at": base_time + timedelta(minutes=i),
        }

        rows.append(row)
        comment_ids.append(comment_id)

    return post_id, rows


class _FakeRecord(dict):
    """A dict subclass that supports attribute-style access via __getitem__ (like asyncpg.Record)."""

    def __getitem__(self, key):
        return super().__getitem__(key)


def _rows_to_fake_records(rows: list[dict]) -> list:
    """Convert row dicts into objects that behave like asyncpg.Record (dict-like access)."""
    return [_FakeRecord(row) for row in rows]


# --- Property 5: Comment tree integrity ---


class TestCommentTreeIntegrity:
    """
    Feature: blog-and-careers, Property 5: Comment tree integrity

    For any blog post and any sequence of comments and replies, each reply
    SHALL be persisted as a child of its specified parent comment, and
    retrieving comments for a post SHALL return all comments with correct
    parent-child relationships.

    **Validates: Requirements 3.4, 3.5**
    """

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(tree_data=_comment_tree_strategy())
    async def test_comment_tree_parent_child_relationships(self, tree_data):
        """
        Property 5: For any blog post and any sequence of comments and replies,
        retrieving comments for a post SHALL return all comments with correct
        parent-child relationships — each reply is nested under its parent,
        and top-level comments appear at the root level.

        **Validates: Requirements 3.4, 3.5**
        """
        post_id, rows = tree_data

        # Build expected relationships from raw data
        expected_top_level_ids = {
            row["id"] for row in rows if row["parent_id"] is None
        }
        expected_children = {}  # parent_id -> set of child ids
        for row in rows:
            if row["parent_id"] is not None:
                if row["parent_id"] not in expected_children:
                    expected_children[row["parent_id"]] = set()
                expected_children[row["parent_id"]].add(row["id"])

        fake_records = _rows_to_fake_records(rows)

        # Mock the database pool and connection
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=fake_records)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.comment_service.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await list_comments_for_post(post_id)

        # Collect all comment IDs from the result tree
        all_returned_ids = set()
        top_level_ids = set()
        actual_children = {}  # parent_id -> set of child ids

        def traverse(comments: list[Comment], parent_id=None):
            for comment in comments:
                all_returned_ids.add(comment.id)
                if parent_id is None:
                    top_level_ids.add(comment.id)
                else:
                    if parent_id not in actual_children:
                        actual_children[parent_id] = set()
                    actual_children[parent_id].add(comment.id)
                # Recurse into replies
                traverse(comment.replies, parent_id=comment.id)

        traverse(result)

        # PROPERTY ASSERTION 1: All comments are returned (no comments lost)
        all_input_ids = {row["id"] for row in rows}
        assert all_returned_ids == all_input_ids, (
            f"Not all comments were returned. "
            f"Missing: {all_input_ids - all_returned_ids}, "
            f"Extra: {all_returned_ids - all_input_ids}"
        )

        # PROPERTY ASSERTION 2: Top-level comments have parent_id=None
        assert top_level_ids == expected_top_level_ids, (
            f"Top-level comment mismatch. "
            f"Expected: {expected_top_level_ids}, Got: {top_level_ids}"
        )

        # PROPERTY ASSERTION 3: Every reply is nested under its correct parent
        for parent_id, expected_child_ids in expected_children.items():
            actual_child_ids = actual_children.get(parent_id, set())
            assert actual_child_ids == expected_child_ids, (
                f"Children of {parent_id} mismatch. "
                f"Expected: {expected_child_ids}, Got: {actual_child_ids}"
            )

        # PROPERTY ASSERTION 4: No spurious parent-child relationships exist
        for parent_id, actual_child_ids in actual_children.items():
            expected_child_ids = expected_children.get(parent_id, set())
            assert actual_child_ids == expected_child_ids, (
                f"Unexpected children under {parent_id}: "
                f"{actual_child_ids - expected_child_ids}"
            )

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(tree_data=_comment_tree_strategy())
    async def test_replies_have_correct_parent_id_set(self, tree_data):
        """
        Property 5 (supplemental): For any reply in the tree, the comment's
        parent_id field SHALL match the parent it was specified to belong to.

        **Validates: Requirements 3.4, 3.5**
        """
        post_id, rows = tree_data

        # Build a lookup of expected parent_id for each comment
        expected_parent_ids = {row["id"]: row["parent_id"] for row in rows}

        fake_records = _rows_to_fake_records(rows)

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=fake_records)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.comment_service.get_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await list_comments_for_post(post_id)

        # Verify that every comment in the tree has its parent_id field
        # correctly set as per the original data
        def verify_parent_ids(comments: list[Comment]):
            for comment in comments:
                assert comment.parent_id == expected_parent_ids[comment.id], (
                    f"Comment {comment.id} has parent_id={comment.parent_id}, "
                    f"expected {expected_parent_ids[comment.id]}"
                )
                verify_parent_ids(comment.replies)

        verify_parent_ids(result)
