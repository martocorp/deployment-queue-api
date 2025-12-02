"""Unified authentication supporting GitHub OIDC and PAT."""

from datetime import UTC, datetime, timedelta
from typing import Optional

import httpx
from fastapi import Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .config import get_settings

security = HTTPBearer(auto_error=False)

# -----------------------------------------------------------------------------
# Caching
# -----------------------------------------------------------------------------

_jwks_cache: dict = {}
_jwks_cache_expiry: Optional[datetime] = None

# Cache org membership: key = "username:token_prefix" -> (set of orgs, expiry)
_org_membership_cache: dict[str, tuple[set[str], datetime]] = {}


def _get_jwks_cache_ttl() -> timedelta:
    return timedelta(seconds=get_settings().jwks_cache_ttl)


def _get_org_cache_ttl() -> timedelta:
    return timedelta(seconds=get_settings().org_membership_cache_ttl)


# -----------------------------------------------------------------------------
# Token Payload
# -----------------------------------------------------------------------------


class TokenPayload:
    """
    Unified token payload for both GitHub OIDC and CLI authentication.

    Attributes:
        organisation: GitHub organisation (tenant identifier)
        source: Authentication source ('github_oidc', 'github_pat', 'dev')
        repository: Full repo name for audit (org/repo)
        workflow: Workflow name for audit
        actor: GitHub username who authenticated
    """

    def __init__(
        self,
        organisation: str,
        source: str,
        repository: str = "",
        workflow: str = "",
        actor: str = "",
    ):
        self.organisation = organisation
        self.source = source
        self.repository = repository
        self.workflow = workflow
        self.actor = actor


# Alias for backwards compatibility
GitHubTokenPayload = TokenPayload


# -----------------------------------------------------------------------------
# GitHub OIDC Verification (for GitHub Actions)
# -----------------------------------------------------------------------------


async def _fetch_github_jwks() -> dict:
    """Fetch and cache GitHub's OIDC public keys (JWKS)."""
    global _jwks_cache, _jwks_cache_expiry

    settings = get_settings()
    now = datetime.now(UTC)
    if _jwks_cache and _jwks_cache_expiry and now < _jwks_cache_expiry:
        return _jwks_cache

    jwks_url = f"{settings.github_oidc_issuer}/.well-known/jwks"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_cache_expiry = now + _get_jwks_cache_ttl()

    return _jwks_cache


def _get_signing_key(jwks: dict, kid: str) -> dict:
    """Find signing key matching token's key ID (kid)."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unable to find matching signing key",
    )


async def _verify_github_oidc_token(token: str) -> TokenPayload:
    """
    Verify GitHub OIDC token (from GitHub Actions).

    Validates:
    - JWT signature against GitHub's public keys
    - Token issuer and audience
    - Token expiry
    - Presence of repository_owner claim
    """
    settings = get_settings()

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing key ID (kid)",
            )

        jwks = await _fetch_github_jwks()
        signing_key = _get_signing_key(jwks, kid)

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.github_oidc_issuer,
            audience=settings.github_oidc_audience,
        )

        organisation = payload.get("repository_owner", "")
        if not organisation:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing repository_owner claim",
            )

        return TokenPayload(
            organisation=organisation,
            source="github_oidc",
            repository=payload.get("repository", ""),
            workflow=payload.get("workflow", ""),
            actor=payload.get("actor", ""),
        )

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid OIDC token: {e}",
        )


# -----------------------------------------------------------------------------
# GitHub PAT Verification (for CLI)
# -----------------------------------------------------------------------------


def _github_headers(token: str) -> dict:
    """Build headers for GitHub API requests."""
    settings = get_settings()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": settings.github_api_version,
    }


async def _get_github_user(github_token: str) -> dict:
    """Get GitHub user info from token."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.github_api_url}/user",
            headers=_github_headers(github_token),
        )
        if response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GitHub token",
            )
        response.raise_for_status()
        return response.json()


async def _get_user_organisations(github_token: str) -> set[str]:
    """Get all organisations the user is a member of."""
    settings = get_settings()
    orgs: set[str] = set()
    page = 1

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            response = await client.get(
                f"{settings.github_api_url}/user/orgs",
                headers=_github_headers(github_token),
                params={"page": page, "per_page": 100},
            )
            response.raise_for_status()
            page_orgs = response.json()

            if not page_orgs:
                break

            orgs.update(org["login"].lower() for org in page_orgs)
            page += 1

            # Safety limit
            if page > 10:
                break

    return orgs


async def _verify_org_membership(
    github_token: str,
    organisation: str,
    username: str,
) -> bool:
    """
    Verify user is member of organisation.

    Uses cache to reduce GitHub API calls.
    """
    # Build cache key (use token prefix for uniqueness without storing full token)
    cache_key = f"{username}:{github_token[:8]}"
    now = datetime.now(UTC)

    # Check cache
    if cache_key in _org_membership_cache:
        cached_orgs, expiry = _org_membership_cache[cache_key]
        if now < expiry:
            return organisation.lower() in cached_orgs

    # Fetch from GitHub
    user_orgs = await _get_user_organisations(github_token)
    _org_membership_cache[cache_key] = (user_orgs, now + _get_org_cache_ttl())

    return organisation.lower() in user_orgs


async def _verify_github_pat(token: str, organisation: str) -> TokenPayload:
    """
    Verify GitHub PAT and check organisation membership.

    Validates:
    - Token is valid GitHub token
    - User is member of specified organisation
    """
    try:
        # Get user info
        user = await _get_github_user(token)
        username = user.get("login", "")

        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to get username from GitHub token",
            )

        # Verify org membership
        is_member = await _verify_org_membership(token, organisation, username)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User '{username}' is not a member of organisation '{organisation}'",
            )

        return TokenPayload(
            organisation=organisation,
            source="github_pat",
            actor=username,
            repository=f"{organisation}/cli",
            workflow="cli",
        )

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to verify GitHub token: {e}",
        )


# -----------------------------------------------------------------------------
# Token Type Detection
# -----------------------------------------------------------------------------


def _is_jwt_token(token: str) -> bool:
    """Check if token is a JWT (used by GitHub OIDC)."""
    try:
        jwt.get_unverified_header(token)
        return True
    except JWTError:
        return False


# -----------------------------------------------------------------------------
# Allowed Organisation Check
# -----------------------------------------------------------------------------


def _check_organisation_allowed(organisation: str) -> bool:
    """Check if organisation is in the allowed list."""
    settings = get_settings()
    if not settings.allowed_organisations:
        return True

    allowed = [org.strip().lower() for org in settings.allowed_organisations.split(",")]
    return organisation.lower() in allowed


# -----------------------------------------------------------------------------
# Unified Auth Dependency
# -----------------------------------------------------------------------------


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    x_organisation: Optional[str] = Header(None, alias="X-Organisation"),
) -> TokenPayload:
    """
    Unified authentication dependency supporting both GitHub OIDC and PAT.

    Authentication methods:

    1. GitHub OIDC (GitHub Actions):
       - Header: Authorization: Bearer <oidc_jwt>
       - Organisation: Extracted from token's repository_owner claim

    2. GitHub PAT (CLI):
       - Header: Authorization: Bearer <github_pat>
       - Header: X-Organisation: <organisation>
       - Organisation: Verified via GitHub API membership check

    Token type is detected automatically:
    - JWTs (have header.payload.signature format) -> OIDC flow
    - Non-JWTs (opaque tokens) -> PAT flow

    Usage in endpoints:
        token: TokenPayload = Depends(verify_token)
        # Then use token.organisation for tenant isolation
    """
    settings = get_settings()

    # Handle disabled auth (local development only)
    if not settings.auth_enabled:
        return TokenPayload(
            organisation=x_organisation or settings.dev_organisation,
            source="dev",
            actor="local-dev",
            repository=f"{x_organisation or settings.dev_organisation}/local",
            workflow="local-dev",
        )

    # Require credentials
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Detect token type and verify accordingly
    if _is_jwt_token(token):
        # GitHub OIDC token (from GitHub Actions)
        payload = await _verify_github_oidc_token(token)
    else:
        # GitHub PAT (from CLI)
        if not x_organisation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Organisation header required for CLI authentication",
            )
        payload = await _verify_github_pat(token, x_organisation)

    # Check organisation is allowed
    if not _check_organisation_allowed(payload.organisation):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Organisation '{payload.organisation}' is not allowed",
        )

    return payload


# Backwards compatibility alias
verify_github_token = verify_token
