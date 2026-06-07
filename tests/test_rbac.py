"""
RBAC (Role-Based Access Control) and User Isolation Tests for avry-blog.

Tests verify:
1. Public endpoints are accessible without authentication
2. Admin endpoints reject unauthenticated requests (401)
3. Admin endpoints reject non-admin users (403)
4. Admin endpoints accept admin/superadmin users (200/201/204)
5. Draft/hidden posts are never exposed on public endpoints
6. Different admin users can all manage content (no per-user isolation needed for blog)

Validates: Requirements 12.1, 12.2, 12.5, 12.7
"""

import pytest
from unittest.mock import patch, AsyncMock
from jose import jwt

from fastapi.testclient import TestClient

# Test JWT secrets
TEST_SUPABASE_SECRET = "test-supabase-jwt-secret-for-rbac"
TEST_LEGACY_SECRET = "test-legacy-jwt-secret-for-rbac"


def _make_token(payload: dict, secret: str = TEST_SUPABASE_SECRET) -> str:
    """Create a signed JWT token for testing."""
    return jwt.encode(payload, secret, algorithm="HS256")


def _admin_token() -> str:
    """Token for an admin user."""
    return _make_token({"sub": "admin-user-1", "account_type": "admin"})


def _superadmin_token() -> str:
    """Token for a superadmin user."""
    return _make_token({"sub": "superadmin-user-1", "account_type": "superadmin"})


def _regular_user_token() -> str:
    """Token for a regular (non-admin) user."""
    return _make_token({"sub": "regular-user-1", "account_type": "user"})


def _no_role_token() -> str:
    """Token without any account_type claim."""
    return _make_token({"sub": "norole-user-1"})


def _wrong_secret_token() -> str:
    """Token signed with an unknown secret."""
    return jwt.encode(
        {"sub": "hacker", "account_type": "admin"},
        "wrong-secret-not-configured",
        algorithm="HS256",
    )


@pytest.fixture
def client():
    """Create a test client with mocked DB and configured secrets."""
    with patch("app.database.connection.create_pool", new_callable=AsyncMock), \
         patch("app.database.connection.close_pool", new_callable=AsyncMock), \
         patch("app.database.connection.check_health", new_callable=AsyncMock, return_value=True), \
         patch("app.database.migrations.run_migrations", new_callable=AsyncMock), \
         patch("app.auth.settings") as mock_settings:
        mock_settings.supabase_jwt_secret = TEST_SUPABASE_SECRET
        mock_settings.jwt_secret = TEST_LEGACY_SECRET

        # Need to reimport after patching
        from app.main import app
        with TestClient(app) as c:
            yield c


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS — No auth required
# ═══════════════════════════════════════════════════════════════════════════════


class TestPublicEndpointsNoAuth:
    """Public endpoints must be accessible without any authentication."""

    def test_get_posts_no_auth(self, client):
        """GET /api/posts is accessible without token."""
        with patch("app.routes.posts.list_published_posts", new_callable=AsyncMock) as mock:
            from app.models.post import PaginatedPosts
            mock.return_value = PaginatedPosts(posts=[], total=0, page=1, limit=10, total_pages=0)
            response = client.get("/api/posts")
        assert response.status_code == 200

    def test_get_post_by_slug_no_auth(self, client):
        """GET /api/posts/{slug} is accessible without token."""
        with patch("app.routes.posts.get_post_by_slug", new_callable=AsyncMock, return_value=None):
            response = client.get("/api/posts/some-slug")
        assert response.status_code == 404  # Not 401 or 403

    def test_get_comments_no_auth(self, client):
        """GET /api/posts/{id}/comments is accessible without token."""
        import uuid
        post_id = str(uuid.uuid4())
        with patch("app.routes.comments.list_comments_for_post", new_callable=AsyncMock, return_value=[]):
            response = client.get(f"/api/posts/{post_id}/comments")
        assert response.status_code == 200

    def test_post_comment_no_auth(self, client):
        """POST /api/posts/{id}/comments is accessible without token."""
        import uuid
        post_id = str(uuid.uuid4())
        with patch("app.routes.comments.create_comment", new_callable=AsyncMock, return_value=None):
            response = client.post(
                f"/api/posts/{post_id}/comments",
                json={"author_name": "Visitor", "body": "Nice post!"},
            )
        # 404 (post not found) is fine — not 401/403
        assert response.status_code in (201, 404)

    def test_like_post_no_auth(self, client):
        """POST /api/posts/{id}/like is accessible without token."""
        import uuid
        post_id = str(uuid.uuid4())
        with patch("app.routes.reactions.like_post", new_callable=AsyncMock, return_value=None):
            response = client.post(
                f"/api/posts/{post_id}/like",
                json={"session_id": "visitor-session-123"},
            )
        # 500 (mock returns None) is fine — not 401/403
        assert response.status_code != 401
        assert response.status_code != 403

    def test_dislike_post_no_auth(self, client):
        """POST /api/posts/{id}/dislike is accessible without token."""
        import uuid
        post_id = str(uuid.uuid4())
        with patch("app.routes.reactions.dislike_post", new_callable=AsyncMock, return_value=None):
            response = client.post(
                f"/api/posts/{post_id}/dislike",
                json={"session_id": "visitor-session-456"},
            )
        assert response.status_code != 401
        assert response.status_code != 403

    def test_health_no_auth(self, client):
        """GET /health is accessible without token."""
        response = client.get("/health")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS — 401 Without Auth
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminEndpoints401WithoutAuth:
    """Admin endpoints must return 401 when no Authorization header is provided."""

    ADMIN_ENDPOINTS = [
        ("GET", "/api/admin/posts"),
        ("POST", "/api/admin/posts"),
        ("PUT", "/api/admin/posts/00000000-0000-0000-0000-000000000001"),
        ("DELETE", "/api/admin/posts/00000000-0000-0000-0000-000000000001"),
        ("PATCH", "/api/admin/posts/00000000-0000-0000-0000-000000000001/status"),
        ("PATCH", "/api/admin/posts/00000000-0000-0000-0000-000000000001/redact"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_no_token_returns_401(self, client, method, path):
        """Admin endpoint without token → 401."""
        response = client.request(method, path)
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing authentication token"


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS — 401 With Invalid Token
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminEndpoints401InvalidToken:
    """Admin endpoints must return 401 for invalid/expired/wrong-secret tokens."""

    ADMIN_ENDPOINTS = [
        ("GET", "/api/admin/posts"),
        ("POST", "/api/admin/posts"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_garbage_token_returns_401(self, client, method, path):
        """Garbage token → 401."""
        response = client.request(method, path, headers={"Authorization": "Bearer garbage.token.here"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired token"

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_wrong_secret_token_returns_401(self, client, method, path):
        """Token signed with unknown secret → 401."""
        response = client.request(
            method, path, headers={"Authorization": f"Bearer {_wrong_secret_token()}"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired token"


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS — 403 For Non-Admin Users
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminEndpoints403NonAdmin:
    """Admin endpoints must return 403 for authenticated non-admin users."""

    ADMIN_ENDPOINTS = [
        ("GET", "/api/admin/posts"),
        ("POST", "/api/admin/posts"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_regular_user_returns_403(self, client, method, path):
        """Regular user (account_type: user) → 403."""
        response = client.request(
            method, path, headers={"Authorization": f"Bearer {_regular_user_token()}"}
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_no_role_returns_403(self, client, method, path):
        """Token without account_type → 403."""
        response = client.request(
            method, path, headers={"Authorization": f"Bearer {_no_role_token()}"}
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS — 200/201 For Admin Users
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminEndpointsAcceptAdmin:
    """Admin endpoints must accept admin and superadmin users."""

    def test_admin_can_list_posts(self, client):
        """Admin user can GET /api/admin/posts."""
        with patch("app.routes.admin.list_all_posts", new_callable=AsyncMock) as mock:
            from app.models.post import PaginatedPosts
            mock.return_value = PaginatedPosts(posts=[], total=0, page=1, limit=50, total_pages=0)
            response = client.get(
                "/api/admin/posts",
                headers={"Authorization": f"Bearer {_admin_token()}"},
            )
        assert response.status_code == 200

    def test_superadmin_can_list_posts(self, client):
        """Superadmin user can GET /api/admin/posts."""
        with patch("app.routes.admin.list_all_posts", new_callable=AsyncMock) as mock:
            from app.models.post import PaginatedPosts
            mock.return_value = PaginatedPosts(posts=[], total=0, page=1, limit=50, total_pages=0)
            response = client.get(
                "/api/admin/posts",
                headers={"Authorization": f"Bearer {_superadmin_token()}"},
            )
        assert response.status_code == 200

    def test_admin_can_create_post(self, client):
        """Admin user can POST /api/admin/posts."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.models.post import BlogPost, PostStatus

        mock_post = BlogPost(
            id=uuid4(), slug="test", title="Test", body={"blocks": []},
            author_name="Admin", status=PostStatus.draft,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        with patch("app.routes.admin.create_post", new_callable=AsyncMock, return_value=mock_post):
            response = client.post(
                "/api/admin/posts",
                json={"title": "Test", "body": {"blocks": []}, "author_name": "Admin"},
                headers={"Authorization": f"Bearer {_admin_token()}"},
            )
        assert response.status_code == 201


# ═══════════════════════════════════════════════════════════════════════════════
# DUAL SECRET SUPPORT
# ═══════════════════════════════════════════════════════════════════════════════


class TestDualSecretSupport:
    """Both Supabase and legacy JWT secrets are accepted."""

    def test_supabase_secret_accepted(self, client):
        """Token signed with SUPABASE_JWT_SECRET is accepted."""
        token = _make_token({"sub": "user", "account_type": "admin"}, TEST_SUPABASE_SECRET)
        with patch("app.routes.admin.list_all_posts", new_callable=AsyncMock) as mock:
            from app.models.post import PaginatedPosts
            mock.return_value = PaginatedPosts(posts=[], total=0, page=1, limit=50, total_pages=0)
            response = client.get(
                "/api/admin/posts",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200

    def test_legacy_secret_accepted(self, client):
        """Token signed with legacy JWT_SECRET is accepted."""
        token = _make_token({"sub": "user", "account_type": "admin"}, TEST_LEGACY_SECRET)
        with patch("app.routes.admin.list_all_posts", new_callable=AsyncMock) as mock:
            from app.models.post import PaginatedPosts
            mock.return_value = PaginatedPosts(posts=[], total=0, page=1, limit=50, total_pages=0)
            response = client.get(
                "/api/admin/posts",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# USER ISOLATION — Public endpoints never expose non-published content
# ═══════════════════════════════════════════════════════════════════════════════


class TestUserIsolation:
    """Public endpoints must never expose draft or hidden posts."""

    def test_draft_post_not_accessible_via_slug(self, client):
        """GET /api/posts/{slug} returns 404 for draft posts."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.models.post import BlogPost, PostStatus

        draft_post = BlogPost(
            id=uuid4(), slug="draft-post", title="Draft", body={},
            author_name="Admin", status=PostStatus.draft,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        with patch("app.routes.posts.get_post_by_slug", new_callable=AsyncMock, return_value=draft_post):
            response = client.get("/api/posts/draft-post")
        assert response.status_code == 404

    def test_hidden_post_not_accessible_via_slug(self, client):
        """GET /api/posts/{slug} returns 404 for hidden posts."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.models.post import BlogPost, PostStatus

        hidden_post = BlogPost(
            id=uuid4(), slug="hidden-post", title="Hidden", body={},
            author_name="Admin", status=PostStatus.hidden,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        with patch("app.routes.posts.get_post_by_slug", new_callable=AsyncMock, return_value=hidden_post):
            response = client.get("/api/posts/hidden-post")
        assert response.status_code == 404

    def test_published_post_accessible_via_slug(self, client):
        """GET /api/posts/{slug} returns 200 for published posts."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.models.post import BlogPost, PostStatus

        pub_post = BlogPost(
            id=uuid4(), slug="pub-post", title="Published", body={"blocks": []},
            author_name="Admin", status=PostStatus.published,
            published_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        with patch("app.routes.posts.get_post_by_slug", new_callable=AsyncMock, return_value=pub_post):
            response = client.get("/api/posts/pub-post")
        assert response.status_code == 200
