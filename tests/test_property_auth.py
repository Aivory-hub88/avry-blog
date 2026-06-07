"""
Property-based tests for authentication and access control.

Uses Hypothesis to verify correctness properties of the blog service's
authentication behavior on public and admin endpoints.

Feature: blog-and-careers
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.comment import Comment
from app.models.post import BlogPost, BlogPostListItem, PaginatedPosts, PostStatus
from app.models.reaction import Reaction, ReactionResponse, ReactionType, TargetType


# --- Strategies ---

_uuid_strategy = st.builds(uuid.uuid4)

_session_id_strategy = st.text(min_size=1, max_size=255).filter(lambda s: s.strip())

_slug_strategy = st.from_regex(r"[a-z0-9]+(-[a-z0-9]+)*", fullmatch=True).filter(
    lambda s: 1 <= len(s) <= 200
)

_datetime_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(timezone.utc),
)

_author_name_strategy = st.text(min_size=1, max_size=100).filter(lambda t: t.strip())
_body_strategy = st.text(min_size=1, max_size=500).filter(lambda t: t.strip())


# --- Helpers to build mock responses ---


def _make_paginated_posts() -> PaginatedPosts:
    """Create an empty paginated posts response for mocking."""
    return PaginatedPosts(
        posts=[],
        total=0,
        page=1,
        limit=10,
        total_pages=0,
    )


def _make_blog_post(slug: str) -> BlogPost:
    """Create a published blog post for mocking."""
    now = datetime.now(timezone.utc)
    return BlogPost(
        id=uuid.uuid4(),
        slug=slug,
        title="Test Post",
        excerpt="An excerpt",
        body={"type": "doc", "content": [{"type": "paragraph", "text": "Body"}]},
        author_name="Author",
        thumbnail_url=None,
        status=PostStatus.published,
        like_count=0,
        dislike_count=0,
        comment_count=0,
        redacted_sections=[],
        published_at=now,
        created_at=now,
        updated_at=now,
    )


def _make_comment(post_id: uuid.UUID, comment_id: uuid.UUID) -> Comment:
    """Create a comment for mocking."""
    return Comment(
        id=comment_id,
        post_id=post_id,
        parent_id=None,
        author_name="Commenter",
        body="A comment",
        like_count=0,
        dislike_count=0,
        created_at=datetime.now(timezone.utc),
        replies=[],
    )


def _make_reaction_response(
    target_type: TargetType,
    target_id: uuid.UUID,
    reaction_type: ReactionType,
    session_id: str,
) -> ReactionResponse:
    """Create a reaction response for mocking."""
    return ReactionResponse(
        reaction=Reaction(
            id=uuid.uuid4(),
            target_type=target_type,
            target_id=target_id,
            reaction_type=reaction_type,
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
        ),
        updated_count=1,
        is_duplicate=False,
    )


# --- Public endpoint definitions ---

# Each entry: (method, path_template, needs_body, mock_patches)
# path_template uses {post_id}, {slug}, {comment_id} as placeholders


@st.composite
def _public_endpoint_strategy(draw):
    """
    Generate a random public endpoint request configuration.

    Each generated value represents one of the blog service's public endpoints
    along with appropriate mock data to allow the request to succeed.
    """
    post_id = draw(_uuid_strategy)
    comment_id = draw(_uuid_strategy)
    slug = draw(_slug_strategy)
    session_id = draw(_session_id_strategy)
    author_name = draw(_author_name_strategy)
    body = draw(_body_strategy)

    endpoints = [
        {
            "method": "GET",
            "path": "/api/posts",
            "json_body": None,
            "patches": {
                "app.routes.posts.list_published_posts": _make_paginated_posts(),
            },
        },
        {
            "method": "GET",
            "path": f"/api/posts/{slug}",
            "json_body": None,
            "patches": {
                "app.routes.posts.get_post_by_slug": _make_blog_post(slug),
            },
        },
        {
            "method": "POST",
            "path": f"/api/posts/{post_id}/like",
            "json_body": {"session_id": session_id},
            "patches": {
                "app.routes.reactions.like_post": _make_reaction_response(
                    TargetType.post, post_id, ReactionType.like, session_id
                ),
            },
        },
        {
            "method": "POST",
            "path": f"/api/posts/{post_id}/dislike",
            "json_body": {"session_id": session_id},
            "patches": {
                "app.routes.reactions.dislike_post": _make_reaction_response(
                    TargetType.post, post_id, ReactionType.dislike, session_id
                ),
            },
        },
        {
            "method": "GET",
            "path": f"/api/posts/{post_id}/comments",
            "json_body": None,
            "patches": {
                "app.routes.comments.list_comments_for_post": [
                    _make_comment(post_id, comment_id)
                ],
            },
        },
        {
            "method": "POST",
            "path": f"/api/posts/{post_id}/comments",
            "json_body": {"author_name": author_name, "body": body},
            "patches": {
                "app.routes.comments.create_comment": _make_comment(post_id, comment_id),
            },
        },
        {
            "method": "POST",
            "path": f"/api/comments/{comment_id}/reply",
            "json_body": {"author_name": author_name, "body": body},
            "patches": {
                "app.routes.comments.create_reply": _make_comment(post_id, comment_id),
            },
        },
        {
            "method": "POST",
            "path": f"/api/comments/{comment_id}/like",
            "json_body": {"session_id": session_id},
            "patches": {
                "app.routes.reactions.like_comment": _make_reaction_response(
                    TargetType.comment, comment_id, ReactionType.like, session_id
                ),
            },
        },
        {
            "method": "POST",
            "path": f"/api/comments/{comment_id}/dislike",
            "json_body": {"session_id": session_id},
            "patches": {
                "app.routes.reactions.dislike_comment": _make_reaction_response(
                    TargetType.comment, comment_id, ReactionType.dislike, session_id
                ),
            },
        },
    ]

    endpoint = draw(st.sampled_from(endpoints))
    return endpoint


# --- Property 14: Public endpoints accessible without authentication ---


class TestPublicEndpointsAccessibleWithoutAuth:
    """
    Feature: blog-and-careers, Property 14: Public endpoints accessible without authentication

    For any public endpoint (post listing, post detail, reactions, comments),
    requests without an Authorization header SHALL receive a successful response
    (not 401 or 403).

    **Validates: Requirements 12.1**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(endpoint=_public_endpoint_strategy())
    async def test_public_endpoints_do_not_require_authentication(self, endpoint):
        """
        Property 14: For any public endpoint (post listing, post detail,
        reactions, comments), requests without an Authorization header SHALL
        receive a successful response (not 401 or 403).

        **Validates: Requirements 12.1**
        """
        method = endpoint["method"]
        path = endpoint["path"]
        json_body = endpoint["json_body"]
        patches = endpoint["patches"]

        # Apply all mocks for this endpoint's service layer
        patch_contexts = []
        for target, return_value in patches.items():
            p = patch(target, new_callable=AsyncMock, return_value=return_value)
            patch_contexts.append(p)

        # Enter all patch contexts
        for p in patch_contexts:
            p.start()

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Make request WITHOUT any Authorization header
                if method == "GET":
                    response = await client.get(path)
                elif method == "POST":
                    response = await client.post(path, json=json_body)
                else:
                    raise ValueError(f"Unsupported method: {method}")

            # PROPERTY ASSERTION: Response should NOT be 401 or 403
            assert response.status_code not in (401, 403), (
                f"Public endpoint {method} {path} returned {response.status_code} "
                f"without Authorization header. Public endpoints must not require "
                f"authentication. Response body: {response.text}"
            )
        finally:
            # Stop all patches
            for p in patch_contexts:
                p.stop()


# --- Additional imports for Property 16 ---
from jose import jwt as jose_jwt
from app.auth import verify_token, JWT_ALGORITHM


# --- Strategies for Property 16 ---

_user_id_strategy = st.one_of(
    st.builds(lambda: str(uuid.uuid4())),
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=64,
    ).filter(lambda s: s.strip()),
)

_admin_account_type_strategy = st.sampled_from(["admin", "superadmin"])

_random_wrong_secret_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=10,
    max_size=64,
).filter(
    lambda s: s not in (
        "test-supabase-jwt-secret-for-property-16",
        "test-legacy-jwt-secret-for-property-16",
    ) and len(s.strip()) > 0
)

# Known test secrets for Property 16
_P16_SUPABASE_SECRET = "test-supabase-jwt-secret-for-property-16"
_P16_LEGACY_SECRET = "test-legacy-jwt-secret-for-property-16"


def _make_signed_token(payload: dict, secret: str) -> str:
    """Create a signed JWT with the given payload and secret."""
    return jose_jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


# --- Property 16: JWT verification accepts both Supabase and legacy tokens ---


class TestJWTVerificationAcceptsBothTokenTypes:
    """
    Feature: blog-and-careers, Property 16: JWT verification accepts both Supabase and legacy tokens

    For any valid JWT signed with either SUPABASE_JWT_SECRET or the legacy
    JWT_SECRET and containing admin account_type, the service SHALL accept the
    token and grant access to admin endpoints.

    **Validates: Requirements 14.3**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        user_id=_user_id_strategy,
        account_type=_admin_account_type_strategy,
    )
    def test_supabase_signed_token_is_accepted(self, user_id: str, account_type: str):
        """
        Property 16a: For any valid JWT signed with SUPABASE_JWT_SECRET and
        containing admin account_type, verify_token SHALL accept the token and
        return the decoded payload.

        **Validates: Requirements 14.3**
        """
        payload = {"sub": user_id, "account_type": account_type}
        token = _make_signed_token(payload, _P16_SUPABASE_SECRET)

        with patch("app.auth.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = _P16_SUPABASE_SECRET
            mock_settings.jwt_secret = _P16_LEGACY_SECRET

            result = verify_token(token)

        assert result is not None, (
            f"Token signed with SUPABASE_JWT_SECRET should be accepted. "
            f"user_id={user_id}, account_type={account_type}"
        )
        assert result["sub"] == user_id
        assert result["account_type"] == account_type

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        user_id=_user_id_strategy,
        account_type=_admin_account_type_strategy,
    )
    def test_legacy_signed_token_is_accepted(self, user_id: str, account_type: str):
        """
        Property 16b: For any valid JWT signed with JWT_SECRET (legacy) and
        containing admin account_type, verify_token SHALL accept the token and
        return the decoded payload.

        **Validates: Requirements 14.3**
        """
        payload = {"sub": user_id, "account_type": account_type}
        token = _make_signed_token(payload, _P16_LEGACY_SECRET)

        with patch("app.auth.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = _P16_SUPABASE_SECRET
            mock_settings.jwt_secret = _P16_LEGACY_SECRET

            result = verify_token(token)

        assert result is not None, (
            f"Token signed with legacy JWT_SECRET should be accepted. "
            f"user_id={user_id}, account_type={account_type}"
        )
        assert result["sub"] == user_id
        assert result["account_type"] == account_type

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        user_id=_user_id_strategy,
        account_type=_admin_account_type_strategy,
        wrong_secret=_random_wrong_secret_strategy,
    )
    def test_wrong_secret_token_is_rejected(self, user_id: str, account_type: str, wrong_secret: str):
        """
        Property 16c: For any JWT signed with a secret that is neither
        SUPABASE_JWT_SECRET nor JWT_SECRET, verify_token SHALL reject the token
        and return None.

        **Validates: Requirements 14.3**
        """
        payload = {"sub": user_id, "account_type": account_type}
        token = _make_signed_token(payload, wrong_secret)

        with patch("app.auth.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = _P16_SUPABASE_SECRET
            mock_settings.jwt_secret = _P16_LEGACY_SECRET

            result = verify_token(token)

        assert result is None, (
            f"Token signed with wrong secret should be rejected. "
            f"user_id={user_id}, account_type={account_type}, wrong_secret={wrong_secret!r}"
        )


# --- Additional imports for Property 15 ---
from jose import jwt as jose_jwt

# --- Constants for Property 15 ---

_TEST_JWT_SECRET = "test-property-secret-for-auth-testing"
_JWT_ALGORITHM = "HS256"

# Admin endpoints with their HTTP methods and sample request bodies
_ADMIN_ENDPOINTS = [
    ("GET", "/api/admin/posts", None),
    ("POST", "/api/admin/posts", {"title": "Test", "body": {"content": []}, "author_name": "Author"}),
    ("PUT", "/api/admin/posts/{post_id}", {"title": "Updated"}),
    ("DELETE", "/api/admin/posts/{post_id}", None),
    ("PATCH", "/api/admin/posts/{post_id}/status", {"status": "published"}),
    ("PATCH", "/api/admin/posts/{post_id}/redact", {"redacted_sections": []}),
]


# --- Strategies for Property 15 ---

_admin_account_types_strategy = st.sampled_from(["admin", "superadmin"])

_non_admin_account_types_strategy = st.sampled_from(
    ["user", "viewer", "editor", "member", "guest", "basic"]
)

_admin_endpoint_strategy = st.sampled_from(_ADMIN_ENDPOINTS)

_user_id_strategy = st.uuids().map(str)


def _make_test_jwt(payload: dict) -> str:
    """Create a JWT signed with the test secret."""
    return jose_jwt.encode(payload, _TEST_JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _resolve_admin_path(path: str) -> str:
    """Replace {post_id} placeholder with a valid UUID."""
    return path.replace("{post_id}", str(uuid.uuid4()))


async def _make_admin_request(client: AsyncClient, method: str, path: str, body, headers: dict):
    """Make an HTTP request with the given method, path, body, and headers."""
    resolved_path = _resolve_admin_path(path)
    if method == "GET":
        return await client.get(resolved_path, headers=headers)
    elif method == "POST":
        return await client.post(resolved_path, json=body, headers=headers)
    elif method == "PUT":
        return await client.put(resolved_path, json=body, headers=headers)
    elif method == "DELETE":
        return await client.delete(resolved_path, headers=headers)
    elif method == "PATCH":
        return await client.patch(resolved_path, json=body, headers=headers)
    raise ValueError(f"Unsupported method: {method}")


def _mock_admin_blog_post():
    """Create a mock BlogPost for admin service layer mocks."""
    now = datetime.now(timezone.utc)
    return BlogPost(
        id=uuid.uuid4(),
        slug="test-property-post",
        title="Test Post",
        excerpt="Excerpt",
        body={"type": "doc", "content": [{"type": "paragraph", "text": "Body"}]},
        author_name="Author",
        thumbnail_url=None,
        status=PostStatus.published,
        like_count=0,
        dislike_count=0,
        comment_count=0,
        redacted_sections=[],
        published_at=now,
        created_at=now,
        updated_at=now,
    )


def _mock_admin_paginated_posts():
    """Create a mock PaginatedPosts for the admin list endpoint."""
    return PaginatedPosts(posts=[], total=0, page=1, limit=50, total_pages=0)


# --- Property 15: Admin endpoints enforce role-based access ---


class TestAdminEndpointsEnforceRoleBasedAccess:
    """
    Feature: blog-and-careers, Property 15: Admin endpoints enforce role-based access

    For any admin endpoint, a request without authentication SHALL return 401,
    a request with a valid JWT lacking admin/superadmin account_type SHALL return 403,
    and a request with a valid admin JWT SHALL be permitted (not 401 or 403).

    **Validates: Requirements 12.2, 12.5, 12.7**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(endpoint=_admin_endpoint_strategy)
    async def test_no_auth_returns_401(self, endpoint):
        """
        Property 15a: For any admin endpoint, a request without an Authorization
        header SHALL return 401 (Missing authentication token).

        **Validates: Requirements 12.5**
        """
        method, path, body = endpoint

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await _make_admin_request(client, method, path, body, headers={})

        assert response.status_code == 401, (
            f"{method} {path} without auth returned {response.status_code}, expected 401"
        )

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        endpoint=_admin_endpoint_strategy,
        account_type=_non_admin_account_types_strategy,
        user_id=_user_id_strategy,
    )
    async def test_non_admin_jwt_returns_403(self, endpoint, account_type, user_id):
        """
        Property 15b: For any admin endpoint, a request with a valid JWT that
        has a non-admin account_type (e.g., "user", "viewer") SHALL return 403
        (Admin access required).

        **Validates: Requirements 12.7**
        """
        method, path, body = endpoint

        # Create a valid JWT with a non-admin account_type
        payload = {"sub": user_id, "account_type": account_type}

        with patch("app.auth.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = _TEST_JWT_SECRET
            mock_settings.jwt_secret = ""

            token = _make_test_jwt(payload)
            headers = {"Authorization": f"Bearer {token}"}

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await _make_admin_request(client, method, path, body, headers=headers)

        assert response.status_code == 403, (
            f"{method} {path} with account_type='{account_type}' returned "
            f"{response.status_code}, expected 403"
        )

    @pytest.mark.asyncio
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        endpoint=_admin_endpoint_strategy,
        account_type=_admin_account_types_strategy,
        user_id=_user_id_strategy,
    )
    async def test_admin_jwt_is_permitted(self, endpoint, account_type, user_id):
        """
        Property 15c: For any admin endpoint, a request with a valid JWT
        containing admin or superadmin account_type SHALL be permitted
        (SHALL NOT return 401 or 403).

        **Validates: Requirements 12.2**
        """
        method, path, body = endpoint

        # Create a valid JWT with admin/superadmin account_type
        payload = {"sub": user_id, "account_type": account_type}

        with patch("app.auth.settings") as mock_settings:
            mock_settings.supabase_jwt_secret = _TEST_JWT_SECRET
            mock_settings.jwt_secret = ""

            token = _make_test_jwt(payload)
            headers = {"Authorization": f"Bearer {token}"}

            # Mock the service layer so we don't need a real database.
            with patch(
                "app.routes.admin.create_post",
                new_callable=AsyncMock,
                return_value=_mock_admin_blog_post(),
            ), patch(
                "app.routes.admin.get_post_by_id",
                new_callable=AsyncMock,
                return_value=_mock_admin_blog_post(),
            ), patch(
                "app.routes.admin.update_post",
                new_callable=AsyncMock,
                return_value=_mock_admin_blog_post(),
            ), patch(
                "app.routes.admin.delete_post",
                new_callable=AsyncMock,
                return_value=True,
            ), patch(
                "app.routes.admin.change_status",
                new_callable=AsyncMock,
                return_value=_mock_admin_blog_post(),
            ), patch(
                "app.routes.admin.list_all_posts",
                new_callable=AsyncMock,
                return_value=_mock_admin_paginated_posts(),
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await _make_admin_request(
                        client, method, path, body, headers=headers
                    )

        assert response.status_code not in (401, 403), (
            f"{method} {path} with account_type='{account_type}' returned "
            f"{response.status_code}, expected neither 401 nor 403"
        )
