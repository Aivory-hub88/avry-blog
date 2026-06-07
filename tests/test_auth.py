"""Unit tests for the avry-blog authentication module."""

import pytest
from unittest.mock import patch
from jose import jwt
from fastapi import HTTPException

from app.auth import (
    verify_token,
    get_current_user,
    require_admin,
    _extract_token,
    _account_type,
    JWT_ALGORITHM,
)


# Test secrets
SUPABASE_SECRET = "test-supabase-jwt-secret"
LEGACY_SECRET = "test-legacy-jwt-secret"


def _make_token(payload: dict, secret: str = SUPABASE_SECRET) -> str:
    """Helper to create a signed JWT."""
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


class TestExtractToken:
    def test_none_header(self):
        assert _extract_token(None) is None

    def test_empty_string(self):
        assert _extract_token("") is None

    def test_bearer_prefix(self):
        assert _extract_token("Bearer abc123") == "abc123"

    def test_bearer_lowercase(self):
        assert _extract_token("bearer abc123") == "abc123"

    def test_bare_token(self):
        assert _extract_token("abc123") == "abc123"

    def test_whitespace_only(self):
        assert _extract_token("   ") is None


class TestVerifyToken:
    @patch("app.auth.settings")
    def test_valid_supabase_token(self, mock_settings):
        mock_settings.supabase_jwt_secret = SUPABASE_SECRET
        mock_settings.jwt_secret = LEGACY_SECRET

        token = _make_token({"sub": "user-1", "account_type": "admin"}, SUPABASE_SECRET)
        payload = verify_token(token)

        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["account_type"] == "admin"

    @patch("app.auth.settings")
    def test_valid_legacy_token(self, mock_settings):
        mock_settings.supabase_jwt_secret = SUPABASE_SECRET
        mock_settings.jwt_secret = LEGACY_SECRET

        token = _make_token({"sub": "user-2", "account_type": "superadmin"}, LEGACY_SECRET)
        payload = verify_token(token)

        assert payload is not None
        assert payload["sub"] == "user-2"
        assert payload["account_type"] == "superadmin"

    @patch("app.auth.settings")
    def test_invalid_token(self, mock_settings):
        mock_settings.supabase_jwt_secret = SUPABASE_SECRET
        mock_settings.jwt_secret = LEGACY_SECRET

        payload = verify_token("completely-invalid-token")
        assert payload is None

    @patch("app.auth.settings")
    def test_wrong_secret(self, mock_settings):
        mock_settings.supabase_jwt_secret = SUPABASE_SECRET
        mock_settings.jwt_secret = LEGACY_SECRET

        token = _make_token({"sub": "user-3"}, "wrong-secret")
        payload = verify_token(token)
        assert payload is None

    @patch("app.auth.settings")
    def test_empty_secrets(self, mock_settings):
        mock_settings.supabase_jwt_secret = ""
        mock_settings.jwt_secret = ""

        token = _make_token({"sub": "user-4"}, SUPABASE_SECRET)
        payload = verify_token(token)
        assert payload is None

    @patch("app.auth.settings")
    def test_supabase_preferred_over_legacy(self, mock_settings):
        """Supabase secret is tried first when both are configured."""
        mock_settings.supabase_jwt_secret = SUPABASE_SECRET
        mock_settings.jwt_secret = LEGACY_SECRET

        token = _make_token({"sub": "user-5", "source": "supabase"}, SUPABASE_SECRET)
        payload = verify_token(token)

        assert payload is not None
        assert payload["source"] == "supabase"


class TestAccountType:
    def test_direct_claim(self):
        assert _account_type({"account_type": "admin"}) == "admin"

    def test_user_metadata(self):
        assert _account_type({"user_metadata": {"account_type": "superadmin"}}) == "superadmin"

    def test_app_metadata(self):
        assert _account_type({"app_metadata": {"account_type": "admin"}}) == "admin"

    def test_no_account_type(self):
        assert _account_type({"sub": "user-1"}) is None

    def test_priority_order(self):
        """Direct claim takes priority over metadata."""
        payload = {
            "account_type": "admin",
            "user_metadata": {"account_type": "superadmin"},
        }
        assert _account_type(payload) == "admin"


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_missing_authorization(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(authorization=None)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Missing authentication token"

    @pytest.mark.asyncio
    @patch("app.auth.settings")
    async def test_invalid_token(self, mock_settings):
        mock_settings.supabase_jwt_secret = SUPABASE_SECRET
        mock_settings.jwt_secret = LEGACY_SECRET

        with pytest.raises(HTTPException) as exc:
            await get_current_user(authorization="Bearer invalid-token")
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    @patch("app.auth.settings")
    async def test_valid_token(self, mock_settings):
        mock_settings.supabase_jwt_secret = SUPABASE_SECRET
        mock_settings.jwt_secret = LEGACY_SECRET

        token = _make_token({"sub": "user-1", "account_type": "admin"}, SUPABASE_SECRET)
        payload = await get_current_user(authorization=f"Bearer {token}")

        assert payload["sub"] == "user-1"
        assert payload["account_type"] == "admin"


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_admin_allowed(self):
        payload = {"sub": "user-1", "account_type": "admin"}
        result = await require_admin(user=payload)
        assert result == payload

    @pytest.mark.asyncio
    async def test_superadmin_allowed(self):
        payload = {"sub": "user-2", "account_type": "superadmin"}
        result = await require_admin(user=payload)
        assert result == payload

    @pytest.mark.asyncio
    async def test_regular_user_forbidden(self):
        payload = {"sub": "user-3", "account_type": "user"}
        with pytest.raises(HTTPException) as exc:
            await require_admin(user=payload)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Admin access required"

    @pytest.mark.asyncio
    async def test_no_account_type_forbidden(self):
        payload = {"sub": "user-4"}
        with pytest.raises(HTTPException) as exc:
            await require_admin(user=payload)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Admin access required"
