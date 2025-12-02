"""Tests for unified authentication (GitHub OIDC and PAT)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from deployment_queue.auth import (
    TokenPayload,
    _check_organisation_allowed,
    _is_jwt_token,
    _org_membership_cache,
    _verify_github_pat,
    _verify_org_membership,
)


class TestTokenPayload:
    """Tests for TokenPayload class."""

    def test_token_payload_creation(self) -> None:
        """Token payload stores all fields correctly."""
        payload = TokenPayload(
            organisation="test-org",
            source="github_oidc",
            repository="test-org/test-repo",
            workflow="deploy.yml",
            actor="test-user",
        )

        assert payload.organisation == "test-org"
        assert payload.source == "github_oidc"
        assert payload.repository == "test-org/test-repo"
        assert payload.workflow == "deploy.yml"
        assert payload.actor == "test-user"

    def test_token_payload_defaults(self) -> None:
        """Token payload has sensible defaults."""
        payload = TokenPayload(
            organisation="test-org",
            source="github_pat",
        )

        assert payload.organisation == "test-org"
        assert payload.source == "github_pat"
        assert payload.repository == ""
        assert payload.workflow == ""
        assert payload.actor == ""


class TestTokenTypeDetection:
    """Tests for JWT vs PAT token detection."""

    def test_jwt_token_detected(self) -> None:
        """Valid JWT structure is detected as JWT."""
        # Valid JWT structure with base64-encoded header containing alg and typ
        # Header: {"alg":"RS256","typ":"JWT","kid":"test"}
        jwt_token = (
            "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dGVzdA"  # base64 "test" as signature placeholder
        )
        assert _is_jwt_token(jwt_token) is True

    def test_pat_token_detected(self) -> None:
        """GitHub PAT format is detected as non-JWT."""
        pat = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        assert _is_jwt_token(pat) is False

    def test_classic_pat_detected(self) -> None:
        """Classic GitHub token format is detected as non-JWT."""
        pat = "github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        assert _is_jwt_token(pat) is False

    def test_empty_token_detected_as_non_jwt(self) -> None:
        """Empty or invalid token is detected as non-JWT."""
        assert _is_jwt_token("") is False
        assert _is_jwt_token("invalid") is False


class TestOrganisationAllowList:
    """Tests for organisation allow list checking."""

    def test_no_restrictions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All organisations allowed when no restrictions configured."""
        from deployment_queue.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "test")
        monkeypatch.setenv("SNOWFLAKE_USER", "test")
        monkeypatch.setenv("ALLOWED_ORGANISATIONS", "")

        assert _check_organisation_allowed("any-org") is True

    def test_allowed_organisation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Organisation in allow list is allowed."""
        from deployment_queue.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "test")
        monkeypatch.setenv("SNOWFLAKE_USER", "test")
        monkeypatch.setenv("ALLOWED_ORGANISATIONS", "allowed-org,another-org")

        assert _check_organisation_allowed("allowed-org") is True
        assert _check_organisation_allowed("another-org") is True

    def test_disallowed_organisation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Organisation not in allow list is denied."""
        from deployment_queue.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "test")
        monkeypatch.setenv("SNOWFLAKE_USER", "test")
        monkeypatch.setenv("ALLOWED_ORGANISATIONS", "allowed-org")

        assert _check_organisation_allowed("other-org") is False

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Organisation matching is case insensitive."""
        from deployment_queue.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "test")
        monkeypatch.setenv("SNOWFLAKE_USER", "test")
        monkeypatch.setenv("ALLOWED_ORGANISATIONS", "Allowed-Org")

        assert _check_organisation_allowed("allowed-org") is True
        assert _check_organisation_allowed("ALLOWED-ORG") is True


class TestGitHubPATVerification:
    """Tests for GitHub PAT verification."""

    @pytest.mark.asyncio
    async def test_valid_pat_with_membership(self) -> None:
        """Valid PAT with org membership succeeds."""
        with patch("deployment_queue.auth._get_github_user") as mock_user, \
             patch("deployment_queue.auth._verify_org_membership") as mock_membership:

            mock_user.return_value = {"login": "testuser"}
            mock_membership.return_value = True

            payload = await _verify_github_pat("ghp_test", "test-org")

            assert payload.organisation == "test-org"
            assert payload.source == "github_pat"
            assert payload.actor == "testuser"
            assert payload.repository == "test-org/cli"
            assert payload.workflow == "cli"

    @pytest.mark.asyncio
    async def test_pat_without_membership(self) -> None:
        """PAT without org membership is rejected."""
        with patch("deployment_queue.auth._get_github_user") as mock_user, \
             patch("deployment_queue.auth._verify_org_membership") as mock_membership:

            mock_user.return_value = {"login": "testuser"}
            mock_membership.return_value = False

            with pytest.raises(HTTPException) as exc:
                await _verify_github_pat("ghp_test", "other-org")

            assert exc.value.status_code == 403
            assert "not a member" in exc.value.detail

    @pytest.mark.asyncio
    async def test_pat_with_empty_username(self) -> None:
        """PAT that returns no username is rejected."""
        with patch("deployment_queue.auth._get_github_user") as mock_user:

            mock_user.return_value = {"login": ""}

            with pytest.raises(HTTPException) as exc:
                await _verify_github_pat("ghp_test", "test-org")

            assert exc.value.status_code == 401
            assert "Unable to get username" in exc.value.detail


class TestOrgMembershipCache:
    """Tests for organisation membership caching."""

    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        """Cache prevents repeated GitHub API calls."""
        # Pre-populate cache
        cache_key = "testuser:ghp_test"
        _org_membership_cache[cache_key] = (
            {"test-org", "other-org"},
            datetime.now(UTC) + timedelta(minutes=5),
        )

        # Should use cache, not call GitHub
        with patch("deployment_queue.auth._get_user_organisations") as mock_get:
            result = await _verify_org_membership("ghp_testxxxx", "test-org", "testuser")

            assert result is True
            mock_get.assert_not_called()

        # Clean up
        del _org_membership_cache[cache_key]

    @pytest.mark.asyncio
    async def test_cache_miss_expired(self) -> None:
        """Expired cache entry triggers fresh fetch."""
        # Pre-populate cache with expired entry
        cache_key = "expireduser:ghp_expi"
        _org_membership_cache[cache_key] = (
            {"old-org"},
            datetime.now(UTC) - timedelta(minutes=5),  # Expired
        )

        # Should fetch from GitHub
        with patch("deployment_queue.auth._get_user_organisations") as mock_get:
            mock_get.return_value = {"new-org"}

            result = await _verify_org_membership(
                "ghp_expiredxx", "new-org", "expireduser"
            )

            assert result is True
            mock_get.assert_called_once()

        # Clean up
        if cache_key in _org_membership_cache:
            del _org_membership_cache[cache_key]

    @pytest.mark.asyncio
    async def test_cache_stores_lowercase_orgs(self) -> None:
        """Cache stores organisation names in lowercase."""
        cache_key = "caseuser:ghp_case"

        with patch("deployment_queue.auth._get_user_organisations") as mock_get:
            mock_get.return_value = {"test-org"}

            # Check with different case
            result = await _verify_org_membership(
                "ghp_casexxxx", "TEST-ORG", "caseuser"
            )

            assert result is True

        # Clean up
        if cache_key in _org_membership_cache:
            del _org_membership_cache[cache_key]
